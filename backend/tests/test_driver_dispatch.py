"""
Tests for the driver ETA / dispatch summary (services/tessie.py::get_driver_dispatch).

This powers the arrival hand-off card ("Thor is on the way, ~9 min"). The ETA is
Tesla's own traffic-aware figure from the car's active navigation route, so no
routing API call is involved.

SECURITY: the nav route also carries the destination NAME and COORDINATES —
a customer's drop-off address. The tests below pin that those never appear in
the returned payload, so a future refactor can't start leaking them.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TESSIE_API_KEY", "test-key-not-real")

from services.tessie import TessieClient  # noqa: E402

# Colorado Springs Airport, and a private drop-off ~9 miles away.
COS_LAT, COS_LON = 38.8058, -104.7008
PRIVATE_LAT, PRIVATE_LON = 38.8339, -104.7747


def _client(drive_state):
    c = TessieClient()
    c.get_vehicle_state = lambda vin: {"drive_state": drive_state}
    return c


def _nav(dest_lat, dest_lon, eta=9.0, delay=0, shift="D"):
    """A drive_state with an active route, shaped like Tessie's real response."""
    return {
        "latitude": 38.85, "longitude": -104.79, "heading": 180,
        "speed": 32, "shift_state": shift,
        "active_route_destination": "Emerson - Private 1",   # PII — must not leak
        "active_route_latitude": dest_lat,                    # PII — must not leak
        "active_route_longitude": dest_lon,                   # PII — must not leak
        "active_route_minutes_to_arrival": eta,
        "active_route_miles_to_arrival": 2.22,
        "active_route_traffic_minutes_delay": delay,
    }


# ── privacy invariants ───────────────────────────────────────────────────────
def test_never_leaks_destination_name_or_coords():
    d = _client(_nav(COS_LAT, COS_LON)).get_driver_dispatch("VIN", COS_LAT, COS_LON)
    blob = repr(d)
    assert "Emerson" not in blob, "destination NAME leaked into the payload"
    for banned in ("active_route_destination", "active_route_latitude",
                   "active_route_longitude", "destination"):
        assert banned not in d, f"{banned} leaked into the payload"
    # Destination coordinates must not appear under any key.
    for v in d.values():
        assert v not in (COS_LON, PRIVATE_LAT, PRIVATE_LON)
    assert set(d.keys()) == {"dispatched", "eta_minutes", "traffic_delay_minutes",
                             "heading_to_expected", "moving"}


# ── dispatch + ETA ───────────────────────────────────────────────────────────
def test_reports_eta_when_route_active():
    d = _client(_nav(COS_LAT, COS_LON, eta=8.6, delay=2)).get_driver_dispatch("VIN")
    assert d["dispatched"] is True
    assert d["eta_minutes"] == 9          # rounded — no false precision
    assert d["traffic_delay_minutes"] == 2
    assert d["moving"] is True


def test_not_dispatched_without_active_route():
    # Car awake and parked, no nav set -> the card must fall back to
    # "being dispatched" rather than promise a number.
    d = _client({"latitude": 38.85, "longitude": -104.79,
                 "shift_state": None, "speed": 0}).get_driver_dispatch("VIN")
    assert d["dispatched"] is False
    assert d["eta_minutes"] is None
    assert d["moving"] is False


def test_heading_to_expected_true_at_airport():
    d = _client(_nav(COS_LAT, COS_LON)).get_driver_dispatch("VIN", COS_LAT, COS_LON)
    assert d["heading_to_expected"] is True


def test_heading_to_expected_false_for_other_destination():
    # Nav set to a private address ~9 mi from the airport: the driver is busy
    # with a different job, so we must not announce him for this arrival.
    d = _client(_nav(PRIVATE_LAT, PRIVATE_LON)).get_driver_dispatch("VIN", COS_LAT, COS_LON)
    assert d["heading_to_expected"] is False


def test_heading_unknown_without_expected_point():
    d = _client(_nav(COS_LAT, COS_LON)).get_driver_dispatch("VIN")
    assert d["heading_to_expected"] is None   # unknown, not False


def test_unreachable_vehicle_returns_none():
    c = TessieClient()
    c.get_vehicle_state = lambda vin: None
    assert c.get_driver_dispatch("VIN") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
