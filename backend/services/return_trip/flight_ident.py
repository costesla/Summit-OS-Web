"""
Flight identifier and service-date parsing.

A flight number ALONE DOES NOT IDENTIFY A FLIGHT. `UA1234` operates most days,
and some idents fly several routes in one day (SWA250 is the case that already
bit this codebase — see services/flightaware.py's destination guard). Binding a
passenger to the wrong daily occurrence produces a booking that looks correct in
every UI and sends a driver to the airport on the wrong day.

So resolution takes ident + service date, and this module is the front door for
both. It normalises what a passenger typed into something a provider can match,
while keeping the original string for the audit trail — if a lookup later turns
out to have resolved the wrong leg, we need to know exactly what was entered,
not what we made of it.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Union

from .errors import InvalidFlightNumber, InvalidServiceDate

# Longest raw string we'll even look at. Matches Rides.CabinTokens.FlightNumber
# (NVARCHAR(16)) so anything we accept can also be persisted there.
MAX_IDENT_LENGTH = 16

# Carrier alternatives are spelled out rather than using [A-Z0-9]{2,3}, which
# looks equivalent but is not: a greedy alphanumeric class swallows the first
# digit of the flight number, so "UA1234" parses as carrier "UA1" / flight
# "234". The forms below are the ones that actually exist:
#   [A-Z]{2,3}  UA, UAL  — IATA two-letter and ICAO three-letter
#   [A-Z]\d     B6, U2   — IATA codes ending in a digit
#   \d[A-Z]     9W, 3U   — IATA codes starting with a digit
# The number then takes ALL remaining digits, which is what makes "UA0045"
# resolve to carrier UA / flight 45 instead of carrier UA0 / flight 045.
_IDENT_RE = re.compile(
    r"^(?P<carrier>[A-Z]{2,3}|[A-Z]\d|\d[A-Z])(?P<number>\d{1,4})(?P<suffix>[A-Z]?)$")

# How far either side of today a return service date may sit. Generous on
# purpose: rejecting a legitimate date is a dead end for the passenger, while
# an implausible one is caught by the provider returning no flight.
SERVICE_DATE_PAST_DAYS = 2
SERVICE_DATE_FUTURE_DAYS = 365


@dataclass(frozen=True)
class FlightIdent:
    """A parsed flight designator.

    `raw` is exactly what the passenger typed and is what gets written to the
    audit trail. Everything else is derived and safe to send to a provider.
    """
    raw: str
    normalized: str      # "UA1234" — carrier + number + suffix, no separators
    carrier: str         # "UA" / "UAL"
    number: str          # "1234" (leading zeros stripped)
    suffix: str = ""     # rare operational letter, e.g. the "A" in "AA100A"

    @property
    def is_icao_style(self) -> bool:
        """Three letters — the form AeroAPI treats as canonical."""
        return len(self.carrier) == 3 and self.carrier.isalpha()


def parse_flight_ident(raw: Union[str, None]) -> FlightIdent:
    """Normalise a passenger-entered flight number.

    Accepts the forms people actually type: "UA1234", "ua 1234", "UA-1234",
    "UAL1234". Raises InvalidFlightNumber for anything else rather than
    guessing — a wrong guess here books the wrong flight.
    """
    original = "" if raw is None else str(raw)
    if len(original) > MAX_IDENT_LENGTH:
        raise InvalidFlightNumber()

    # Strip the separators people use, then uppercase. Note this is applied to
    # a length-checked string, so it can't be used to smuggle a long ident past
    # the limit with padding.
    condensed = re.sub(r"[\s\-\.]", "", original).upper()
    if not condensed:
        raise InvalidFlightNumber()

    m = _IDENT_RE.match(condensed)
    if not m:
        raise InvalidFlightNumber()

    # Every carrier alternative in the pattern contains a letter, so a bare
    # number can't reach this point.
    carrier = m.group("carrier")

    # Providers don't zero-pad; "UA0045" and "UA45" are the same flight.
    number = m.group("number").lstrip("0") or "0"
    if number == "0":
        raise InvalidFlightNumber()

    suffix = m.group("suffix")
    return FlightIdent(
        raw=original,
        normalized=f"{carrier}{number}{suffix}",
        carrier=carrier,
        number=number,
        suffix=suffix,
    )


def parse_service_date(raw: Union[str, date, None], *,
                       today: Optional[date] = None) -> date:
    """Validate the flight's local departure date (YYYY-MM-DD).

    This is the DEPARTURE date in the origin airport's local time, which is how
    airlines label a service — not the arrival date, and not UTC. The provider
    adapter is responsible for comparing it in the right timezone.
    """
    if raw is None or raw == "":
        raise InvalidServiceDate()

    if isinstance(raw, datetime):
        parsed = raw.date()
    elif isinstance(raw, date):
        parsed = raw
    else:
        text = str(raw).strip()
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise InvalidServiceDate()

    reference = today or datetime.utcnow().date()
    if parsed < reference - timedelta(days=SERVICE_DATE_PAST_DAYS):
        raise InvalidServiceDate("That date has already passed.")
    if parsed > reference + timedelta(days=SERVICE_DATE_FUTURE_DAYS):
        raise InvalidServiceDate("That date is too far in the future to look up.")
    return parsed
