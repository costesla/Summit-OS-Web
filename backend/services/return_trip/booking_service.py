"""
Return-trip resolve + confirm.

Two operations the passenger drives, both gated by the link token:

  * `resolve_flight` — they type a flight number; we turn it into ONE dated
    occurrence and persist it as a verification.
  * `confirm`        — they commit; we bind the flight, arm telemetry, and
    queue the calendar event, in one transaction.

**Why confirm takes a verification id and not a flight.** The occurrence is
resolved once, server-side, and referenced by id afterwards. If confirm
accepted flight details from the browser, the client could resolve a cheap
convenient flight and confirm a different one, and the binding would look
perfectly consistent. `get_live_verification` also scopes by workflow in the
WHERE clause, so a verification id belonging to someone else's workflow is
indistinguishable from one that never existed.

**Why resolve is metered.** Every resolve is a billed AeroAPI call. The token
holder therefore controls our spend, so the budget is charged BEFORE the
provider call, not after — charging afterwards means a provider that is slow or
erroring is free to be called repeatedly.
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from .errors import (
    AmbiguousFlightOccurrence, FlightNotFound, InvalidOrExpiredToken,
    RateLimitExceeded, ReturnBookingAlreadyExists,
)
from .flight_ident import parse_flight_ident
from .states import WorkflowState
from .store import ReturnTripStore
from .tokens import TokenService

# How far ahead the first telemetry check is scheduled after confirmation.
# Stage 5 owns the polling cadence; this only ensures a freshly bound flight is
# not left with a null next-check that no sweep would ever pick up.
FIRST_CHECK_MINUTES = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReturnTripBookingService:
    def __init__(self, *, store: ReturnTripStore, tokens: TokenService,
                 provider=None):
        self._store = store
        self._tokens = tokens
        self._provider = provider

    def _provider_or_default(self):
        if self._provider is None:
            from .flight_provider import default_provider
            self._provider = default_provider()
        return self._provider

    def _workflow_for(self, raw_token: str):
        """Resolve token → workflow, or raise. Never leaks which one failed."""
        record = self._tokens.resolve(raw_token)
        if not record:
            raise InvalidOrExpiredToken()
        workflow = self._store.get_workflow(record["workflow_id"])
        if workflow is None:
            # Token valid but workflow voided underneath it. Same error on
            # purpose: the passenger can do nothing differently either way.
            raise InvalidOrExpiredToken()
        return workflow

    # ── resolve ──────────────────────────────────────────────────────────────
    def resolve_flight(self, raw_token: str, *, flight_number: str,
                       service_date: date) -> Dict[str, Any]:
        workflow = self._workflow_for(raw_token)

        if workflow.status in (WorkflowState.CONFIRMED, WorkflowState.CANCELED,
                               WorkflowState.EXPIRED):
            raise ReturnBookingAlreadyExists(
                f"Workflow is {workflow.status.value}")

        # Parse BEFORE charging: a malformed flight number raises
        # InvalidFlightNumber, which is a 400 the passenger can fix, and should
        # cost them no budget and us no provider call.
        ident = parse_flight_ident(flight_number)

        if not self._tokens.charge_resolve(raw_token):
            raise RateLimitExceeded(
                "Too many flight lookups for this return trip")

        provider = self._provider_or_default()
        occurrences = provider.resolve_flight_occurrence(
            ident=ident, service_date=service_date)

        if not occurrences:
            raise FlightNotFound(
                f"No {ident.normalized} on {service_date.isoformat()}")

        if len(occurrences) > 1:
            # Not an error state for the workflow — the passenger picks one and
            # calls again with the disambiguating detail. The self-loop on
            # FLIGHT_VERIFICATION_PENDING exists for exactly this.
            raise AmbiguousFlightOccurrence(
                [self._candidate(o) for o in occurrences])

        occurrence = occurrences[0]
        verification_id = self._store.save_verification(
            workflow_id=workflow.workflow_id, occurrence=occurrence,
            ident_raw=ident.raw, ident_normalized=ident.normalized,
            service_date=service_date)

        # Move to PENDING on first resolve; the state machine allows the
        # self-loop so a retry with a different flight is legal.
        if workflow.status in (WorkflowState.REMINDER_SENT,
                               WorkflowState.FLIGHT_VERIFICATION_PENDING):
            self._store.transition(
                workflow.workflow_id, expected_version=workflow.version,
                from_state=workflow.status,
                to_state=WorkflowState.FLIGHT_VERIFICATION_PENDING)

        return {"verificationId": verification_id,
                "flight": self._candidate(occurrence)}

    @staticmethod
    def _candidate(occurrence) -> Dict[str, Any]:
        """Passenger-facing view of an occurrence. No provider ids, no PII.

        `flight_number` is the marketing number — the one printed on their
        ticket — which is what someone disambiguating between two legs will
        recognise. `best_arrival_utc` prefers actual over estimated over
        scheduled and never invents a time.
        """
        return {
            "flightNumber": occurrence.flight_number,
            "departureAirport": occurrence.departure.iata,
            "arrivalAirport": occurrence.arrival.iata,
            "isCodeshare": occurrence.is_codeshare,
            "scheduledArrivalUtc": (occurrence.scheduled_arrival_utc.isoformat()
                                    if occurrence.scheduled_arrival_utc else None),
            "bestArrivalUtc": (occurrence.best_arrival_utc.isoformat()
                               if occurrence.best_arrival_utc else None),
        }

    # ── confirm ──────────────────────────────────────────────────────────────
    def confirm(self, raw_token: str, *, verification_id: str,
                idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        workflow = self._workflow_for(raw_token)

        if workflow.status is WorkflowState.CONFIRMED:
            # Replay of a confirm the passenger already made — a double-submit
            # or a refreshed tab. Not an error to show them.
            return {"alreadyConfirmed": True, "workflowId": workflow.workflow_id}

        verification = self._store.get_live_verification(
            verification_id, workflow.workflow_id)
        if not verification:
            # Expired, consumed, or another workflow's. Indistinguishable by
            # design — see get_live_verification.
            raise InvalidOrExpiredToken("Verification is not usable")

        result = self._store.confirm_return_trip(
            workflow_id=workflow.workflow_id,
            expected_version=workflow.version,
            from_state=workflow.status,
            verification_id=verification_id,
            provider=verification["provider"],
            provider_flight_id=verification["provider_flight_id"],
            idempotency_key=idempotency_key,
            first_check_minutes=FIRST_CHECK_MINUTES,
        )
        if not result:
            # Lost the version race — someone else confirmed or cancelled
            # between our read and our write.
            raise ReturnBookingAlreadyExists("Return trip already resolved")

        # The link has done its job. Revoking is not merely tidy: a live link
        # to a confirmed workflow invites a second confirmation attempt that
        # can only fail confusingly.
        try:
            self._tokens.revoke(workflow.workflow_id)
        except Exception:
            logging.exception(
                f"Confirmed workflow {workflow.workflow_id} but could not revoke "
                "its link token")

        return {"alreadyConfirmed": False,
                "workflowId": workflow.workflow_id,
                "bindingId": result["binding_id"]}
