"""
Normalized flight domain types.

The booking domain must never hold a FlightAware or Flightradar24 response
object. Providers rename fields, change shapes between plans, and disagree with
each other about what "on time" means; if those objects leak into booking code,
swapping a provider becomes a rewrite instead of a new adapter.

Two rules run through this module:

  * UTC for persistence, IANA timezone retained for display. An arrival time
    without its airport's timezone cannot be shown correctly and cannot be
    scheduled against — so the timezone travels with the timestamp.

  * Unavailable is not the same as absent. A provider plan that doesn't return
    gate data is different from a flight that has no gate assigned yet, and
    both differ from "we never asked". `DataAvailability` records which optional
    groups we actually got, so the UI can say "gate not published" instead of
    silently rendering a blank and the caller never promises data it lacks.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class FlightStatus(str, Enum):
    """Provider statuses collapsed to the states the workflow reasons about."""
    SCHEDULED = "Scheduled"
    ACTIVE = "Active"          # departed, not yet arrived
    LANDED = "Landed"
    CANCELLED = "Cancelled"
    DIVERTED = "Diverted"
    UNKNOWN = "Unknown"

    @property
    def is_terminal(self) -> bool:
        """No further useful updates — stop polling and stop paying for it."""
        return self in (FlightStatus.LANDED, FlightStatus.CANCELLED,
                        FlightStatus.DIVERTED)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    """UTC ISO-8601, or None. Never raises on a naive datetime — it assumes
    UTC, because every timestamp that reaches persistence is already UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class Airport:
    """An endpoint of a flight. `timezone_name` is IANA (e.g. America/Denver)."""
    iata: Optional[str] = None
    icao: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    timezone_name: Optional[str] = None

    @property
    def code(self) -> Optional[str]:
        """Preferred display code — IATA is what a boarding pass shows."""
        return self.iata or self.icao

    def matches(self, expected: Optional[str]) -> bool:
        """True if `expected` equals any code we hold, case/space-insensitive.

        Used by the route guard, so it errs strict: an unknown expected code
        matches nothing rather than everything.
        """
        if not expected:
            return False
        want = str(expected).strip().upper()
        return want in {c.strip().upper() for c in (self.iata, self.icao) if c}

    def to_public(self) -> dict:
        return {"iata": self.iata, "name": self.name, "city": self.city}


@dataclass(frozen=True)
class DataAvailability:
    """Which optional field groups this provider actually returned."""
    has_estimated_times: bool = False
    has_actual_times: bool = False
    has_gates: bool = False
    has_terminal: bool = False
    has_timezones: bool = False

    def to_public(self) -> dict:
        return {
            "estimatedTimes": self.has_estimated_times,
            "actualTimes": self.has_actual_times,
            "gates": self.has_gates,
            "terminal": self.has_terminal,
        }


