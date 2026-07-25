"""
Tests for FlightAware canonical resolution + destination guard
(services/flightaware.py::FlightAwareClient.flight_info).

These pin the fix for the "wrong flight" bug: AeroAPI's /flights/{ident} returns
an ARRAY of legs across multiple days AND destinations, so the old phase-only
selection could resolve SWA250 to the wrong leg. The client now canonical-
resolves the ident (IATA->ICAO) and guards the destination.

The HTTP layer is mocked — no network, no billing, no real key.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Client reads the key via SecretManager; KEYVAULT_URL is unset in tests so it
# falls back to this env var.
os.environ["FLIGHTAWARE_API_KEY"] = "test-key-not-real"

from services.flightaware import FlightAwareClient  # noqa: E402


def _airport(iata):
    return {"code_iata": iata, "code_icao": "K" + iata, "code_lid": None,
            "code": "K" + iata, "city": iata}


def _leg(origin, dest, sched_out, progress=0, actual_out=None, cancelled=False, fa_id=None):
    return {
        "fa_flight_id": fa_id or f"SWA250-{sched_out}",
        "ident": "SWA250", "ident_iata": "WN250", "ident_icao": "SWA250",
        "operator": "SWA", "origin": _airport(origin), "destination": _airport(dest),
        "scheduled_out": sched_out, "estimated_out": sched_out, "actual_out": actual_out,
        "scheduled_in": sched_out, "estimated_in": sched_out,
        "progress_percent": progress, "cancelled": cancelled,
    }


def _swa250_array():
    # Australia-bound leg FIRST (the decoy the old logic could pick), plus the
    # real COS->DAL pickup and other-day DAL legs. All not-yet-departed.
    return [
        _leg("SYD", "MEL", "2026-07-27T18:20:00Z", fa_id="wrong-australia"),
        _leg("COS", "DAL", "2026-07-25T11:00:00Z", fa_id="right-cos-dal"),
        _leg("COS", "DAL", "2026-07-24T11:00:00Z", actual_out="2026-07-24T11:05:00Z", fa_id="dal-yesterday"),
        _leg("COS", "DAL", "2026-07-26T11:00:00Z", fa_id="dal-tomorrow"),
    ]


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


# ── destination guard ────────────────────────────────────────────────────────
def test_guard_accepts_dal_over_array_order():
    c = _client_with(_swa250_array())
    f = c.flight_info("SWA250", expected_destination="DAL", when="2026-07-25T10:00:00Z")
    assert f is not None
    assert f["destination"]["code_iata"] == "DAL"
    assert f["origin"]["code_iata"] == "COS"
    assert f["fa_flight_id"] == "right-cos-dal"  # NOT the SYD decoy at index 0


def test_guard_rejects_unmatched_destination():
    c = _client_with(_swa250_array())
    # No SWA250 leg arrives at JFK -> refuse to return a guessed flight.
    assert c.flight_info("SWA250", expected_destination="JFK") is None


def test_guard_accepts_icao_form():
    c = _client_with(_swa250_array())
    f = c.flight_info("SWA250", expected_destination="KDAL", when="2026-07-25T10:00:00Z")
    assert f is not None and f["destination"]["code_iata"] == "DAL"


# ── canonical resolution ─────────────────────────────────────────────────────
def test_canonical_maps_iata_to_icao():
    c = _client_with(_swa250_array(),
                     canonical_idents=[{"ident": "SWA250", "ident_type": "designator"}])
    f = c.flight_info("WN250", expected_destination="DAL",
                      when="2026-07-25T10:00:00Z", dest_country="US")
    assert f is not None
    # First call canonicalizes WN250 and forwards country_code=US.
    canon_path, canon_params = c._calls[0]
    assert canon_path == "/flights/WN250/canonical"
    assert canon_params.get("country_code") == "US"
    # The status call then uses the canonical SWA250 ident.
    assert c._calls[1][0] == "/flights/SWA250"


def test_canonical_falls_back_to_input_when_empty():
    c = _client_with(_swa250_array(), canonical_idents=[])
    f = c.flight_info("SWA250", expected_destination="DAL", when="2026-07-25T10:00:00Z")
    assert f is not None and c._calls[1][0] == "/flights/SWA250"


# ── array / day selection ────────────────────────────────────────────────────
def test_selects_leg_nearest_booking_date():
    c = _client_with(_swa250_array())
    f = c.flight_info("SWA250", expected_destination="DAL", when="2026-07-26T10:30:00Z")
    assert f["fa_flight_id"] == "dal-tomorrow"


def test_in_progress_leg_preferred():
    flights = [
        _leg("COS", "DAL", "2026-07-25T11:00:00Z", progress=0, fa_id="scheduled"),
        _leg("COS", "DAL", "2026-07-25T09:00:00Z", progress=55,
             actual_out="2026-07-25T09:05:00Z", fa_id="airborne"),
    ]
    c = _client_with(flights)
    f = c.flight_info("SWA250", expected_destination="DAL", when="2026-07-25T11:00:00Z")
    assert f["fa_flight_id"] == "airborne"


def test_unknown_ident_returns_none():
    c = _client_with([])
    assert c.flight_info("SWA250", expected_destination="DAL") is None


def test_bare_lookup_still_returns_a_leg():
    # No expected_destination: keeps working (now canonical + nearest-time).
    c = _client_with(_swa250_array())
    f = c.flight_info("SWA250", when="2026-07-25T10:00:00Z")
    assert f is not None
    assert f["fa_flight_id"] == "right-cos-dal"  # nearest to the given time


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
