"""
A flight-data provider OUTAGE must not be reported as a bad flight number.

Pins the fix for the August 2026 incident: the AeroAPI subscription lapsed and
every lookup began returning 403 UNAUTHORIZED_USER. Because the provider
methods degrade gracefully (they return None/[] instead of raising),
`/api/flight-status` answered HTTP 200 `{"success": true, "found": false}` for
EVERY flight — and the public tracker rendered that as "No flight found for
that number right now. Double-check the flight number." For roughly a week,
passengers tracking a perfectly valid flight were told they had mistyped it,
and nobody could see the outage from the outside.

The distinction these tests protect:
  - providers ANSWERED and had nothing  -> 200, found:false   (genuine miss)
  - providers FAILED                    -> 503, retryable     (we don't know)

The asymmetry that matters: FlightAware can speak to a flight in any state,
but FR24 only sees aircraft airborne RIGHT NOW. So FR24 finding nothing — or
failing outright — says nothing about a flight that hasn't departed or has
already landed, and must never on its own produce "no such flight".

No network, no billing, no real key.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("FLIGHTAWARE_API_KEY", "test-key-not-real")

import azure.functions as func  # noqa: E402

from services.flight import FlightStatusService, FlightDataUnavailable  # noqa: E402
from services.flightaware import FlightAwareClient, FlightAwareApiError  # noqa: E402

import pytest  # noqa: E402


LAPSED = FlightAwareApiError(403, "FlightAware request failed (HTTP 403).")


# ── fake providers ───────────────────────────────────────────────────────────
def _fa_class(*, info=None, error=None, canonical_error=None, position=None):
    class _FA:
        def __init__(self):
            self.last_error = error
            self.last_canonical_error = canonical_error

        def flight_info(self, ident, **kw):
            return info

        def last_position(self, fa_flight_id, **kw):
            return position

    return _FA


def _fr_class(*, positions=None, error=None):
    class _FR:
        def __init__(self):
            pass

        def live_flight_positions(self, **kw):
            if error is not None:
                raise error
            return list(positions or [])

        def airline_light(self, code, **kw):
            return {"name": "Test Air"}

    return _FR


def _patch(monkeypatch, fa_cls, fr_cls):
    import services.flight as flight_mod
    monkeypatch.setattr(flight_mod, "FlightAwareClient", fa_cls)
    monkeypatch.setattr(flight_mod, "Flightradar24Client", fr_cls)


AIRBORNE = {
    "lat": 38.79, "lon": -104.7, "alt": 38000, "gspeed": 454, "track": 248,
    "orig_iata": "OMA", "dest_iata": "PHX", "type": "B38M",
    "operating_as": "SWA", "eta": "2026-08-04T15:00:16Z",
}

SCHEDULED_LEG = {
    "fa_flight_id": "SKW4677-1", "operator": "SKW",
    "origin": {"code_iata": "COS", "city": "Colorado Springs"},
    "destination": {"code_iata": "DEN", "city": "Denver"},
    "scheduled_in": "2026-08-04T14:52:00Z", "status": "Scheduled",
    "actual_out": None, "actual_in": None, "progress_percent": 0,
}


# ── the incident itself ──────────────────────────────────────────────────────
def test_both_providers_down_raises_rather_than_reporting_not_found(monkeypatch):
    """The exact August 2026 shape: AeroAPI 403 and no live position."""
    _patch(monkeypatch,
           _fa_class(info=None, error=LAPSED),
           _fr_class(positions=[]))
    with pytest.raises(FlightDataUnavailable):
        FlightStatusService().get_flight_status("UA4677")


def test_schedule_provider_down_but_flight_airborne_degrades_not_fails(monkeypatch):
    """FR24 could still see airborne aircraft during the outage — keep serving them."""
    _patch(monkeypatch,
           _fa_class(info=None, error=LAPSED),
           _fr_class(positions=[AIRBORNE]))
    data = FlightStatusService().get_flight_status("WN4835")
    assert data is not None                       # must NOT raise
    assert data["sources"] == {"schedule": None, "live": "FlightRadar24"}
    assert data["live"]["altitude_ft"] == 38000
    assert data["status"] == "En route (live)"


# ── things that are NOT outages ──────────────────────────────────────────────
def test_healthy_providers_with_no_such_flight_still_returns_none(monkeypatch):
    """A genuine miss must stay a genuine miss — 'ZZ9999' really isn't a flight."""
    _patch(monkeypatch,
           _fa_class(info=None, error=None),
           _fr_class(positions=[]))
    assert FlightStatusService().get_flight_status("ZZ9999") is None