@dataclass(frozen=True)
class FlightOccurrence:
    """ONE dated operation of a flight number — the thing a booking binds to.

    `provider_flight_id` is the provider's handle for this specific leg. It is
    what telemetry polls, precisely because the flight number is not unique.
    """
    provider: str
    provider_flight_id: str

    marketing_carrier: Optional[str] = None
    marketing_number: Optional[str] = None
    operating_carrier: Optional[str] = None
    operating_number: Optional[str] = None

    departure: Airport = field(default_factory=Airport)
    arrival: Airport = field(default_factory=Airport)

    scheduled_departure_utc: Optional[datetime] = None
    scheduled_arrival_utc: Optional[datetime] = None
    estimated_departure_utc: Optional[datetime] = None
    estimated_arrival_utc: Optional[datetime] = None
    actual_departure_utc: Optional[datetime] = None
    actual_arrival_utc: Optional[datetime] = None

    departure_gate: Optional[str] = None
    arrival_gate: Optional[str] = None
    terminal: Optional[str] = None

    status: FlightStatus = FlightStatus.UNKNOWN
    airline_name: Optional[str] = None
    aircraft_type: Optional[str] = None
    diverted: bool = False
    cancelled: bool = False

    availability: DataAvailability = field(default_factory=DataAvailability)
    retrieved_at_utc: datetime = field(default_factory=utc_now)
    # Pointer to the archived raw payload, per the repo's retention policy.
    # Never the payload itself — it can carry provider-specific detail we have
    # no business handing to a passenger.
    raw_payload_reference: Optional[str] = None

    @property
    def flight_number(self) -> str:
        """The number a passenger recognises — the one on their ticket."""
        carrier = self.marketing_carrier or self.operating_carrier or ""
        number = self.marketing_number or self.operating_number or ""
        return f"{carrier}{number}"

    @property
    def is_codeshare(self) -> bool:
        """Marketing and operating carriers differ — the passenger's ticket
        says one airline, the aircraft belongs to another."""
        return bool(self.operating_carrier
                    and self.marketing_carrier
                    and self.operating_carrier != self.marketing_carrier)

    @property
    def best_arrival_utc(self) -> Optional[datetime]:
        """The arrival time to schedule a driver against: actual beats
        estimated beats scheduled. Never invents one."""
        return (self.actual_arrival_utc or self.estimated_arrival_utc
                or self.scheduled_arrival_utc)

    def to_public(self) -> dict:
        """Passenger-safe summary — the §6 verification shape.

        Only fields the provider actually returned. Nulls stay null rather
        than being back-filled with a scheduled time dressed up as an
        estimate.
        """
        return {
            "carrier": self.airline_name or self.marketing_carrier,
            "flightNumber": self.flight_number,
            "isCodeshare": self.is_codeshare,
            "operatedBy": (f"{self.operating_carrier}{self.operating_number or ''}"
                           if self.is_codeshare else None),
            "departureAirport": self.departure.to_public(),
            "scheduledDepartureAt": iso(self.scheduled_departure_utc),
            "departureTimeZone": self.departure.timezone_name,
            "arrivalAirport": self.arrival.to_public(),
            "scheduledArrivalAt": iso(self.scheduled_arrival_utc),
            "arrivalTimeZone": self.arrival.timezone_name,
            "estimatedArrivalAt": iso(self.estimated_arrival_utc),
            "status": self.status.value,
            "departureGate": self.departure_gate,
            "arrivalGate": self.arrival_gate,
            "aircraftType": self.aircraft_type,
            "dataAvailability": self.availability.to_public(),
        }


@dataclass(frozen=True)
class FlightTelemetry:
    """A monitoring snapshot for an already-bound occurrence."""
    provider: str
    provider_flight_id: str
    status: FlightStatus
    estimated_arrival_utc: Optional[datetime] = None
    actual_arrival_utc: Optional[datetime] = None
    arrival_gate: Optional[str] = None
    terminal: Optional[str] = None
    diverted: bool = False
    cancelled: bool = False
    diverted_to: Optional[Airport] = None
    retrieved_at_utc: datetime = field(default_factory=utc_now)

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def materially_differs_from(self, other: Optional["FlightTelemetry"]) -> bool:
        """True if this snapshot is worth persisting and acting on.

        Deduplication is not a micro-optimisation here: AeroAPI bills per call
        and per returned data, and every unchanged snapshot we store is a
        calendar update we might otherwise push for no reason. `retrieved_at`
        deliberately does NOT count as a difference — it changes every poll.
        """
        if other is None:
            return True
        return (
            self.status != other.status
            or self.estimated_arrival_utc != other.estimated_arrival_utc
            or self.actual_arrival_utc != other.actual_arrival_utc
            or self.arrival_gate != other.arrival_gate
            or self.terminal != other.terminal
            or self.diverted != other.diverted
            or self.cancelled != other.cancelled
        )


@dataclass(frozen=True)
class OccurrenceQuery:
    """What the caller is asking a provider to resolve."""
    ident_normalized: str
    service_date: "object"                    # datetime.date
    expected_arrival_code: Optional[str] = None
    expected_departure_code: Optional[str] = None
    dest_country: Optional[str] = None


def summarize_candidates(occurrences: List[FlightOccurrence]) -> List[dict]:
    """Minimal information for a passenger to pick the right leg — route and
    times only. Enough to disambiguate, nothing more."""
    return [
        {
            "verificationCandidateId": o.provider_flight_id,
            "flightNumber": o.flight_number,
            "departureAirport": o.departure.to_public(),
            "arrivalAirport": o.arrival.to_public(),
            "scheduledDepartureAt": iso(o.scheduled_departure_utc),
            "scheduledArrivalAt": iso(o.scheduled_arrival_utc),
            "operatedBy": (f"{o.operating_carrier}{o.operating_number or ''}"
                           if o.is_codeshare else None),
        }
        for o in occurrences
    ]
