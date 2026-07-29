"""
Return-trip state machines.

Status is not a string a controller may set. Every legal move lives in the
transition tables below and nowhere else, because the failure mode of loose
status handling is invisible: a workflow that jumps from ReminderScheduled
straight to Confirmed has skipped flight verification, and nothing about the
resulting row looks wrong afterwards.

Two separate machines, deliberately:

  * WORKFLOW tracks OUR process — reminding, verifying, confirming. We drive it.
  * TELEMETRY tracks the WORLD — the aircraft. We only observe it.

Conflating them would mean a diverted flight could mark our workflow failed, or
a provider outage could look like a cancelled booking. They move independently
and are allowed to disagree.
"""
from enum import Enum
from typing import Dict, FrozenSet

from .errors import InvalidStateTransition


class WorkflowState(str, Enum):
    """Our side of the return-trip process."""
    PENDING_RETURN_ESTIMATE = "PendingReturnEstimate"
    REMINDER_SCHEDULED = "ReminderScheduled"
    REMINDER_DISPATCHING = "ReminderDispatching"
    REMINDER_SENT = "ReminderSent"
    FLIGHT_VERIFICATION_PENDING = "FlightVerificationPending"
    FLIGHT_VERIFIED = "FlightVerified"
    CONFIRMATION_PROCESSING = "ConfirmationProcessing"
    CONFIRMED = "Confirmed"
    EXPIRED = "Expired"
    CANCELED = "Canceled"
    FAILED = "Failed"


class TelemetryState(str, Enum):
    """The aircraft's side. Observed, never chosen."""
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    ACTIVE = "Active"
    LANDED = "Landed"
    CANCELED = "Canceled"
    DIVERTED = "Diverted"
    UNKNOWN = "Unknown"
    MONITORING_COMPLETE = "MonitoringComplete"


# Terminal workflow states. Confirmed is terminal for THIS workflow: a further
# return trip is a new journey with its own workflow, not a mutation of this one.
WORKFLOW_TERMINAL: FrozenSet[WorkflowState] = frozenset({
    WorkflowState.CONFIRMED, WorkflowState.EXPIRED,
    WorkflowState.CANCELED, WorkflowState.FAILED,
})

_WORKFLOW_TRANSITIONS: Dict[WorkflowState, FrozenSet[WorkflowState]] = {
    # No usable return date yet — can't schedule a reminder against nothing.
    WorkflowState.PENDING_RETURN_ESTIMATE: frozenset({
        WorkflowState.REMINDER_SCHEDULED,
        WorkflowState.EXPIRED, WorkflowState.CANCELED, WorkflowState.FAILED,
    }),
    WorkflowState.REMINDER_SCHEDULED: frozenset({
        WorkflowState.REMINDER_DISPATCHING,
        # A passenger can change their return date after we've scheduled.
        WorkflowState.PENDING_RETURN_ESTIMATE,
        WorkflowState.EXPIRED, WorkflowState.CANCELED, WorkflowState.FAILED,
    }),
    # Claimed by a worker. Back to SCHEDULED is the retry path — the claim is
    # released so another run can pick it up without sending twice.
    WorkflowState.REMINDER_DISPATCHING: frozenset({
        WorkflowState.REMINDER_SENT, WorkflowState.REMINDER_SCHEDULED,
        WorkflowState.FAILED, WorkflowState.CANCELED,
    }),
    WorkflowState.REMINDER_SENT: frozenset({
        WorkflowState.FLIGHT_VERIFICATION_PENDING,
        WorkflowState.EXPIRED, WorkflowState.CANCELED, WorkflowState.FAILED,
    }),
    # Passenger has the form open. Self-loop: a failed lookup or a wrong flight
    # number must leave them able to try again.
    WorkflowState.FLIGHT_VERIFICATION_PENDING: frozenset({
        WorkflowState.FLIGHT_VERIFICATION_PENDING,
        WorkflowState.FLIGHT_VERIFIED,
        WorkflowState.EXPIRED, WorkflowState.CANCELED, WorkflowState.FAILED,
    }),
    # Verified but not confirmed. Back to PENDING covers "actually, wrong
    # flight" before they commit.
    WorkflowState.FLIGHT_VERIFIED: frozenset({
        WorkflowState.CONFIRMATION_PROCESSING,
        WorkflowState.FLIGHT_VERIFICATION_PENDING,
        WorkflowState.EXPIRED, WorkflowState.CANCELED, WorkflowState.FAILED,
    }),
    # Inside the confirmation transaction. Rolling back to FLIGHT_VERIFIED is
    # what makes a retry safe after a mid-transaction dependency failure.
    WorkflowState.CONFIRMATION_PROCESSING: frozenset({
        WorkflowState.CONFIRMED, WorkflowState.FLIGHT_VERIFIED,
        WorkflowState.FAILED,
    }),
    # A booked return can still be called off; it cannot be re-confirmed.
    WorkflowState.CONFIRMED: frozenset({WorkflowState.CANCELED}),
    WorkflowState.EXPIRED: frozenset(),
    WorkflowState.CANCELED: frozenset(),
    # Failure is recoverable by an operator re-arming the reminder.
    WorkflowState.FAILED: frozenset({
        WorkflowState.REMINDER_SCHEDULED, WorkflowState.CANCELED,
    }),
}

