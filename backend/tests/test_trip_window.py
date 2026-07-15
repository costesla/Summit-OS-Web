"""
Tests for the trip-window privacy gate.

This is a security control: a False here keeps the owner's live location
private. The tests below pin the fail-closed behaviour so a future refactor
can't silently start broadcasting.
"""
import sys
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import trip_window  # noqa: E402
from services.trip_window import is_trip_active  # noqa: E402

NOW = datetime(2026, 7, 14, 19, 0, 0, tzinfo=timezone.utc)  # 1pm Mountain


def _event(subject, start_utc, end_utc):
    """Graph-shaped event. Times as naive Mountain strings + timeZone, which
    is what get_calendar_view actually returns (Prefer: America/Denver)."""
    import pytz

    mt = pytz.timezone("America/Denver")
    return {
        "subject": subject,
        "start": {"dateTime": start_utc.astimezone(mt).replace(tzinfo=None).isoformat(), "timeZone": "America/Denver"},
        "end": {"dateTime": end_utc.astimezone(mt).replace(tzinfo=None).isoformat(), "timeZone": "America/Denver"},
    }


def setup_function():
    trip_window._reset_cache_for_tests()


@contextmanager
def _with_events(events):
    """GraphClient.__init__ raises without real creds, so stub it out too —
    otherwise we'd only ever be testing the missing-credentials path."""
    with patch("services.graph.GraphClient.__init__", return_value=None), patch(
        "services.graph.GraphClient.get_calendar_view", return_value=events
    ):
        yield


@contextmanager
def _graph_raises(exc):
    with patch("services.graph.GraphClient.__init__", return_value=None), patch(
        "services.graph.GraphClient.get_calendar_view", side_effect=exc
    ):
        yield


def _no_graph_creds():
    # GraphClient.__init__ raises when creds are missing — must fail closed.
    return patch("services.graph.GraphClient.__init__", side_effect=Exception("Missing creds"))


# ── The gate opens only for a real, current booking ──────────────────────

def test_active_booking_opens_the_gate():
    with _with_events([_event("Booking: Jane Doe", NOW - timedelta(minutes=10), NOW + timedelta(minutes=40))]):
        assert is_trip_active(NOW, use_cache=False) is True


def test_en_route_lead_window_opens_the_gate():
    # Pickup is 20 min out; LEAD_MINUTES=30 means we're en route.
    with _with_events([_event("Booking: Jane Doe", NOW + timedelta(minutes=20), NOW + timedelta(minutes=80))]):
        assert is_trip_active(NOW, use_cache=False) is True


def test_trailing_window_opens_the_gate():
    # Trip ended 10 min ago; TRAIL_MINUTES=30 covers wrap-up.
    with _with_events([_event("Booking: Jane Doe", NOW - timedelta(minutes=70), NOW - timedelta(minutes=10))]):
        assert is_trip_active(NOW, use_cache=False) is True


# ── Everything else keeps the location private ───────────────────────────

def test_no_events_stays_private():
    with _with_events([]):
        assert is_trip_active(NOW, use_cache=False) is False


def test_booking_far_in_the_future_stays_private():
    with _with_events([_event("Booking: Jane Doe", NOW + timedelta(hours=5), NOW + timedelta(hours=6))]):
        assert is_trip_active(NOW, use_cache=False) is False


def test_finished_booking_stays_private():
    with _with_events([_event("Booking: Jane Doe", NOW - timedelta(hours=4), NOW - timedelta(hours=3))]):
        assert is_trip_active(NOW, use_cache=False) is False


def test_personal_calendar_event_never_unlocks_location():
    """The whole point: a dentist appointment is not a trip."""
    with _with_events([
        _event("Dentist", NOW - timedelta(minutes=10), NOW + timedelta(minutes=40)),
        _event("Lunch with Terrance", NOW - timedelta(minutes=5), NOW + timedelta(minutes=25)),
    ]):
        assert is_trip_active(NOW, use_cache=False) is False


# ── Fail-closed ──────────────────────────────────────────────────────────

def test_graph_error_fails_closed():
    with _graph_raises(Exception("Graph 503")):
        assert is_trip_active(NOW, use_cache=False) is False


def test_graph_timeout_fails_closed():
    with _graph_raises(TimeoutError("timed out")):
        assert is_trip_active(NOW, use_cache=False) is False


def test_missing_credentials_fails_closed():
    with _no_graph_creds():
        assert is_trip_active(NOW, use_cache=False) is False


def test_unparseable_event_time_fails_closed():
    with _with_events([{"subject": "Booking: Jane", "start": {"dateTime": "not-a-date"}, "end": None}]):
        assert is_trip_active(NOW, use_cache=False) is False


def test_unknown_timezone_fails_closed():
    """Refuse to guess a timezone — guessing wrong could expose a location."""
    with _with_events([{
        "subject": "Booking: Jane",
        "start": {"dateTime": "2026-07-14T12:50:00", "timeZone": "Narnia/Standard Time"},
        "end": {"dateTime": "2026-07-14T13:50:00", "timeZone": "Narnia/Standard Time"},
    }]):
        assert is_trip_active(NOW, use_cache=False) is False


# ── Cache ────────────────────────────────────────────────────────────────

def test_cache_prevents_hammering_graph():
    events = [_event("Booking: Jane Doe", NOW - timedelta(minutes=10), NOW + timedelta(minutes=40))]
    with patch("services.graph.GraphClient.__init__", return_value=None), patch(
        "services.graph.GraphClient.get_calendar_view", return_value=events
    ) as spy:
        assert is_trip_active(NOW) is True
        assert is_trip_active(NOW) is True
        assert is_trip_active(NOW) is True
        assert spy.call_count == 1, "expected the 60s cache to collapse repeat polls into one Graph call"
