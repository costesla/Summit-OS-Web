"""
Tests for FlightAware canonical resolution + destination guard + leg selection
(services/flightaware.py::FlightAwareClient.flight_info).

Pins the fix for the "wrong flight" bug: AeroAPI's /flights/{ident} returns an
ARRAY of legs across multiple days AND destinations for one flight number, so the
old phase-only selection could resolve SWA250/WN250 to the wrong leg (e.g. a
future MCO->SJU leg instead of the flight that just departed). The client now
canonical-resolves the ident (IATA->ICAO), guards the destination when one is
expected, and for a bare lookup prefers the leg active right now.

The HTTP layer is mocked — no network, no billing, no real key.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Client reads the key via SecretManager; KEYVAULT_URL is unset in tests so it
# falls back to this env var.
os.environ["FLIGHTAWARE_API_KEY"] = "test-key-not-real"

from services.flightaware import FlightAwareClient  # noqa: E402

# A fixed "now" so time-relative tests are deterministic, and ISO stamps built
# around it.
NOW = 1_769_000_000.0  # arbitrary fixed epoch


def _iso(offset_hours):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW + offset_hours * 3600))


def _airport(iata):
    return {"code_iata": iata, "code_icao": "K" + iata, "code_lid": None,
            "code": "K" + iata, "city": iata}


def _leg(origin, dest, sched_out_h, state="scheduled", fa_id=None):
    """state: 'scheduled' (future, not departed), 'active' (departed, flying),
    'arrived' (completed)."""
    f = {
        "fa_flight_id": fa_id or f"{origin}{dest}-{sched_out_h}",
        "ident": "SWA250", "ident_iata": "WN250", "ident_icao": "SWA250",
        "operator": "SWA", "origin": _airport(origin), "destination": _airport(dest),
        "scheduled_out": _iso(sched_out_h), "estimated_out": _iso(sched_out_h),
        "scheduled_in": _iso(sched_out_h + 2), "estimated_in": _iso(sched_out_h + 2),
        "actual_out": None, "actual_in": None, "progress_percent": 0,
        "status": "Scheduled", "cancelled": False,
    }
    if state == "active":
        f.update(actual_out=_iso(sched_out_h), progress_percent=0, status="Taxiing / Left Gate")
    elif state == "arrived":
        f.update(actual_out=_iso(sched_out_h), actual_in=_iso(sched_out_h + 2),
                 progress_percent=100, status="Arrived / Gate Arrival")
    return f


def _client_with(flights, canonical_idents=None):
    """A FlightAwareClient whose _get is faked to route canonical vs /flights."""
    FlightAwareClient._cache.clear()
    FlightAwareClient.MIN_INTERVAL_SEC = 0
    c = FlightAwareClient()
    calls = []

    def fake_get(path, params, cache_ttl=None):
        calls.append((path, params or {}))
        if path.endswith("/canonical"):
            idents = (canonical_idents if canonical_idents is not None
                      else [{"ident": "SWA250", "ident_type": "designator"}])
            return {"idents": idents}
        return {"flights": flights}

    c._get = fake_get
    c._calls = calls
    return c


# Realistic WN250: the COS->DAL leg just departed (active now); other legs are
# either days in the future or already arrived.
def _wn250_now():
    return [
        _leg("AUS", "AMA", 55, "scheduled", fa_id="ama-future"),
        _leg("MCO", "SJU", 38, "scheduled", fa_id="sju-future"),
        _leg("COS", "DAL", -0.1, "active", fa_id="dal-now"),        # departed 6 min ago
        _leg("AUS", "AMA", -17, "arrived", fa_id="ama-yesterday"),
        _leg("COS", "DAL", -168, "arrived", fa_id="dal-lastweek"),
    ]


# ── the WN250 bug: bare lookup must pick the flight active right now ──────────
def test_bare_lookup_prefers_active_flight_over_future_leg():
    c = _client_with(_wn250_now())
    # Force the client's "now" to match the fixture's now.
    _orig = time.time
    time.time = lambda: NOW
    try:
        f = c.flight_info("WN250")
    finally:
        time.time = _orig
    assert f is not None
    assert f["fa_flight_id"] == "dal-now"          # NOT sju-future / ama-future
    assert f["destination"]["code_iata"] == "DAL"


def test_bare_lookup_nearest_when_none_active():
    # All legs scheduled/arrived, none active -> nearest scheduled to now.
    flights = [
        _leg("AUS", "AMA", 55, "scheduled", fa_id="ama-far"),
        _leg("COS", "DAL", 1.5, "scheduled", fa_id="dal-soon"),
        _leg("MCO", "SJU", -170, "arrived", fa_id="sju-old"),
    ]
    c = _client_with(flights)
    _orig = time.time
    time.time = lambda: NOW
    try:
        f = c.flight_info("WN250")
    finally:
        time.time = _orig
    assert f["fa_flight_id"] == "dal-soon"


# ── destination guard ────────────────────────────────────────────────────────
def test_guard_accepts_dal_over_array_order():
    c = _client_with(_wn250_now())
    f = c.flight_info("SWA250", expected_destination="DAL", when=_iso(0))
    assert f is not None
    assert f["destination"]["code_iata"] == "DAL"
    assert f["origin"]["code_iata"] == "COS"


def test_guard_rejects_unmatched_destination():
    c = _client_with(_wn250_now())
    assert c.flight_info("SWA250", expected_destination="JFK") is None


def test_guard_accepts_icao_form():
    c = _client_with(_wn250_now())
    f = c.flight_info("SWA250", expected_destination="KDAL", when=_iso(0))
    assert f is not None and f["destination"]["code_iata"] == "DAL"


# ── canonical resolution ─────────────────────────────────────────────────────
def test_canonical_maps_iata_to_icao():
    c = _client_with(_wn250_now(),
                     canonical_idents=[{"ident": "SWA250", "ident_type": "designator"}])
    f = c.flight_info("WN250", expected_destination="DAL", when=_iso(0), dest_country="US")
    assert f is not None
    canon_path, canon_params = c._calls[0]
    assert canon_path == "/flights/WN250/canonical"
    assert canon_params.get("country_code") == "US"
    assert c._calls[1][0] == "/flights/SWA250"


def test_canonical_falls_back_to_input_when_empty():
    c = _client_with(_wn250_now(), canonical_idents=[])
    f = c.flight_info("SWA250", expected_destination="DAL", when=_iso(0))
    assert f is not None and c._calls[1][0] == "/flights/SWA250"


# ── array / day selection with an explicit booking time ──────────────────────
def test_selects_dal_leg_nearest_booking_time():
    flights = [
        _leg("COS", "DAL", -168, "arrived", fa_id="dal-lastweek"),
        _leg("COS", "DAL", 24, "scheduled", fa_id="dal-tomorrow"),
        _leg("COS", "DAL", 0.5, "scheduled", fa_id="dal-today"),
        _leg("AUS", "AMA", 1, "scheduled", fa_id="ama"),
    ]
    c = _client_with(flights)
    f = c.flight_info("SWA250", expected_destination="DAL", when=_iso(25))  # ~tomorrow
    assert f["fa_flight_id"] == "dal-tomorrow"


def test_unknown_ident_returns_none():
    c = _client_with([])
    assert c.flight_info("SWA250", expected_destination="DAL") is None


# ── live position (powers the flight map) ────────────────────────────────────
def test_last_position_normalizes_altitude_to_feet():
    c = _client_with([])
    c._get = lambda path, params, cache_ttl=None: {"last_position": {
        "latitude": 3.31, "longitude": -14.24, "altitude": 370,
        "groundspeed": 494, "heading": 128, "timestamp": "2026-07-25T11:24:29Z"}}
    p = c.last_position("DAL200-x")
    assert p["latitude"] == 3.31 and p["longitude"] == -14.24
    assert p["altitude_ft"] == 37000        # flight level 370 -> feet
    assert p["heading_deg"] == 128 and p["ground_speed_kts"] == 494


def test_last_position_none_without_fix():
    c = _client_with([])
    c._get = lambda path, params, cache_ttl=None: {"fa_flight_id": "x"}  # no last_position
    assert c.last_position("x") is None
    assert c.last_position("") is None       # empty id short-circuits


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
