"""
Flight provider abstraction.

The booking domain talks to `FlightDataProvider` and nothing else. Concrete
providers sit behind it, so adding Flightradar24 as a second source, or moving
off AeroAPI entirely, is a new adapter rather than a change to booking logic.

Two behaviours here are worth stating plainly because both are about NOT
guessing:

  * `resolve_flight_occurrence` returns a LIST. A flight number plus a date can
    still match several legs — codeshares, and idents genuinely reused across
    routes on one day. Returning "the best one" is how a passenger ends up
    bound to the wrong flight, so the caller is forced to deal with the
    ambiguity (and asks the passenger).

  * Service-date matching is done in the ORIGIN AIRPORT'S LOCAL TIME, because
    that is how an airline labels a service. A 11:30pm departure from Denver is
    the 6th locally and the 7th in UTC; matching on UTC would silently drop it.
    When the provider gives us no timezone we widen to a UTC window rather than
    dropping candidates, and record that we did via DataAvailability.

Cost note: AeroAPI bills per call and per returned payload. Every method here
takes `cache_ttl` and passes it through to the client's cache; callers in the
polling path are expected to use it.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Protocol, runtime_checkable

try:                                    # py3.9+
    from zoneinfo import ZoneInfo
except ImportError:                     # pragma: no cover - repo runs 3.11
    ZoneInfo = None                     # type: ignore

from .errors import FlightProviderUnavailable
from .flight_types import (
    Airport, DataAvailability, FlightOccurrence, FlightStatus, FlightTelemetry,
    OccurrenceQuery, utc_now,
)

PROVIDER_AEROAPI = "flightaware-aeroapi"

# How far off the requested service date a candidate may sit when we have no
# timezone to place it precisely. One day either way covers every real UTC
# offset (max ±14h) without letting an unrelated day's leg through.
_UNTIMEZONED_DATE_TOLERANCE_DAYS = 1


@runtime_checkable
class FlightDataProvider(Protocol):
    """What the booking domain is allowed to ask of a flight data source."""

    name: str

    def resolve_flight_occurrence(
        self, query: OccurrenceQuery, *, cache_ttl: Optional[int] = None,
    ) -> List[FlightOccurrence]:
        """Every dated operation matching the query. May be empty; may be >1."""
        ...

    def get_flight_status(
        self, provider_flight_id: str, *, cache_ttl: Optional[int] = None,
    ) -> Optional[FlightTelemetry]:
        """Current state of one already-bound occurrence."""
        ...


# ── parsing helpers (pure, provider-shaped in / domain-shaped out) ───────────
def _parse_utc(value) -> Optional[datetime]:
    """AeroAPI ISO-8601 (or epoch) -> tz-aware UTC datetime, or None."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _airport_from(raw: Optional[dict]) -> Airport:
    if not isinstance(raw, dict):
        return Airport()
    return Airport(
        iata=raw.get("code_iata") or raw.get("code_lid"),
        icao=raw.get("code_icao") or raw.get("code"),
        name=raw.get("name"),
        city=raw.get("city"),
        timezone_name=raw.get("timezone"),
    )


def _split_ident(ident: Optional[str]):
    """'UA1234' -> ('UA', '1234'). Returns (None, None) for anything else."""
    if not ident:
        return None, None
    text = str(ident).strip().upper()
    i = 0
    while i < len(text) and not text[i].isdigit():
        i += 1
    carrier, number = text[:i], text[i:]
    return (carrier or None), (number or None)


def _status_from(raw: dict) -> FlightStatus:
    """Collapse AeroAPI's free-text status + flags into our enum.

    Flags win over the text: `cancelled`/`diverted` are booleans the provider
    sets deliberately, while `status` is a display string that varies.
    """
    if raw.get("cancelled"):
        return FlightStatus.CANCELLED
    if raw.get("diverted"):
        return FlightStatus.DIVERTED
    if raw.get("actual_in") or raw.get("actual_on"):
        return FlightStatus.LANDED
    if raw.get("actual_out") or raw.get("actual_off"):
        return FlightStatus.ACTIVE
    text = str(raw.get("status") or "").lower()
    if "cancel" in text:
        return FlightStatus.CANCELLED
    if "divert" in text:
        return FlightStatus.DIVERTED
    if "arriv" in text or "landed" in text:
        return FlightStatus.LANDED
    if "en route" in text or "airborne" in text or "taxi" in text:
        return FlightStatus.ACTIVE
    if "scheduled" in text or raw.get("scheduled_out"):
        return FlightStatus.SCHEDULED
    return FlightStatus.UNKNOWN


