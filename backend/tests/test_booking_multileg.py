"""
Multi-leg routes: order is load-bearing.

A trip is [pickup, ...stops, finalDropoff], and the sequence IS the trip. These
tests follow that sequence through every layer it has to survive — the two
booking paths, Stripe metadata, the Graph payload, and both receipts — because
a reordering failure is silent everywhere: the booking succeeds, the calendar
event looks plausible, the receipt lists the right places. The only symptom is
a driver arriving somewhere in the wrong order.

The paid and unpaid paths are separate implementations that have drifted
before, so several tests here assert they agree rather than testing each alone.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import azure.functions as func  # noqa: E402

from services.bookings import (  # noqa: E402
    MAX_METADATA_STOPS, decode_route_metadata, encode_route_metadata,
    render_route_rows,
)

ROUTE = ["Dry cleaner, Colorado Springs", "Bank, Colorado Springs",
         "Pharmacy, Colorado Springs"]


# ── recording stubs ──────────────────────────────────────────────────────────
class _RecordingDb:
    calls = []

    def create_cabin_token(self, booking_id, valid_hours=None, expires_at=None,
                           flight_number=None, expected_dest=None):
        _RecordingDb.calls.append({"flight_number": flight_number,
                                   "expected_dest": expected_dest})
        return "123456"

    def save_trip(self, *a, **k):
        return True

    def set_payment_status(self, *a, **k):
        return True


class _RecordingBookings:
    calls = []

    def create_appointment(self, customer_data, start_dt, end_dt, service_id,
                           transaction_id=None):
        _RecordingBookings.calls.append(customer_data)
        return {"id": "evt-1"}


class _SilentGraph:
    def send_mail(self, *a, **k):
        return True


def _reset():
    _RecordingDb.calls = []
    _RecordingBookings.calls = []


def _patch_common(monkeypatch):
    import api.bookings as bookings_api
    import services.bookings as bookings_service
    monkeypatch.setattr(bookings_api, "DatabaseClient", _RecordingDb)
    monkeypatch.setattr(bookings_api, "GraphClient", _SilentGraph)
    monkeypatch.setattr(bookings_api, "create_stripe_payment_link", lambda *a, **k: None)
    monkeypatch.setattr(bookings_service, "BookingsClient", _RecordingBookings)
    push = types.ModuleType("services.push_sender")
    push.notify_driver = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "services.push_sender", push)
    return bookings_api


def _post(body):
    return func.HttpRequest(
        method="POST", url="/api/book",
        headers={"Content-Type": "application/json"},
        body=json.dumps(body).encode("utf-8"))


BASE = {
    "customerName": "Ada Lovelace",
    "customerEmail": "ada@example.com",
    "pickup": "Home, Colorado Springs",
    "dropoff": "Airport, Colorado Springs",
    "price": "$85.00",
    "appointmentStart": "2026-08-01T21:00:00Z",
    "paymentMethod": "Invoice",
}


# ── Stripe metadata codec ────────────────────────────────────────────────────
class TestRouteMetadata:
    def test_round_trips_in_order(self):
        encoded = encode_route_metadata(ROUTE)
        assert decode_route_metadata(encoded) == ROUTE

    def test_the_index_carries_the_order(self):
        encoded = encode_route_metadata(ROUTE)
        assert encoded["stop0"] == ROUTE[0]
        assert encoded["stop2"] == ROUTE[2]

    def test_decoding_ignores_dict_ordering(self):
        # Stripe returns metadata as an unordered mapping. Reading by index
        # rather than by iteration is what stops a customer's itinerary from
        # depending on dict order.
        shuffled = {"stop2": "C", "stop0": "A", "stop1": "B",
                    "pickup": "Home", "flightNumber": "UA1"}
        assert decode_route_metadata(shuffled) == ["A", "B", "C"]

    def test_decoding_stops_at_the_first_gap(self):
        # A missing index means the route ended, not that a leg is skippable —
        # silently closing a gap would reorder the remaining stops.
        assert decode_route_metadata({"stop0": "A", "stop2": "C"}) == ["A"]

    def test_no_stops_is_empty_both_ways(self):
        assert encode_route_metadata(None) == {}
        assert encode_route_metadata([]) == {}
        assert decode_route_metadata({}) == []
        assert decode_route_metadata(None) == []

    def test_blank_entries_are_dropped_before_encoding(self):
        assert decode_route_metadata(encode_route_metadata(["A", "  ", "B"])) \
            == ["A", "B"]

    def test_the_cap_is_enforced(self):
        many = [f"Stop {i}" for i in range(MAX_METADATA_STOPS + 4)]
        assert len(encode_route_metadata(many)) == MAX_METADATA_STOPS

    def test_values_stay_under_the_stripe_limit(self):
        # Stripe caps a metadata value at 500 characters and truncates
        # silently; an over-length address must be cut here, where we control
        # it, not there.
        encoded = encode_route_metadata(["x" * 900])
        assert all(len(v) <= 480 for v in encoded.values())

    def test_a_repeated_address_survives(self):
        assert decode_route_metadata(encode_route_metadata(["Bank", "Home", "Bank"])) \
            == ["Bank", "Home", "Bank"]


# ── unpaid path ──────────────────────────────────────────────────────────────
class TestUnpaidPath:
    def test_stops_reach_the_calendar_in_order(self, monkeypatch):
        _reset()
        api = _patch_common(monkeypatch)
        api.book(_post({**BASE, "stops": ROUTE}))
        assert _RecordingBookings.calls[0]["stops"] == ROUTE

    def test_the_return_leg_reverses_the_stops(self, monkeypatch):
        # The way back retraces the outbound. Reusing the outbound order would
        # zig-zag across town.
        _reset()
        api = _patch_common(monkeypatch)
        api.book(_post({**BASE, "stops": ROUTE,
                        "returnStart": "2026-08-02T15:00:00Z"}))
        outbound, ret = _RecordingBookings.calls[0], _RecordingBookings.calls[1]
        assert outbound["stops"] == ROUTE
        assert ret["stops"] == list(reversed(ROUTE))
        # ...and the endpoints swap too.
        assert ret["pickup"] == outbound["dropoff"]

    def test_blank_stops_are_dropped_not_forwarded(self, monkeypatch):
        _reset()
        api = _patch_common(monkeypatch)
        api.book(_post({**BASE, "stops": ["A", "   ", "", "B"]}))
        assert _RecordingBookings.calls[0]["stops"] == ["A", "B"]

    def test_a_plain_trip_sends_no_stops(self, monkeypatch):
        # The regression that matters: an A-to-B booking must behave exactly
        # as it did before multi-leg existed.
        _reset()
        api = _patch_common(monkeypatch)
        api.book(_post(BASE))
        assert _RecordingBookings.calls[0]["stops"] == []


# ── paid path ────────────────────────────────────────────────────────────────
class _FakeSession:
    id = "cs_test_ABC12345"
    amount_total = 8500


PAID_META = {
    "customerName": "Ada Lovelace",
    "customerEmail": "ada@example.com",
    "pickup": "Home, Colorado Springs",
    "dropoff": "Airport, Colorado Springs",
    "appointmentStart": "2026-08-01T21:00:00Z",
}


class TestPaidPath:
    def test_checkout_writes_numbered_metadata_keys(self, monkeypatch):
        import stripe
        import api.checkout as checkout
        captured = {}

        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
        monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(
            lambda **kw: (captured.update(kw),
                          types.SimpleNamespace(id="cs_1", url="https://x"))[1]))

        checkout.create_checkout_session(func.HttpRequest(
            method="POST", url="/api/create-checkout-session",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "pickup": "Home", "dropoff": "Airport", "stops": ROUTE,
                "price": "$85.00", "appointmentStart": "2026-08-01T21:00:00Z",
                "successUrl": "https://x/s", "cancelUrl": "https://x/c",
            }).encode("utf-8")))

        meta = captured["metadata"]
        assert meta["stop0"] == ROUTE[0]
        assert meta["stop2"] == ROUTE[2]
        assert decode_route_metadata(meta) == ROUTE

    def test_finalize_rebuilds_the_route_in_order(self, monkeypatch):
        import services.finalize_service as fin
        captured = {}

        class _Bookings:
            def create_appointment(self, customer_data, **kw):
                captured.setdefault("calls", []).append(customer_data)
                return {"id": "evt-1"}

        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
        monkeypatch.setattr("services.bookings.BookingsClient", _Bookings)
        monkeypatch.setattr(fin, "_claim_session", lambda s: True)
        monkeypatch.setattr(fin, "_release_claim", lambda s: None)
        monkeypatch.setattr(fin, "_send_paid_receipt", lambda s, m: None)
        monkeypatch.setattr(fin, "_log_trip", lambda s, m: None)

        meta = {**PAID_META, **encode_route_metadata(ROUTE)}
        session = types.SimpleNamespace(
            id="cs_1", amount_total=8500, payment_status="paid", metadata=meta)
        monkeypatch.setattr("stripe.checkout.Session.retrieve",
                            staticmethod(lambda *a, **k: session))
        monkeypatch.setattr("stripe.checkout.Session.modify",
                            staticmethod(lambda *a, **k: None))

        fin.finalize_stripe_session("cs_1")
        assert captured["calls"][0]["stops"] == ROUTE


# ── the two paths must agree ─────────────────────────────────────────────────
def test_both_receipts_render_the_same_route(monkeypatch):
    """One renderer, used by both. A customer whose receipt lists stops in a
    different order from the driver's calendar can't tell which is real."""
    rows = render_route_rows("Home", ROUTE, "Airport")
    # Order is positional in the output, so assert on relative position.
    positions = [rows.index(leg) for leg in ["Home", *ROUTE, "Airport"]]
    assert positions == sorted(positions), "receipt rows must follow travel order"
    assert "Stop 1" in rows and "Stop 3" in rows
    assert "Final Drop-off" in rows


def test_a_plain_receipt_is_unchanged():
    # No stops: the original two-row layout, so an A-to-B receipt looks
    # exactly as it always has.
    rows = render_route_rows("Home", [], "Airport")
    assert "Pickup Location" in rows and "Dropoff Location" in rows
    assert "Stop 1" not in rows


# ── Graph payload ────────────────────────────────────────────────────────────
class TestGraphPayload:
    def test_the_event_carries_an_ordered_locations_array(self, monkeypatch):
        # Graph's Event resource has an ORDERED `locations` array alongside the
        # singular `location`. Sending it keeps the sequence as structured
        # data instead of leaving it to be re-read out of the body prose.
        from services.graph import GraphClient
        captured = {}

        class _Resp:
            ok = True
            status_code = 200
            text = "{}"

            @staticmethod
            def json():
                return {"id": "evt-1"}

        for var in ("OAUTH_TENANT_ID", "OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET"):
            monkeypatch.setenv(var, "test-not-real")
        monkeypatch.setattr(GraphClient, "_get_token", lambda self: "t")
        monkeypatch.setattr("services.graph.requests.post",
                            lambda url, headers=None, json=None, timeout=None:
                            (captured.update(json), _Resp())[1])

        from datetime import datetime, timezone
        GraphClient().create_calendar_event(
            subject="s", body="b",
            start_dt=datetime(2026, 8, 1, 21, tzinfo=timezone.utc),
            end_dt=datetime(2026, 8, 1, 22, tzinfo=timezone.utc),
            location="Home", attendee_email=None,
            locations=["Home", *ROUTE, "Airport"])

        names = [l["displayName"] for l in captured["locations"]]
        assert names == ["Home", *ROUTE, "Airport"]

    def test_a_plain_trip_sends_no_locations_array(self, monkeypatch):
        from services.graph import GraphClient
        captured = {}

        class _Resp:
            ok = True
            status_code = 200
            text = "{}"

            @staticmethod
            def json():
                return {"id": "evt-1"}

        for var in ("OAUTH_TENANT_ID", "OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET"):
            monkeypatch.setenv(var, "test-not-real")
        monkeypatch.setattr(GraphClient, "_get_token", lambda self: "t")
        monkeypatch.setattr("services.graph.requests.post",
                            lambda url, headers=None, json=None, timeout=None:
                            (captured.update(json), _Resp())[1])

        from datetime import datetime, timezone
        GraphClient().create_calendar_event(
            subject="s", body="b",
            start_dt=datetime(2026, 8, 1, 21, tzinfo=timezone.utc),
            end_dt=datetime(2026, 8, 1, 22, tzinfo=timezone.utc),
            location="Home", attendee_email=None)

        assert "locations" not in captured

    def test_the_body_lists_the_route_in_order(self, monkeypatch):
        import services.bookings as bookings_service
        captured = {}

        class _Graph:
            def create_calendar_event(self, **kw):
                captured.update(kw)
                return {"id": "evt-1"}

        client = bookings_service.BookingsClient.__new__(bookings_service.BookingsClient)
        client.graph = _Graph()
        client.business_id = None

        from datetime import datetime, timezone
        client.create_appointment(
            customer_data={"name": "Ada", "pickup": "Home",
                           "dropoff": "Airport", "stops": ROUTE},
            start_dt=datetime(2026, 8, 1, 21, tzinfo=timezone.utc),
            end_dt=datetime(2026, 8, 1, 22, tzinfo=timezone.utc),
            service_id="svc")

        body = captured["body"]
        assert "<ol>" in body
        positions = [body.index(leg) for leg in ["Home", *ROUTE, "Airport"]]
        assert positions == sorted(positions), "body must list legs in travel order"
        assert captured["locations"] == ["Home", *ROUTE, "Airport"]