TELEMETRY_TERMINAL: FrozenSet[TelemetryState] = frozenset({
    TelemetryState.MONITORING_COMPLETE,
})

_TELEMETRY_TRANSITIONS: Dict[TelemetryState, FrozenSet[TelemetryState]] = {
    TelemetryState.PENDING: frozenset({
        TelemetryState.SCHEDULED, TelemetryState.ACTIVE, TelemetryState.CANCELED,
        TelemetryState.UNKNOWN, TelemetryState.MONITORING_COMPLETE,
    }),
    TelemetryState.SCHEDULED: frozenset({
        TelemetryState.ACTIVE, TelemetryState.CANCELED, TelemetryState.DIVERTED,
        TelemetryState.LANDED, TelemetryState.UNKNOWN,
        TelemetryState.MONITORING_COMPLETE,
    }),
    TelemetryState.ACTIVE: frozenset({
        TelemetryState.LANDED, TelemetryState.DIVERTED, TelemetryState.UNKNOWN,
        TelemetryState.CANCELED, TelemetryState.MONITORING_COMPLETE,
    }),
    # Landed is where the aircraft stops, but monitoring runs a little longer
    # (a gate can still be assigned), so it isn't terminal by itself.
    TelemetryState.LANDED: frozenset({
        TelemetryState.MONITORING_COMPLETE, TelemetryState.DIVERTED,
    }),
    TelemetryState.CANCELED: frozenset({TelemetryState.MONITORING_COMPLETE}),
    # A diversion still lands somewhere, and the passenger still needs
    # collecting — from a different airport.
    TelemetryState.DIVERTED: frozenset({
        TelemetryState.LANDED, TelemetryState.MONITORING_COMPLETE,
    }),
    # UNKNOWN is a provider outage, NOT a fact about the flight. Every real
    # state must remain reachable from it — this is why a temporary outage can
    # never strand or cancel a booking.
    TelemetryState.UNKNOWN: frozenset({
        TelemetryState.SCHEDULED, TelemetryState.ACTIVE, TelemetryState.LANDED,
        TelemetryState.CANCELED, TelemetryState.DIVERTED,
        TelemetryState.MONITORING_COMPLETE,
    }),
    TelemetryState.MONITORING_COMPLETE: frozenset(),
}


def _check(table, current, target, label):
    if current == target:
        # Idempotent re-application. Retries and redelivered events land here,
        # and they must be harmless — allowed only where the table permits a
        # self-loop, so a genuine no-op stays a no-op.
        if target in table.get(current, frozenset()):
            return True
        return False
    return target in table.get(current, frozenset())


def can_transition(current: WorkflowState, target: WorkflowState) -> bool:
    return _check(_WORKFLOW_TRANSITIONS, current, target, "workflow")


def assert_transition(current: WorkflowState, target: WorkflowState) -> WorkflowState:
    """Return `target`, or raise. Call this instead of assigning a status."""
    if not can_transition(current, target):
        raise InvalidStateTransition(
            f"Illegal workflow transition {current.value} -> {target.value}")
    return target


def can_transition_telemetry(current: TelemetryState, target: TelemetryState) -> bool:
    return _check(_TELEMETRY_TRANSITIONS, current, target, "telemetry")


def assert_transition_telemetry(current: TelemetryState,
                                target: TelemetryState) -> TelemetryState:
    if not can_transition_telemetry(current, target):
        raise InvalidStateTransition(
            f"Illegal telemetry transition {current.value} -> {target.value}")
    return target


def is_workflow_terminal(state: WorkflowState) -> bool:
    return state in WORKFLOW_TERMINAL


def telemetry_state_for(flight_status) -> TelemetryState:
    """Map an observed FlightStatus onto the telemetry machine.

    UNKNOWN maps to UNKNOWN rather than to any concrete state — we never
    invent a flight state from a provider's silence.
    """
    from .flight_types import FlightStatus
    return {
        FlightStatus.SCHEDULED: TelemetryState.SCHEDULED,
        FlightStatus.ACTIVE: TelemetryState.ACTIVE,
        FlightStatus.LANDED: TelemetryState.LANDED,
        FlightStatus.CANCELLED: TelemetryState.CANCELED,
        FlightStatus.DIVERTED: TelemetryState.DIVERTED,
        FlightStatus.UNKNOWN: TelemetryState.UNKNOWN,
    }.get(flight_status, TelemetryState.UNKNOWN)