def _local_departure_date(scheduled_utc: Optional[datetime],
                          tz_name: Optional[str]) -> Optional[date]:
    """The airline's service date: departure date in the ORIGIN's local time."""
    if scheduled_utc is None:
        return None
    if tz_name and ZoneInfo is not None:
        try:
            return scheduled_utc.astimezone(ZoneInfo(tz_name)).date()
        except Exception:                       # unknown/garbage tz identifier
            logging.debug(f"Unrecognised timezone from provider: {tz_name!r}")
    return scheduled_utc.date()


def occurrence_matches_service_date(occurrence: FlightOccurrence,
                                    service_date: date) -> bool:
    """Whether this leg is the requested day's service.

    With a timezone we compare exactly. Without one we accept ±1 day rather
    than dropping a leg we simply couldn't place — a slightly wider candidate
    set is recoverable (the passenger picks), a wrongly-excluded flight is a
    dead end.
    """
    local = _local_departure_date(occurrence.scheduled_departure_utc,
                                  occurrence.departure.timezone_name)
    if local is None:
        return False
    if occurrence.availability.has_timezones:
        return local == service_date
    return abs((local - service_date).days) <= _UNTIMEZONED_DATE_TOLERANCE_DAYS


def occurrence_from_aeroapi(raw: dict, *, requested_ident: Optional[str] = None
                            ) -> Optional[FlightOccurrence]:
    """Map one AeroAPI leg to the domain type. None if it has no usable id."""
    if not isinstance(raw, dict):
        return None
    fa_id = raw.get("fa_flight_id")
    if not fa_id:
        return None

    origin = _airport_from(raw.get("origin"))
    destination = _airport_from(raw.get("destination"))

    # Marketing = what's on the passenger's ticket (the ident they gave us).
    # Operating = whose aircraft it is. Only claim a codeshare when the
    # provider actually disagrees with the marketing carrier.
    marketing_carrier, marketing_number = _split_ident(
        raw.get("ident_iata") or raw.get("ident") or requested_ident)
    operator = raw.get("operator_iata") or raw.get("operator")
    operating_carrier = None
    operating_number = None
    if operator and marketing_carrier and str(operator).upper() != marketing_carrier:
        operating_carrier = str(operator).upper()
        _, operating_number = _split_ident(raw.get("ident_icao") or raw.get("ident"))

    est_dep = _parse_utc(raw.get("estimated_out") or raw.get("estimated_off"))
    est_arr = _parse_utc(raw.get("estimated_in") or raw.get("estimated_on"))
    act_dep = _parse_utc(raw.get("actual_out") or raw.get("actual_off"))
    act_arr = _parse_utc(raw.get("actual_in") or raw.get("actual_on"))
    dep_gate = raw.get("gate_origin")
    arr_gate = raw.get("gate_destination")
    terminal = raw.get("terminal_destination") or raw.get("terminal_origin")

    availability = DataAvailability(
        has_estimated_times=bool(est_dep or est_arr),
        has_actual_times=bool(act_dep or act_arr),
        has_gates=bool(dep_gate or arr_gate),
        has_terminal=bool(terminal),
        has_timezones=bool(origin.timezone_name and destination.timezone_name),
    )

    return FlightOccurrence(
        provider=PROVIDER_AEROAPI,
        provider_flight_id=str(fa_id),
        marketing_carrier=marketing_carrier,
        marketing_number=marketing_number,
        operating_carrier=operating_carrier,
        operating_number=operating_number,
        departure=origin,
        arrival=destination,
        scheduled_departure_utc=_parse_utc(raw.get("scheduled_out")),
        scheduled_arrival_utc=_parse_utc(raw.get("scheduled_in")),
        estimated_departure_utc=est_dep,
        estimated_arrival_utc=est_arr,
        actual_departure_utc=act_dep,
        actual_arrival_utc=act_arr,
        departure_gate=dep_gate,
        arrival_gate=arr_gate,
        terminal=terminal,
        status=_status_from(raw),
        airline_name=raw.get("operator_name") or raw.get("airline"),
        aircraft_type=raw.get("aircraft_type"),
        diverted=bool(raw.get("diverted")),
        cancelled=bool(raw.get("cancelled")),
        availability=availability,
        retrieved_at_utc=utc_now(),
    )


