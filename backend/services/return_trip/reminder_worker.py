"""
Reminder worker — turns a due workflow into a queued reminder.

The concurrency problem is already solved upstream: `claim_due_reminders` is a
single `UPDATE ... OUTPUT` that flips REMINDER_SCHEDULED to REMINDER_DISPATCHING
and returns only the rows this run won. Two workers, or one worker overlapping
its own previous run, cannot both claim the same workflow, so this module never
has to reason about duplicate sends.

What it does have to get right is what happens AFTER the claim, because a claim
is a debt: the row now sits in REMINDER_DISPATCHING and no other run will touch
it. Crashing here without releasing it strands the passenger's reminder in a
state nothing retries. So every path out of a claim ends in an explicit
transition — REMINDER_SENT on success, back to REMINDER_SCHEDULED on a failure
worth retrying, FAILED only when retrying is pointless.

The reminder itself is enqueued to the outbox rather than sent inline. That is
the whole point of Stage 2's outbox: `api/bookings.py` sends mail fire-and-forget
and reports success even when both Graph and SMTP fail (findings §2.4), and a
reminder nobody receives with nothing queued and nothing logged is the same bug
with a longer fuse.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .states import WorkflowState
from .store import ReturnTripStore

# Event type the outbox drain (Stage 5) dispatches on.
REMINDER_EVENT = "ReturnTripReminderDue"

# Workflows claimed per tick. Kept small deliberately: each one costs a write
# and the timer runs often, so a large batch buys nothing and lengthens the
# window in which a crash strands claimed rows.
REMINDER_BATCH_SIZE = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _release(store: ReturnTripStore, workflow, reason: str) -> None:
    """Hand a claimed workflow back so a later tick can retry it.

    Failure to release is worse than the original error: the workflow is
    unreachable by any future run, so it is logged at error rather than
    swallowed, and the exception is not re-raised — one stuck row must not
    stop the rest of the batch being released.
    """
    try:
        store.transition(
            workflow.workflow_id,
            expected_version=workflow.version,
            from_state=WorkflowState.REMINDER_DISPATCHING,
            to_state=WorkflowState.REMINDER_SCHEDULED,
        )
        store.audit(workflow.workflow_id, "ReminderDispatchReleased",
                    detail={"reason": reason[:400]})
    except Exception:
        logging.exception(
            f"Workflow {workflow.workflow_id} is stranded in ReminderDispatching: "
            "the release transition itself failed")


def dispatch_one(workflow_id: str, *, store: ReturnTripStore) -> bool:
    """Queue the reminder for one claimed workflow. True if it was queued.

    Returns rather than raises on the ordinary failures, so `run_once` can
    report a batch total instead of dying on the first bad row.
    """
    workflow = store.get_workflow(workflow_id)
    if workflow is None:
        # Claimed a moment ago, so this means the row was voided underneath us.
        logging.warning(f"Claimed workflow {workflow_id} vanished before dispatch")
        return False

    if workflow.status is not WorkflowState.REMINDER_DISPATCHING:
        # Someone else moved it — cancelled, expired, or an operator intervened.
        # Not ours to send, and not ours to release either.
        logging.info(
            f"Workflow {workflow_id} left ReminderDispatching before dispatch "
            f"(now {workflow.status.value}); skipping")
        return False

    if not workflow.passenger_email:
        # Nothing to send to, and no later run will fix it. FAILED is the
        # honest terminal state — it is operator-recoverable by design, where
        # a silent skip would leave a row that looks scheduled forever.
        logging.error(
            f"Workflow {workflow_id} has no passenger email; cannot send reminder")
        try:
            store.transition(
                workflow_id, expected_version=workflow.version,
                from_state=WorkflowState.REMINDER_DISPATCHING,
                to_state=WorkflowState.FAILED,
            )
            store.audit(workflow_id, "ReminderFailed",
                        detail={"reason": "no passenger email"})
        except Exception:
            logging.exception(f"Could not mark workflow {workflow_id} failed")
        return False

    payload: Dict[str, Any] = {
        "workflowId": workflow.workflow_id,
        "outboundBookingId": workflow.outbound_booking_id,
        "passengerEmail": workflow.passenger_email,
        "passengerName": workflow.passenger_name,
        # The return leg reverses the outbound: we collect at the airport and
        # drop at the original pickup.
        "returnPickupAirport": workflow.original_dropoff_airport,
        "returnDropoffText": workflow.original_pickup_text,
        "estimatedReturnAtUtc": (workflow.estimated_return_at_utc.isoformat()
                                 if workflow.estimated_return_at_utc else None),
        "correlationId": workflow.correlation_id,
    }

    try:
        # Enqueue and advance in ONE transaction. Split across two, a crash
        # between them either sends a reminder for a workflow still marked
        # Dispatching (double send on the retry) or advances one whose
        # reminder was never queued (silent no-send). Committing together is
        # what makes the outbox worth having.
        store.enqueue_and_transition(
            event_type=REMINDER_EVENT,
            aggregate_id=workflow.workflow_id,
            payload=payload,
            workflow_id=workflow.workflow_id,
            expected_version=workflow.version,
            from_state=WorkflowState.REMINDER_DISPATCHING,
            to_state=WorkflowState.REMINDER_SENT,
            reminder_dispatched_at_utc=_utcnow(),
        )
    except Exception as exc:
        logging.exception(f"Failed to queue reminder for workflow {workflow_id}")
        _release(store, workflow, f"enqueue failed: {exc}")
        return False

    store.audit(workflow_id, "ReminderQueued")
    return True


def run_once(*, store: ReturnTripStore, now: Optional[datetime] = None,
             limit: int = REMINDER_BATCH_SIZE) -> Dict[str, int]:
    """One pass: claim what's due, queue each, report what happened.

    The returned counts are the run's only observable output, so they
    distinguish queued from failed. A pass that claimed ten and queued none is
    a different event from a quiet pass, and the caller must be able to tell.
    """
    claimed = store.claim_due_reminders(now=now, limit=limit)
    result = {"claimed": len(claimed), "queued": 0, "failed": 0}
    for workflow_id in claimed:
        try:
            if dispatch_one(workflow_id, store=store):
                result["queued"] += 1
            else:
                result["failed"] += 1
        except Exception:
            # dispatch_one handles its own errors; this is the belt-and-braces
            # case so one unexpected raise cannot abandon the rest of the batch.
            logging.exception(f"Unhandled error dispatching workflow {workflow_id}")
            result["failed"] += 1
    if result["failed"]:
        logging.error(
            f"Reminder pass: {result['queued']} queued, {result['failed']} failed "
            f"of {result['claimed']} claimed")
    return result