def test_fr24_failure_alone_is_not_an_outage(monkeypatch):
    """FR24 only sees airborne traffic; its failure can't prove a flight absent,
    but neither does it make a confident FlightAware 'no such flight' unknown."""
    _patch(monkeypatch,
           _fa_class(info=None, error=None),
           _fr_class(error=RuntimeError("FR24 boom")))
    assert FlightStatusService().get_flight_status("ZZ9999") is None


def test_canonical_blip_alone_is_not_an_outage(monkeypatch):
    """canonical_ident degrades to the input ident and the lookup still runs, so
    a canonical failure followed by a healthy lookup is not a provider outage."""
    _patch(monkeypatch,
           _fa_class(info=None, error=None, canonical_error=LAPSED),
           _fr_class(positions=[]))
    assert FlightStatusService().get_flight_status("WN250") is None


def test_healthy_lookup_returns_data_and_never_raises(monkeypatch):
    _patch(monkeypatch,
           _fa_class(info=SCHEDULED_LEG, error=None),
           _fr_class(positions=[]))
    data = FlightStatusService().get_flight_status("UA4677")
    assert data["sources"]["schedule"] == "FlightAware"
    assert data["origin"]["code"] == "COS"
    assert data["destination"]["code"] == "DEN"


# ── client contract: guard rejection vs real failure ─────────────────────────
def _client(get_impl):
    FlightAwareClient._cache.clear()
    FlightAwareClient.MIN_INTERVAL_SEC = 0
    c = FlightAwareClient()
    c._get = get_impl
    return c


def test_destination_guard_rejection_leaves_last_error_clean():
    """No leg arrives at JFK — a legitimate 'not found', NOT a provider failure."""
    legs = {"flights": [dict(SCHEDULED_LEG)]}

    def fake_get(path, params, cache_ttl=None):
        if path.endswith("/canonical"):
            return {"idents": [{"ident": "SKW4677"}]}
        return legs

    c = _client(fake_get)
    assert c.flight_candidates("UA4677", expected_destination="JFK") == []
    assert c.last_error is None          # the guard fired, nothing broke


def test_lookup_failure_records_last_error():
    def fake_get(path, params, cache_ttl=None):
        raise LAPSED

    c = _client(fake_get)
    assert c.flight_candidates("UA4677") == []
    assert c.last_error is LAPSED


def test_canonical_failure_is_recorded_separately():
    """A canonical blip must not masquerade as a data-bearing call failing."""
    def fake_get(path, params, cache_ttl=None):
        if path.endswith("/canonical"):
            raise LAPSED
        return {"flights": [dict(SCHEDULED_LEG)]}

    c = _client(fake_get)
    assert c.flight_candidates("UA4677") != []
    assert c.last_error is None
    assert c.last_canonical_error is LAPSED


# ── the HTTP contract the frontend depends on ────────────────────────────────
def _req(body):
    return func.HttpRequest(
        method="POST", url="/api/flight-status",
        headers={"Content-Type": "application/json"},
        body=json.dumps(body).encode("utf-8"),
    )


def test_route_answers_503_when_providers_are_down(monkeypatch):
    import api.bookings as bookings_api

    class _Down:
        def get_flight_status(self, *a, **k):
            raise FlightDataUnavailable()

    monkeypatch.setattr(bookings_api, "FlightStatusService", _Down)
    res = bookings_api.flight_status.build().get_user_function()(
        _req({"flightNumber": "UA4677"}))
    body = json.loads(res.get_body())

    assert res.status_code == 503
    assert body["success"] is False
    assert body["retryable"] is True
    # The tracker renders this verbatim — it must not blame the passenger,
    # and it must not leak provider or key state.
    assert "temporarily unavailable" in body["error"].lower()
    for leaked in ("key", "aeroapi", "403", "flightaware"):
        assert leaked not in body["error"].lower()


def test_route_still_answers_200_found_false_for_a_genuine_miss(monkeypatch):
    import api.bookings as bookings_api

    class _Empty:
        def get_flight_status(self, *a, **k):
            return None

    monkeypatch.setattr(bookings_api, "FlightStatusService", _Empty)
    res = bookings_api.flight_status.build().get_user_function()(
        _req({"flightNumber": "ZZ9999"}))
    body = json.loads(res.get_body())

    assert res.status_code == 200
    assert body["success"] is True
    assert body["found"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
