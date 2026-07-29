"""
Outbound-trip completion — the event the return-trip workflow hangs off.

SummitOS has no trip-completion signal (findings §2.1): a booking row is written
at *booking* time and never updated, and Tessie drives are never reconciled
against it. So completion has to be produced rather than observed, and the
decision (findings §5a) was driver-confirmed with a time-based safety net.

**Which trips arm a return, and why it is departures.** We arm when we drove the
passenger TO the airport — an outbound departure. The return leg is then their
inbound flight, which is the leg worth tracking: Stage 1's TelemetryState carries
LANDED and DIVERTED, and the arrival map and landed hand-off already exist for
meeting an aircraft. Arming on arrivals instead would produce a return of
hotel-to-airport, with no inbound aircraft and none of that machinery in play.
Stage 2's model says the same thing in its column names — `OriginalPickupText`
plus `OriginalDropoffAirport`, with the outbound drop-off being the airport.

The predicate follows the booking-direction logic from the multi-leg work: a
departure writes a FlightNumber with NO ExpectedDest, because `ExpectedDest`
means "the airport we're collecting at" and there is no collection at an airport
on the way out.

Two entry points, one path:

  * `complete_outbound_trip` — the driver tapped "trip complete".
  * `sweep_unconfirmed`      — nobody tapped, and the trip ended long enough
                               ago that we arm it anyway.

Both funnel into `_arm`, so the safety net cannot drift from the manual path.
Both are replay-safe: `create_workflow` takes a PK claim on the outbound
booking first and returns None when a workflow is already active, which makes
a double-tap, a retried request, and an overlapping sweep all no-ops.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .states import WorkflowState
from .store import ReturnTripStore

# How long after a trip's expected end the safety net gives up waiting for the
# driver. Four hours matches the cabin-token window, which is the other place
# this system already assumes "the trip is over by now".
SAFETY_NET_HOURS = 4

# Upper bound on one sweep pass. The sweep runs on a timer against a table that
# only grows, so an unbounded query is a slow-motion outage: bound it here and
# let the next tick take the rest.
SWEEP_BATCH_SIZE = 50


class CompletionOutcome:
    """Why a completion attempt did or did not arm a workflow.

    Distinguished rather than collapsed to a bool because the caller's response
    differs: ARMED and ALREADY_ACTIVE are both success to an HTTP caller, but
    only one of them should be counted when asking "how many returns did we
    open today?", and NOT_A_DEPARTURE is the answer to a support question
    ("why didn't my customer get a return reminder?") that a bare False hides.
    """
    ARMED = "Armed"
    ALREADY_ACTIVE = "AlreadyActive"
    NOT_A_DEPARTURE = "NotADeparture"
    UNKNOWN_BOOKING = "UnknownBooking"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def departure_metadata(booking_id: str, connection_factory) -> Optional[Dict[str, Any]]:
    """Flight details for an outbound booking, or None if it wasn't a departure.

    `ExpectedDest IS NULL` is the departure half of the predicate and it is
    load-bearing, not a tidy-up: `ExpectedDest` means "the airport we're
    collecting at", so an ARRIVAL has one and a DEPARTURE does not. Dropping
    the null check would arm a return for every airport trip in both
    directions, and the arrival ones have no inbound flight to track.

    Deliberately NOT reusing `DatabaseClient.get_cabin_trip`: that filters on
    `ExpiresAt > GETDATE()`, which is right for serving a live trip and exactly
    wrong here. A completed trip's token has usually expired by definition —
    the token window is four hours — so reusing it would return None for
    precisely the bookings this function exists to find.
    """
    conn = connection_factory()
    if not conn:
        raise RuntimeError("Database unavailable")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 FlightNumber FROM Rides.CabinTokens "
            "WHERE BookingID = ? AND FlightNumber IS NOT NULL "
            "  AND ExpectedDest IS NULL "
            "ORDER BY ExpiresAt DESC",
            (booking_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        return {"flight_number": row[0]}
    except Exception as exc:
        # Includes the pre-#10 case where the columns don't exist. Raising
        # rather than returning None on purpose: "no departure found" and "the
        # schema isn't there" must not look identical to the caller, or a
        # missing migration silently stops every return trip being armed and
        # nothing anywhere reports a problem.
        logging.error(f"departure_metadata failed for booking {booking_id}: {exc}")
        raise
    finally:
        conn.close()


def _arm(booking_id: str, *, store: ReturnTripStore, connection_factory,
         source: str, correlation_id: Optional[str] = None) -> str:
    """Shared arming path for both the driver tap and the safety net."""
    flight = departure_metadata(booking_id, connection_factory)
    if flight is None:
        logging.info(
            f"Outbound {booking_id} completed via {source} but is not an airport "
            "departure; no return workflow armed")
        return CompletionOutcome.NOT_A_DEPARTURE

    # Only fields the store actually persists. `create_workflow` reads its
    # **fields by snake_case name and silently ignores anything else, so an
    # invented key here would not raise — it would just quietly not be stored.
    workflow = store.create_workflow(
        outbound_booking_id=booking_id,
        status=WorkflowState.PENDING_RETURN_ESTIMATE,
        correlation_id=correlation_id,
    )
    if workflow is None:
        return CompletionOutcome.ALREADY_ACTIVE

    # The outbound flight number is history, not state: the return is a
    # different flight the passenger tells us in Stage 4. It belongs in the
    # audit trail, and there is no workflow column for it by design.
    store.audit(workflow.workflow_id, "OutboundTripCompleted",
                detail={"source": source,
                        "outboundFlight": flight["flight_number"]})
    return CompletionOutcome.ARMED


def complete_outbound_trip(booking_id: str, *, store: ReturnTripStore,
                           connection_factory,
                           correlation_id: Optional[str] = None) -> str:
    """Driver confirmed the outbound trip is done."""
    if not booking_id:
        return CompletionOutcome.UNKNOWN_BOOKING
    return _arm(booking_id, store=store, connection_factory=connection_factory,
                source="DriverConfirmed", correlation_id=correlation_id)


def find_unconfirmed(connection_factory, *, now: Optional[datetime] = None,
                     limit: int = SWEEP_BATCH_SIZE) -> List[str]:
    """Airport departures whose trip ended over SAFETY_NET_HOURS ago, unarmed.

    The active-claim table is the record of "already armed", so the NOT EXISTS
    against it is what stops the sweep re-offering a booking the driver already
    confirmed. `create_workflow` would reject the duplicate anyway — this just
    avoids doing that work once per tick, forever, for every trip ever taken.
    """
    now = now or _utcnow()
    cutoff = now - timedelta(hours=SAFETY_NET_HOURS)
    conn = connection_factory()
    if not conn:
        raise RuntimeError("Database unavailable")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT TOP (?) t.BookingID FROM Rides.CabinTokens t "
            "WHERE t.FlightNumber IS NOT NULL "
            "  AND t.ExpectedDest IS NULL "
            "  AND t.ExpiresAt <= ? "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM Bookings.ReturnTripActiveClaim c "
            "    WHERE c.OutboundBookingId = t.BookingID)",
            (limit, cutoff),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def sweep_unconfirmed(*, store: ReturnTripStore, connection_factory,
                      now: Optional[datetime] = None) -> Dict[str, int]:
    """Arm the returns the driver forgot to confirm.

    One booking failing must not abandon the rest of the batch — a single bad
    row would otherwise stall every later return trip behind it, and the timer
    would rediscover the same bad row on the next tick and stall again.
    """
    counts = {CompletionOutcome.ARMED: 0, CompletionOutcome.ALREADY_ACTIVE: 0,
              CompletionOutcome.NOT_A_DEPARTURE: 0, "Errors": 0}
    for booking_id in find_unconfirmed(connection_factory, now=now):
        try:
            outcome = _arm(booking_id, store=store,
                           connection_factory=connection_factory,
                           source="SafetyNet")
            counts[outcome] = counts.get(outcome, 0) + 1
        except Exception:
            # Logged with the booking id and counted. The count is what the
            # caller reports, so a run that armed nothing because everything
            # failed cannot be mistaken for a quiet night.
            logging.exception(f"Safety-net arming failed for outbound {booking_id}")
            counts["Errors"] += 1
    return counts