class AeroApiFlightProvider:
    """FlightDataProvider over the repo's existing FlightAware client.

    The client is injectable so tests never make a billable call.
    """

    name = PROVIDER_AEROAPI

    def __init__(self, client=None):
        if client is None:
            from services.flightaware import FlightAwareClient
            client = FlightAwareClient()
        self._client = client

    def resolve_flight_occurrence(
        self, query: OccurrenceQuery, *, cache_ttl: Optional[int] = None,
    ) -> List[FlightOccurrence]:
        try:
            raw_legs = self._client.flight_candidates(
                query.ident_normalized,
                cache_ttl=cache_ttl,
                expected_destination=query.expected_arrival_code,
                dest_country=query.dest_country,
            )
        except Exception as e:
            # The client swallows its own API errors; anything reaching here is
            # unexpected (network, auth, a shape change). Surface it as a
            # retryable dependency failure, never as "flight not found" — the
            # passenger must not be told their real flight doesn't exist.
            logging.error(f"Flight provider failure for {query.ident_normalized}: {e}")
            raise FlightProviderUnavailable() from e

        occurrences = []
        for leg in raw_legs or []:
            occ = occurrence_from_aeroapi(leg, requested_ident=query.ident_normalized)
            if occ is None:
                continue
            if not occurrence_matches_service_date(occ, query.service_date):
                continue
            # Belt and braces: flight_candidates already guards the arrival
            # airport, but the guard is the difference between the right
            # airport and a wasted trip, so it's re-asserted on the mapped type.
            if query.expected_arrival_code and not occ.arrival.matches(query.expected_arrival_code):
                continue
            if query.expected_departure_code and not occ.departure.matches(query.expected_departure_code):
                continue
            occurrences.append(occ)

        # Stable, human-sensible order for the ambiguity picker.
        occurrences.sort(
            key=lambda o: (o.scheduled_departure_utc or datetime.max.replace(tzinfo=timezone.utc),
                           o.provider_flight_id))
        return occurrences

    def get_flight_status(
        self, provider_flight_id: str, *, cache_ttl: Optional[int] = None,
    ) -> Optional[FlightTelemetry]:
        try:
            raw = self._client.flight_by_fa_id(provider_flight_id, cache_ttl=cache_ttl)
        except Exception as e:
            logging.error(f"Flight provider failure for {provider_flight_id}: {e}")
            raise FlightProviderUnavailable() from e
        if not raw:
            return None

        diverted_to = None
        if raw.get("diverted") and raw.get("actual_destination"):
            diverted_to = _airport_from(raw.get("actual_destination"))

        return FlightTelemetry(
            provider=self.name,
            provider_flight_id=str(raw.get("fa_flight_id") or provider_flight_id),
            status=_status_from(raw),
            estimated_arrival_utc=_parse_utc(raw.get("estimated_in") or raw.get("estimated_on")),
            actual_arrival_utc=_parse_utc(raw.get("actual_in") or raw.get("actual_on")),
            arrival_gate=raw.get("gate_destination"),
            terminal=raw.get("terminal_destination"),
            diverted=bool(raw.get("diverted")),
            cancelled=bool(raw.get("cancelled")),
            diverted_to=diverted_to,
            retrieved_at_utc=utc_now(),
        )


def default_provider() -> FlightDataProvider:
    """The configured provider. Single seam for a future FLIGHT_PROVIDER
    setting — callers should never construct an adapter directly."""
    return AeroApiFlightProvider()
