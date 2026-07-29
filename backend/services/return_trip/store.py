"""
Return-trip persistence. The database is the source of truth; the calendar is a
projection of it.

Schema conventions follow the repo rather than introducing a migration
framework mid-feature: idempotent `IF NOT EXISTS ... CREATE/ALTER` executed by
`ensure_schema()`, the same shape as `DatabaseClient.create_cabin_token` and
`finalize_service._claim_session`. Every timestamp is UTC (`GETUTCDATE()`),
because a schedule computed against local time breaks twice a year.

Three decisions worth knowing before reading:

  * **Uniqueness is a claim table, not a filtered index.** "At most one active
    return per outbound booking" could be a filtered unique index, but those
    have awkward predicate restrictions and this environment has no SQL Server
    to prove the DDL against. `ReturnTripActiveClaim` gets the same guarantee
    from a plain primary key and an IntegrityError — the exact pattern
    `_claim_session` already runs in production. Cancelling releases the claim,
    so a passenger who cancels can rebook.

  * **Optimistic concurrency on every state change.** `transition()` matches on
    the expected version and reports how many rows it touched. Two concurrent
    confirmations both read Version 3; only one writes Version 4, and the loser
    is told, rather than silently overwriting.

  * **The audit trail is written in the same transaction as the change.** An
    audit row that can be lost independently of the thing it records is worse
    than no audit trail, because it looks authoritative.

Nothing here logs passenger email, phone, or addresses. Workflow ids and
correlation ids only.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    import pyodbc
except ImportError:                     # pragma: no cover - tests stub the DB
    pyodbc = None                       # type: ignore

from .flight_types import FlightOccurrence, FlightTelemetry, iso
from .states import (
    TelemetryState, WorkflowState, assert_transition,
)

SCHEMA = "Bookings"

# Outbox rows a single drain pass will claim. Small on purpose: the worker runs
# on a timer, and a short batch that finishes beats a long one that gets killed
# mid-flight and leaves rows stuck in Processing.
OUTBOX_BATCH_SIZE = 20
# Backoff schedule for a failing outbox row, in minutes. Past the end of the
# list the row is dead-lettered rather than retried forever.
OUTBOX_BACKOFF_MINUTES = (1, 5, 15, 60, 240)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Workflow:
    """A return-trip workflow row.

    Carries the passenger's contact and the outbound endpoints directly:
    there is no account or saved-location table to reference (see
    docs/return-trip-engine-findings.md §2.2), so this row IS the identity the
    opaque link resolves to.
    """
    workflow_id: str
    outbound_booking_id: str
    status: WorkflowState
    version: int
    outbound_trip_id: Optional[str] = None
    passenger_email: Optional[str] = None
    passenger_name: Optional[str] = None
    passenger_phone: Optional[str] = None
    # The outbound pickup becomes the return DROP-OFF, and the outbound
    # airport becomes the return PICKUP. Stored, never put in a URL.
    original_pickup_text: Optional[str] = None
    original_dropoff_airport: Optional[str] = None
    reminder_dispatch_at_utc: Optional[datetime] = None
    reminder_dispatched_at_utc: Optional[datetime] = None
    estimated_return_at_utc: Optional[datetime] = None
    expiration_at_utc: Optional[datetime] = None
    correlation_id: Optional[str] = None
    created_at_utc: Optional[datetime] = None
    updated_at_utc: Optional[datetime] = None
    voided_at_utc: Optional[datetime] = None


class ReturnTripStore:
    """Repository for the return-trip tables.

    `connection_factory` is injectable so tests run against a fake cursor —
    the same approach `test_cabin_trip.py` uses.
    """

    def __init__(self, connection_factory=None):
        if connection_factory is None:
            from services.database import DatabaseClient
            connection_factory = DatabaseClient().get_connection
        self._connect = connection_factory

    # ── schema ───────────────────────────────────────────────────────────────
    def ensure_schema(self, cursor=None) -> None:
        """Create every table and index if absent. Safe to call repeatedly.

        Called at the head of each write path rather than once at startup:
        Azure Functions instances come and go, and a cold instance must not be
        the first thing to discover the table is missing.
        """
        owned = cursor is None
        conn = None
        if owned:
            conn = self._connect()
            if not conn:
                raise RuntimeError("Database unavailable")
            cursor = conn.cursor()
        try:
            for statement in _DDL:
                cursor.execute(statement)
            if owned:
                conn.commit()
        finally:
            if owned and conn is not None:
                cursor.close()
                conn.close()

    # ── workflow ─────────────────────────────────────────────────────────────
    def create_workflow(self, *, outbound_booking_id: str,
                        status: WorkflowState = WorkflowState.PENDING_RETURN_ESTIMATE,
                        correlation_id: Optional[str] = None,
                        **fields) -> Optional[Workflow]:
        """Create a workflow, or return None if one is already active.

        The None is the point. Trip-completion events get replayed — by a retry,
        a redelivered webhook, a driver double-tapping — and every replay must
        be a no-op rather than a second workflow that sends the passenger a
        second reminder for the same journey.
        """
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        workflow_id = new_id()
        now = _utcnow()
        try:
            self.ensure_schema(cur)
            # The claim goes in FIRST. If a workflow is already active for this
            # outbound booking the PK rejects it and we never write the row.
            try:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.ReturnTripActiveClaim "
                    "(OutboundBookingId, WorkflowId, ClaimedAtUtc) VALUES (?, ?, ?)",
                    (outbound_booking_id, workflow_id, now),
                )
            except _integrity_errors():
                conn.rollback()
                logging.info(
                    f"Return workflow already active for outbound {outbound_booking_id}; "
                    "ignoring duplicate completion event")
                return None

            cur.execute(
                f"INSERT INTO {SCHEMA}.ReturnTripWorkflow ("
                "WorkflowId, OutboundBookingId, OutboundTripId, PassengerEmail, "
                "PassengerName, PassengerPhone, OriginalPickupText, "
                "OriginalDropoffAirport, WorkflowStatus, ReminderDispatchAtUtc, "
                "EstimatedReturnAtUtc, ExpirationAtUtc, Version, CorrelationId, "
                "CreatedAtUtc, UpdatedAtUtc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (workflow_id, outbound_booking_id, fields.get("outbound_trip_id"),
                 fields.get("passenger_email"), fields.get("passenger_name"),
                 fields.get("passenger_phone"), fields.get("original_pickup_text"),
                 _upper(fields.get("original_dropoff_airport"), 8),
                 status.value, fields.get("reminder_dispatch_at_utc"),
                 fields.get("estimated_return_at_utc"), fields.get("expiration_at_utc"),
                 correlation_id, now, now),
            )
            self._audit(cur, workflow_id, "ReturnWorkflowCreated",
                        to_state=status, correlation_id=correlation_id)
            conn.commit()
            return Workflow(workflow_id=workflow_id,
                            outbound_booking_id=outbound_booking_id,
                            status=status, version=1, correlation_id=correlation_id,
                            created_at_utc=now, updated_at_utc=now,
                            **{k: v for k, v in fields.items()
                               if k in Workflow.__dataclass_fields__})
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT {_WORKFLOW_COLUMNS} FROM {SCHEMA}.ReturnTripWorkflow "
                        "WHERE WorkflowId = ? AND VoidedAtUtc IS NULL", (workflow_id,))
            row = cur.fetchone()
            return _workflow_from_row(row) if row else None
        finally:
            cur.close()
            conn.close()

    def transition(self, workflow_id: str, *, expected_version: int,
                   from_state: WorkflowState, to_state: WorkflowState,
                   correlation_id: Optional[str] = None,
                   **updates) -> bool:
        """Move a workflow, guarded by the transition table AND the row version.

        Two guards because they catch different bugs: the state machine stops
        an illegal move (skipping verification), the version stops a legal move
        applied twice concurrently. Returns False when another writer got there
        first — the caller retries or reports a conflict, never assumes.
        """
        assert_transition(from_state, to_state)     # raises on an illegal move

        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            if not self._apply_transition(cur, workflow_id,
                                          expected_version=expected_version,
                                          from_state=from_state, to_state=to_state,
                                          correlation_id=correlation_id,
                                          updates=updates):
                conn.rollback()
                return False
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def _apply_transition(self, cursor, workflow_id: str, *, expected_version: int,
                          from_state: WorkflowState, to_state: WorkflowState,
                          correlation_id: Optional[str] = None,
                          updates: Optional[Dict[str, Any]] = None) -> bool:
        """The move itself, on the caller's cursor and without committing.

        Factored out so `transition` and `enqueue_and_transition` cannot drift:
        the version guard, the audit row and the claim release are the parts
        that must happen on every transition, and duplicating them once would
        be enough for one copy to quietly lose the claim cleanup.
        """
        sets, params = ["WorkflowStatus = ?", "Version = Version + 1",
                        "UpdatedAtUtc = ?"], [to_state.value, _utcnow()]
        for column, value in _updatable(updates or {}):
            sets.append(f"{column} = ?")
            params.append(value)
        params.extend([workflow_id, expected_version, from_state.value])

        cursor.execute(
            f"UPDATE {SCHEMA}.ReturnTripWorkflow SET {', '.join(sets)} "
            "WHERE WorkflowId = ? AND Version = ? AND WorkflowStatus = ? "
            "AND VoidedAtUtc IS NULL",
            tuple(params),
        )
        if (cursor.rowcount or 0) == 0:
            logging.info(f"Workflow {workflow_id} transition {from_state.value}->"
                         f"{to_state.value} lost a concurrency race")
            return False
        self._audit(cursor, workflow_id, f"ReturnWorkflow{to_state.value}",
                    from_state=from_state, to_state=to_state,
                    correlation_id=correlation_id)
        # A workflow that reaches a dead end releases its claim, so the
        # passenger can be offered a return again later.
        if to_state in (WorkflowState.CANCELED, WorkflowState.EXPIRED):
            cursor.execute(
                f"DELETE FROM {SCHEMA}.ReturnTripActiveClaim WHERE WorkflowId = ?",
                (workflow_id,))
        return True

    def enqueue_and_transition(self, *, event_type: str, aggregate_id: str,
                               payload: Dict[str, Any], workflow_id: str,
                               expected_version: int, from_state: WorkflowState,
                               to_state: WorkflowState,
                               correlation_id: Optional[str] = None,
                               **updates) -> bool:
        """Queue a side effect and advance the workflow in ONE transaction.

        Split into two commits, a crash in the gap gives you either a workflow
        marked Sent whose reminder was never queued (silent no-send), or a
        queued reminder against a workflow still marked Dispatching, which the
        next claim re-sends. Committing them together is the entire reason the
        outbox exists rather than sending inline.

        Transition first: if it loses the version race the row belongs to
        another writer, and enqueuing anyway would post a side effect for work
        we did not do.
        """
        assert_transition(from_state, to_state)
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            if not self._apply_transition(cur, workflow_id,
                                          expected_version=expected_version,
                                          from_state=from_state, to_state=to_state,
                                          correlation_id=correlation_id,
                                          updates=updates):
                conn.rollback()
                return False
            self.enqueue(cur, event_type=event_type, aggregate_id=aggregate_id,
                         payload=payload)
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def claim_due_reminders(self, *, now: Optional[datetime] = None,
                            limit: int = 10) -> List[str]:
        """Atomically take ownership of reminders that are due.

        One UPDATE ... OUTPUT, not SELECT-then-UPDATE: with two workers (or one
        worker whose previous run is still finishing) a read-then-write sends
        the same passenger the same email twice. Whoever flips the row to
        Dispatching owns it.
        """
        now = now or _utcnow()
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            cur.execute(
                f"UPDATE TOP (?) {SCHEMA}.ReturnTripWorkflow "
                "SET WorkflowStatus = ?, Version = Version + 1, UpdatedAtUtc = ?, "
                "    ClaimedAtUtc = ? "
                "OUTPUT inserted.WorkflowId "
                "WHERE WorkflowStatus = ? AND VoidedAtUtc IS NULL "
                "  AND ReminderDispatchAtUtc IS NOT NULL "
                "  AND ReminderDispatchAtUtc <= ? "
                "  AND (ExpirationAtUtc IS NULL OR ExpirationAtUtc > ?)",
                (limit, WorkflowState.REMINDER_DISPATCHING.value, now, now,
                 WorkflowState.REMINDER_SCHEDULED.value, now, now),
            )
            claimed = [r[0] for r in cur.fetchall()]
            conn.commit()
            return claimed
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    # ── flight verification ──────────────────────────────────────────────────
    def save_verification(self, *, workflow_id: str, occurrence: FlightOccurrence,
                          ident_raw: str, ident_normalized: str,
                          service_date: date, ttl_minutes: int = 30) -> str:
        """Persist a resolved occurrence and return its id.

        Confirmation later references this id rather than accepting flight
        details from the browser. That is the whole reason it exists: between
        verification and confirmation the client must not be able to swap the
        flight for a different one.
        """
        verification_id = new_id()
        now = _utcnow()
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            cur.execute(
                f"INSERT INTO {SCHEMA}.ReturnFlightVerification ("
                "VerificationId, WorkflowId, Provider, ProviderFlightId, IdentRaw, "
                "IdentNormalized, ServiceDate, DepartureIata, ArrivalIata, "
                "ScheduledArrivalUtc, EstimatedArrivalUtc, ArrivalTimeZone, "
                "OccurrenceJson, ExpiresAtUtc, CreatedAtUtc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (verification_id, workflow_id, occurrence.provider,
                 occurrence.provider_flight_id, (ident_raw or "")[:32],
                 ident_normalized[:16], service_date,
                 occurrence.departure.iata, occurrence.arrival.iata,
                 occurrence.scheduled_arrival_utc, occurrence.estimated_arrival_utc,
                 occurrence.arrival.timezone_name,
                 json.dumps(occurrence.to_public()),
                 now + timedelta(minutes=ttl_minutes), now),
            )
            self._audit(cur, workflow_id, "ReturnFlightResolved",
                        detail={"providerFlightId": occurrence.provider_flight_id,
                                "arrival": occurrence.arrival.iata})
            conn.commit()
            return verification_id
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def get_live_verification(self, verification_id: str,
                              workflow_id: str) -> Optional[Dict[str, Any]]:
        """A verification that belongs to this workflow, is unexpired, unconsumed.

        Ownership is part of the WHERE clause, not a check afterwards: a
        verification id from someone else's workflow must be indistinguishable
        from one that never existed.
        """
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT VerificationId, WorkflowId, Provider, ProviderFlightId, "
                "ArrivalIata, ScheduledArrivalUtc, EstimatedArrivalUtc, "
                "ArrivalTimeZone, OccurrenceJson "
                f"FROM {SCHEMA}.ReturnFlightVerification "
                "WHERE VerificationId = ? AND WorkflowId = ? "
                "AND ConsumedAtUtc IS NULL AND ExpiresAtUtc > ?",
                (verification_id, workflow_id, _utcnow()),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "verification_id": row[0], "workflow_id": row[1],
                "provider": row[2], "provider_flight_id": row[3],
                "arrival_iata": row[4], "scheduled_arrival_utc": row[5],
                "estimated_arrival_utc": row[6], "arrival_timezone": row[7],
                "occurrence": json.loads(row[8]) if row[8] else None,
            }
        finally:
            cur.close()
            conn.close()

    # ── binding + telemetry ──────────────────────────────────────────────────
    def create_binding(self, cursor, *, return_booking_id: str, workflow_id: str,
                       provider: str, provider_flight_id: str,
                       next_check_at_utc: Optional[datetime] = None) -> str:
        """Bind a booking to ONE dated flight occurrence.

        Takes a cursor because this belongs inside the confirmation
        transaction — a booking that exists without its flight binding would
        never be monitored, and nothing downstream would notice.
        """
        binding_id = new_id()
        now = _utcnow()
        cursor.execute(
            f"INSERT INTO {SCHEMA}.BookingFlightBinding ("
            "BindingId, ReturnBookingId, WorkflowId, Provider, ProviderFlightId, "
            "TelemetryState, NextCheckAtUtc, FailureCount, CreatedAtUtc, UpdatedAtUtc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (binding_id, return_booking_id, workflow_id, provider, provider_flight_id,
             TelemetryState.PENDING.value, next_check_at_utc, now, now),
        )
        return binding_id

    def record_snapshot(self, *, binding_id: str, telemetry: FlightTelemetry,
                        previous: Optional[FlightTelemetry] = None,
                        next_check_at_utc: Optional[datetime] = None) -> bool:
        """Append a snapshot only when something actually changed.

        AeroAPI bills per call and per payload, and each stored snapshot can
        trigger a calendar push. An unchanged poll updates the schedule fields
        and writes nothing else. Returns whether a snapshot was written.
        """
        material = telemetry.materially_differs_from(previous)
        now = _utcnow()
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            if material:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.FlightTelemetrySnapshot ("
                    "BindingId, Status, EstimatedArrivalUtc, ActualArrivalUtc, "
                    "ArrivalGate, Terminal, Diverted, Cancelled, RetrievedAtUtc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (binding_id, telemetry.status.value,
                     telemetry.estimated_arrival_utc, telemetry.actual_arrival_utc,
                     telemetry.arrival_gate, telemetry.terminal,
                     1 if telemetry.diverted else 0,
                     1 if telemetry.cancelled else 0, telemetry.retrieved_at_utc),
                )
            cur.execute(
                f"UPDATE {SCHEMA}.BookingFlightBinding "
                "SET TelemetryState = ?, LastCheckedAtUtc = ?, NextCheckAtUtc = ?, "
                "    FailureCount = 0, UpdatedAtUtc = ? WHERE BindingId = ?",
                (_telemetry_state(telemetry).value, now, next_check_at_utc, now,
                 binding_id),
            )
            conn.commit()
            return material
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def record_poll_failure(self, *, binding_id: str,
                            next_check_at_utc: Optional[datetime] = None) -> None:
        """A failed poll increments a counter and reschedules. It does NOT
        change the telemetry state — a provider outage is not a fact about the
        aircraft, and must never look like a cancelled flight."""
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            cur.execute(
                f"UPDATE {SCHEMA}.BookingFlightBinding "
                "SET FailureCount = FailureCount + 1, LastCheckedAtUtc = ?, "
                "    NextCheckAtUtc = ?, UpdatedAtUtc = ? WHERE BindingId = ?",
                (_utcnow(), next_check_at_utc, _utcnow(), binding_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    # ── outbox ───────────────────────────────────────────────────────────────
    def enqueue(self, cursor, *, event_type: str, aggregate_id: str,
                payload: Dict[str, Any]) -> str:
        """Queue a side effect inside the caller's transaction.

        This is what makes the calendar a projection rather than a second
        source of truth: the booking and the intent to sync it commit together,
        so a calendar API that is down cannot roll back a confirmed booking and
        cannot be forgotten either.
        """
        outbox_id = new_id()
        now = _utcnow()
        cursor.execute(
            f"INSERT INTO {SCHEMA}.OutboxEvent ("
            "OutboxId, EventType, AggregateId, PayloadJson, Status, AttemptCount, "
            "NextAttemptAtUtc, CreatedAtUtc, UpdatedAtUtc) "
            "VALUES (?, ?, ?, ?, 'Pending', 0, ?, ?, ?)",
            (outbox_id, event_type, aggregate_id, json.dumps(payload), now, now, now),
        )
        return outbox_id

    def claim_outbox(self, *, now: Optional[datetime] = None,
                     limit: int = OUTBOX_BATCH_SIZE) -> List[Dict[str, Any]]:
        """Atomically claim due outbox rows, same one-statement rule as reminders."""
        now = now or _utcnow()
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            cur.execute(
                f"UPDATE TOP (?) {SCHEMA}.OutboxEvent "
                "SET Status = 'Processing', ClaimedAtUtc = ?, "
                "    AttemptCount = AttemptCount + 1, UpdatedAtUtc = ? "
                "OUTPUT inserted.OutboxId, inserted.EventType, inserted.AggregateId, "
                "       inserted.PayloadJson, inserted.AttemptCount "
                "WHERE Status = 'Pending' AND NextAttemptAtUtc <= ?",
                (limit, now, now, now),
            )
            rows = cur.fetchall()
            conn.commit()
            return [{"outbox_id": r[0], "event_type": r[1], "aggregate_id": r[2],
                     "payload": json.loads(r[3]) if r[3] else {},
                     "attempt": r[4]} for r in rows]
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def complete_outbox(self, outbox_id: str) -> None:
        self._set_outbox(outbox_id, "Done", None, None)

    def fail_outbox(self, outbox_id: str, *, attempt: int,
                    error: Optional[str] = None) -> bool:
        """Reschedule with backoff, or dead-letter once retries are exhausted.

        Returns True if it will be retried. `error` is truncated and is
        expected to be a message, never a provider payload or a stack trace.
        """
        if attempt >= len(OUTBOX_BACKOFF_MINUTES):
            self._set_outbox(outbox_id, "Failed", None, error)
            logging.error(f"Outbox {outbox_id} dead-lettered after {attempt} attempts")
            return False
        delay = OUTBOX_BACKOFF_MINUTES[max(0, attempt - 1)]
        self._set_outbox(outbox_id, "Pending",
                         _utcnow() + timedelta(minutes=delay), error)
        return True

    def _set_outbox(self, outbox_id: str, status: str,
                    next_attempt: Optional[datetime], error: Optional[str]) -> None:
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            cur.execute(
                f"UPDATE {SCHEMA}.OutboxEvent SET Status = ?, NextAttemptAtUtc = ?, "
                "LastError = ?, ClaimedAtUtc = NULL, UpdatedAtUtc = ? "
                "WHERE OutboxId = ?",
                (status, next_attempt, (error or "")[:1000] or None, _utcnow(),
                 outbox_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    # ── audit ────────────────────────────────────────────────────────────────
    def _audit(self, cursor, workflow_id: str, event_type: str, *,
               from_state: Optional[WorkflowState] = None,
               to_state: Optional[WorkflowState] = None,
               correlation_id: Optional[str] = None,
               detail: Optional[Dict[str, Any]] = None) -> None:
        """Append an audit row on the caller's cursor — same transaction as the
        change it records. `detail` must already be PII-free."""
        cursor.execute(
            f"INSERT INTO {SCHEMA}.ReturnWorkflowAuditEvent ("
            "WorkflowId, EventType, FromState, ToState, CorrelationId, DetailJson, "
            "CreatedAtUtc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workflow_id, event_type,
             from_state.value if from_state else None,
             to_state.value if to_state else None,
             correlation_id, json.dumps(detail) if detail else None, _utcnow()),
        )

    def audit(self, workflow_id: str, event_type: str, **kw) -> None:
        """Standalone audit write, for events with no accompanying row change
        (a link being opened, a lookup that found nothing)."""
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            self._audit(cur, workflow_id, event_type, **kw)
            conn.commit()
        finally:
            cur.close()
            conn.close()


# ── helpers ──────────────────────────────────────────────────────────────────
def _integrity_errors():
    """Duplicate-key exception types, tolerating pyodbc being absent in tests."""
    if pyodbc is not None:
        return (pyodbc.IntegrityError,)
    return (Exception,)


def _upper(value, limit):
    return (str(value).strip().upper()[:limit] or None) if value else None


def _telemetry_state(telemetry: FlightTelemetry) -> TelemetryState:
    from .states import telemetry_state_for
    return telemetry_state_for(telemetry.status)


_UPDATABLE_COLUMNS = {
    "reminder_dispatch_at_utc": "ReminderDispatchAtUtc",
    "reminder_dispatched_at_utc": "ReminderDispatchedAtUtc",
    "estimated_return_at_utc": "EstimatedReturnAtUtc",
    "expiration_at_utc": "ExpirationAtUtc",
    "original_pickup_text": "OriginalPickupText",
    "original_dropoff_airport": "OriginalDropoffAirport",
}


def _updatable(updates: Dict[str, Any]):
    """Whitelist mapping for transition(**updates).

    A whitelist rather than string interpolation of caller keys: these become
    column names in SQL, and an unchecked key there is an injection point.
    """
    for key, value in updates.items():
        column = _UPDATABLE_COLUMNS.get(key)
        if column is None:
            raise ValueError(f"{key} is not an updatable workflow field")
        yield column, value


_WORKFLOW_COLUMNS = (
    "WorkflowId, OutboundBookingId, OutboundTripId, PassengerEmail, PassengerName, "
    "PassengerPhone, OriginalPickupText, OriginalDropoffAirport, WorkflowStatus, "
    "ReminderDispatchAtUtc, ReminderDispatchedAtUtc, EstimatedReturnAtUtc, "
    "ExpirationAtUtc, Version, CorrelationId, CreatedAtUtc, UpdatedAtUtc, VoidedAtUtc"
)


def _workflow_from_row(row) -> Workflow:
    return Workflow(
        workflow_id=row[0], outbound_booking_id=row[1], outbound_trip_id=row[2],
        passenger_email=row[3], passenger_name=row[4], passenger_phone=row[5],
        original_pickup_text=row[6], original_dropoff_airport=row[7],
        status=WorkflowState(row[8]),
        reminder_dispatch_at_utc=row[9], reminder_dispatched_at_utc=row[10],
        estimated_return_at_utc=row[11], expiration_at_utc=row[12],
        version=row[13], correlation_id=row[14],
        created_at_utc=row[15], updated_at_utc=row[16], voided_at_utc=row[17],
    )


# ── DDL ──────────────────────────────────────────────────────────────────────
# Idempotent by construction, matching the convention in services/database.py.
# Soft delete (VoidedAtUtc) rather than DELETE, so an audit trail can still
# reference a withdrawn workflow.
_DDL = (
    "IF SCHEMA_ID('Bookings') IS NULL EXEC('CREATE SCHEMA Bookings')",

    # At most one ACTIVE return per outbound booking. A plain PK does the work;
    # cancelling deletes the row so the passenger can be offered a return again.
    f"IF OBJECT_ID('{SCHEMA}.ReturnTripActiveClaim') IS NULL "
    f"CREATE TABLE {SCHEMA}.ReturnTripActiveClaim ("
    "OutboundBookingId NVARCHAR(128) NOT NULL PRIMARY KEY, "
    "WorkflowId NVARCHAR(64) NOT NULL, "
    "ClaimedAtUtc DATETIME2 NOT NULL)",

    f"IF OBJECT_ID('{SCHEMA}.ReturnTripWorkflow') IS NULL "
    f"CREATE TABLE {SCHEMA}.ReturnTripWorkflow ("
    "WorkflowId NVARCHAR(64) NOT NULL PRIMARY KEY, "
    "OutboundBookingId NVARCHAR(128) NOT NULL, "
    "OutboundTripId NVARCHAR(128) NULL, "
    "PassengerEmail NVARCHAR(256) NULL, "
    "PassengerName NVARCHAR(200) NULL, "
    "PassengerPhone NVARCHAR(64) NULL, "
    "OriginalPickupText NVARCHAR(512) NULL, "
    "OriginalDropoffAirport NVARCHAR(8) NULL, "
    "WorkflowStatus NVARCHAR(40) NOT NULL, "
    "ReminderDispatchAtUtc DATETIME2 NULL, "
    "ReminderDispatchedAtUtc DATETIME2 NULL, "
    "EstimatedReturnAtUtc DATETIME2 NULL, "
    "ExpirationAtUtc DATETIME2 NULL, "
    "ClaimedAtUtc DATETIME2 NULL, "
    "Version INT NOT NULL DEFAULT 1, "
    "CorrelationId NVARCHAR(64) NULL, "
    "CreatedAtUtc DATETIME2 NOT NULL, "
    "UpdatedAtUtc DATETIME2 NOT NULL, "
    "VoidedAtUtc DATETIME2 NULL)",

    # The reminder worker's claim query filters on exactly these two columns.
    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ReturnTripWorkflow_Due') "
    f"CREATE INDEX IX_ReturnTripWorkflow_Due ON {SCHEMA}.ReturnTripWorkflow "
    "(WorkflowStatus, ReminderDispatchAtUtc)",

    f"IF OBJECT_ID('{SCHEMA}.ReturnFlightVerification') IS NULL "
    f"CREATE TABLE {SCHEMA}.ReturnFlightVerification ("
    "VerificationId NVARCHAR(64) NOT NULL PRIMARY KEY, "
    "WorkflowId NVARCHAR(64) NOT NULL, "
    "Provider NVARCHAR(64) NOT NULL, "
    "ProviderFlightId NVARCHAR(128) NOT NULL, "
    "IdentRaw NVARCHAR(32) NULL, "
    "IdentNormalized NVARCHAR(16) NOT NULL, "
    "ServiceDate DATE NOT NULL, "
    "DepartureIata NVARCHAR(8) NULL, "
    "ArrivalIata NVARCHAR(8) NULL, "
    "ScheduledArrivalUtc DATETIME2 NULL, "
    "EstimatedArrivalUtc DATETIME2 NULL, "
    "ArrivalTimeZone NVARCHAR(64) NULL, "
    "OccurrenceJson NVARCHAR(MAX) NULL, "
    "ExpiresAtUtc DATETIME2 NOT NULL, "
    "ConsumedAtUtc DATETIME2 NULL, "
    "CreatedAtUtc DATETIME2 NOT NULL)",

    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ReturnFlightVerification_Workflow') "
    f"CREATE INDEX IX_ReturnFlightVerification_Workflow ON {SCHEMA}.ReturnFlightVerification "
    "(WorkflowId, ExpiresAtUtc)",

    # One binding per return booking — a second would mean two telemetry
    # subscriptions racing to update the same calendar hold.
    f"IF OBJECT_ID('{SCHEMA}.BookingFlightBinding') IS NULL "
    f"CREATE TABLE {SCHEMA}.BookingFlightBinding ("
    "BindingId NVARCHAR(64) NOT NULL PRIMARY KEY, "
    "ReturnBookingId NVARCHAR(128) NOT NULL UNIQUE, "
    "WorkflowId NVARCHAR(64) NOT NULL, "
    "Provider NVARCHAR(64) NOT NULL, "
    "ProviderFlightId NVARCHAR(128) NOT NULL, "
    "TelemetryState NVARCHAR(40) NOT NULL, "
    "LastCheckedAtUtc DATETIME2 NULL, "
    "NextCheckAtUtc DATETIME2 NULL, "
    "FailureCount INT NOT NULL DEFAULT 0, "
    "CalendarEventId NVARCHAR(256) NULL, "
    "CalendarLockedByOwner BIT NOT NULL DEFAULT 0, "
    "CreatedAtUtc DATETIME2 NOT NULL, "
    "UpdatedAtUtc DATETIME2 NOT NULL)",

    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BookingFlightBinding_Due') "
    f"CREATE INDEX IX_BookingFlightBinding_Due ON {SCHEMA}.BookingFlightBinding "
    "(TelemetryState, NextCheckAtUtc)",

    # Append-only history. Written only on material change.
    f"IF OBJECT_ID('{SCHEMA}.FlightTelemetrySnapshot') IS NULL "
    f"CREATE TABLE {SCHEMA}.FlightTelemetrySnapshot ("
    "SnapshotId BIGINT IDENTITY(1,1) PRIMARY KEY, "
    "BindingId NVARCHAR(64) NOT NULL, "
    "Status NVARCHAR(40) NOT NULL, "
    "EstimatedArrivalUtc DATETIME2 NULL, "
    "ActualArrivalUtc DATETIME2 NULL, "
    "ArrivalGate NVARCHAR(16) NULL, "
    "Terminal NVARCHAR(16) NULL, "
    "Diverted BIT NOT NULL DEFAULT 0, "
    "Cancelled BIT NOT NULL DEFAULT 0, "
    "RetrievedAtUtc DATETIME2 NOT NULL)",

    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_FlightTelemetrySnapshot_Binding') "
    f"CREATE INDEX IX_FlightTelemetrySnapshot_Binding ON {SCHEMA}.FlightTelemetrySnapshot "
    "(BindingId, RetrievedAtUtc)",

    f"IF OBJECT_ID('{SCHEMA}.ReturnWorkflowAuditEvent') IS NULL "
    f"CREATE TABLE {SCHEMA}.ReturnWorkflowAuditEvent ("
    "EventId BIGINT IDENTITY(1,1) PRIMARY KEY, "
    "WorkflowId NVARCHAR(64) NOT NULL, "
    "EventType NVARCHAR(64) NOT NULL, "
    "FromState NVARCHAR(40) NULL, "
    "ToState NVARCHAR(40) NULL, "
    "CorrelationId NVARCHAR(64) NULL, "
    "DetailJson NVARCHAR(MAX) NULL, "
    "CreatedAtUtc DATETIME2 NOT NULL)",

    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ReturnWorkflowAuditEvent_Workflow') "
    f"CREATE INDEX IX_ReturnWorkflowAuditEvent_Workflow ON {SCHEMA}.ReturnWorkflowAuditEvent "
    "(WorkflowId, CreatedAtUtc)",

    f"IF OBJECT_ID('{SCHEMA}.OutboxEvent') IS NULL "
    f"CREATE TABLE {SCHEMA}.OutboxEvent ("
    "OutboxId NVARCHAR(64) NOT NULL PRIMARY KEY, "
    "EventType NVARCHAR(64) NOT NULL, "
    "AggregateId NVARCHAR(128) NOT NULL, "
    "PayloadJson NVARCHAR(MAX) NOT NULL, "
    "Status NVARCHAR(20) NOT NULL, "
    "AttemptCount INT NOT NULL DEFAULT 0, "
    "NextAttemptAtUtc DATETIME2 NULL, "
    "ClaimedAtUtc DATETIME2 NULL, "
    "LastError NVARCHAR(1000) NULL, "
    "CreatedAtUtc DATETIME2 NOT NULL, "
    "UpdatedAtUtc DATETIME2 NOT NULL)",

    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OutboxEvent_Due') "
    f"CREATE INDEX IX_OutboxEvent_Due ON {SCHEMA}.OutboxEvent "
    "(Status, NextAttemptAtUtc)",
)
