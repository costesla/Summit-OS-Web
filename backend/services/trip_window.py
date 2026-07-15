"""
Trip-window gate — decides whether the vehicle's live location may be public.

SECURITY CONTROL. The public map (/api/vehicle-location -> get_public_state)
must reveal real coordinates ONLY while a customer trip is actually running.
Any other time — parked at a charger, running errands, sitting in a driveway —
the location is private.

Design rules (do not relax without a deliberate decision):
  1. FAIL CLOSED. Any error, timeout, unparseable event, or ambiguity returns
     False (=> caller shows the privacy shield). Silence is safety.
  2. Only real bookings count. SummitOS writes trips as calendar events with a
     "Booking:" subject prefix (see services/bookings.py create_appointment).
     A personal calendar entry must NEVER unlock the live location.
  3. Cached. The public homepage polls every ~20s per visitor; without a cache
     this would hammer Microsoft Graph into rate limits.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

# Location goes live this long before a scheduled pickup (driver en route)…
LEAD_MINUTES = 30
# …and stays live this long after the scheduled end (drop-off wrap-up).
TRAIL_MINUTES = 30

CACHE_TTL_SEC = 60          # success: matches the ~20s public poll cadence
CACHE_TTL_FAILURE_SEC = 15  # failure: shorter, so we recover quickly

# Windows timezone names Graph can return, mapped to IANA.
_WINDOWS_TZ = {
    "Mountain Standard Time": "America/Denver",
    "Mountain Daylight Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "UTC": "UTC",
}

_cache = {"value": None, "expires": 0.0}


def _parse_graph_dt(node):
    """Parse Graph's {'dateTime': ..., 'timeZone': ...} into aware UTC.
    Returns None if anything is off — callers must treat None as 'skip',
    which keeps the gate fail-closed."""
    if not node:
        return None
    raw = node.get("dateTime")
    if not raw:
        return None
    tz_name = node.get("timeZone") or "UTC"
    tz_name = _WINDOWS_TZ.get(tz_name, tz_name)
    try:
        import pytz
        from dateutil import parser as date_parser

        dt = date_parser.parse(raw)
        if dt.tzinfo is None:
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                # Unknown timezone: refuse to guess. Skipping the event is the
                # safe direction (it can only keep the location hidden).
                logging.warning(f"trip_window: unknown timeZone '{tz_name}' — skipping event")
                return None
            dt = tz.localize(dt)
        return dt.astimezone(pytz.UTC)
    except Exception as e:
        logging.warning(f"trip_window: unparseable event time {raw!r}: {e}")
        return None


def _compute_active(now):
    """Uncached truth: is a booking window covering `now`? Raises on Graph failure."""
    from services.graph import GraphClient

    # Query wide enough to catch a long trip that began before `now`, but not so
    # wide that we page. Bookings are hours, not days.
    events = GraphClient().get_calendar_view(
        now - timedelta(hours=12),
        now + timedelta(hours=12),
        top=50,
    )

    for ev in events or []:
        subject = (ev.get("subject") or "").strip()
        # Rule 2: only real bookings unlock the map.
        if not subject.lower().startswith("booking:"):
            continue

        start = _parse_graph_dt(ev.get("start"))
        end = _parse_graph_dt(ev.get("end"))
        if start is None or end is None:
            continue  # fail-closed: can't trust it, don't count it

        if (start - timedelta(minutes=LEAD_MINUTES)) <= now <= (end + timedelta(minutes=TRAIL_MINUTES)):
            return True

    return False


def is_trip_active(now=None, use_cache=True):
    """True only when a real booking window (± lead/trail buffers) covers now.

    Fail-closed: returns False on any error. False => location stays private.
    """
    now = now or datetime.now(timezone.utc)
    clock = time.time()

    if use_cache and _cache["value"] is not None and clock < _cache["expires"]:
        return _cache["value"]

    try:
        active = _compute_active(now)
        if use_cache:
            _cache["value"] = active
            _cache["expires"] = clock + CACHE_TTL_SEC
        return active
    except Exception as e:
        # Graph down / token failure / network timeout -> hide the location.
        logging.warning(f"trip_window: lookup failed, failing closed (privacy on): {e}")
        if use_cache:
            _cache["value"] = False
            _cache["expires"] = clock + CACHE_TTL_FAILURE_SEC
        return False


def _reset_cache_for_tests():
    _cache["value"] = None
    _cache["expires"] = 0.0
