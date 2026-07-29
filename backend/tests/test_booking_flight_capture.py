"""
The booking → cabin-token flight linkage.

`Rides.CabinTokens.FlightNumber` / `.ExpectedDest` have existed and been tested
since the cabin-trip work, but for a long time NOTHING WROTE THEM: both callers
of `create_cabin_token` omitted the arguments, so the columns were always NULL
in production and the arrival console fell back to a hand-appended `?flight=`
URL parameter. These tests exist so that can't silently happen again.

The other thing pinned here is that the two booking paths AGREE. A booking is
written by one of two entirely separate code paths — `/api/book` for
invoice/cash/Venmo, and the Stripe finalize path for paid bookings — and they
have drifted before. If one of them upper-cases the flight and the other
doesn't, the same trip gets a different token depending on how it was paid,
and the failure only shows up as a flight that won't resolve.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import azure.functions as func  # noqa: E402


# ── recording stubs ──────────────────────────────────────────────────────────
class _RecordingDb:
    """Captures the create_cabin_token call and swallows the rest."""
    calls = []

    def create_cabin_token(self, booking_id, valid_hours=None, expires_at=None,
                           flight_number=None, expected_dest=None):
        _RecordingDb.calls.append({
            "booking_id": booking_id,
            "flight_number": flight_number,
            "expected_dest": expected_dest,
        })
        return "123456"

    def save_trip(self, *a, **k):
        return True

    def set_payment_status(self, *a, **k):
        return True


class _RecordingBookings:
    """Captures the calendar appointment so we can read its notes."""
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
    """Neutralise everything the booking flow touches except what we assert on."""
    import api.bookings as bookings_api
    import services.bookings as bookings_service

    monkeypatch.setattr(bookings_api, "DatabaseClient", _RecordingDb)
    monkeypatch.setattr(bookings_api, "GraphClient", _SilentGraph)
    monkeypatch.setattr(bookings_api, "create_stripe_payment_link",
                        lambda *a, **k: None)
    monkeypatch.setattr(bookings_service, "BookingsClient", _RecordingBookings)
    # Imported inside the function body, so it has to exist as a module.
    push = types.ModuleType("services.push_sender")
    push.notify_driver = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "services.push_sender", push)
    return bookings_api


def _post(body: dict) -> func.HttpRequest:
    import json
    return func.HttpRequest(
        method="POST",
        url="/api/book",
        headers={"Content-Type": "application/json"},
        body=json.dumps(body).encode("utf-8"),
    )


BASE_BOOKING = {
    "customerName": "Ada Lovelace",
    "customerEmail": "ada@example.com",
    "customerPhone": "555-0100",
    "pickup": "Colorado Springs Airport, CO",
    "dropoff": "1 Lake Ave, Colorado Springs, CO",
    "price": "$85.00",
    "appointmentStart": "2026-08-01T21:00:00Z",
    "paymentMethod": "Invoice",
}


# ── unpaid path: /api/book ───────────────────────────────────────────────────
def test_unpaid_booking_writes_the_flight_onto_the_token(monkeypatch):
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": "DL4089",
                    "arrivalAirport": "COS"}))

    assert len(_RecordingDb.calls) == 1, "the booking must mint exactly one token"
    call = _RecordingDb.calls[0]
    assert call["flight_number"] == "DL4089"
    assert call["expected_dest"] == "COS"


def test_unpaid_booking_normalises_what_the_customer_typed(monkeypatch):
    # Passengers type "dl4089 " and " cos". The console compares these against
    # provider airport codes, which are upper-case — so normalise at the door.
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": "  dl4089 ",
                    "arrivalAirport": " cos "}))

    call = _RecordingDb.calls[0]
    assert call["flight_number"] == "DL4089"
    assert call["expected_dest"] == "COS"


def test_a_non_airport_booking_is_completely_unchanged(monkeypatch):
    # The regression that matters most: every booking that isn't an airport
    # pickup must behave exactly as it did before this feature existed, which
    # means NULLs — not empty strings, which would look like a real value.
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post(BASE_BOOKING))

    call = _RecordingDb.calls[0]
    assert call["flight_number"] is None
    assert call["expected_dest"] is None


def test_blank_strings_are_treated_as_absent(monkeypatch):
    # A rendered-but-untouched form posts "", not undefined.
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": "   ", "arrivalAirport": ""}))

    call = _RecordingDb.calls[0]
    assert call["flight_number"] is None
    assert call["expected_dest"] is None


def test_a_flight_without_an_airport_is_still_recorded(monkeypatch):
    # The airport is optional even when the flight isn't — the destination
    # guard just can't disambiguate a reused ident without it.
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": "UA123"}))

    call = _RecordingDb.calls[0]
    assert call["flight_number"] == "UA123"
    assert call["expected_dest"] is None


def test_dispatch_sees_the_flight_on_the_calendar_appointment(monkeypatch):
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": "DL4089",
                    "arrivalAirport": "COS"}))

    assert _RecordingBookings.calls, "an invoice booking must create the appointment"
    notes = _RecordingBookings.calls[0]["notes"]
    assert "DL4089" in notes and "COS" in notes


def test_no_flight_leaves_the_calendar_note_alone(monkeypatch):
    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post(BASE_BOOKING))

    assert _RecordingBookings.calls[0]["notes"] == "Payment Method: Invoice"


# ── paid path: Stripe metadata → finalize ────────────────────────────────────
class _FakeSession:
    id = "cs_test_ABC12345"
    amount_total = 8500


def _finalize_receipt(monkeypatch, meta):
    """Run the paid path's receipt/token step against recording stubs."""
    import services.finalize_service as fin
    monkeypatch.setattr(fin, "DatabaseClient", _RecordingDb)
    monkeypatch.setattr(fin, "GraphClient", _SilentGraph)
    fin._send_paid_receipt(_FakeSession(), meta)


PAID_META = {
    "customerName": "Ada Lovelace",
    "customerEmail": "ada@example.com",
    "customerPhone": "555-0100",
    "pickup": "Colorado Springs Airport, CO",
    "dropoff": "1 Lake Ave, Colorado Springs, CO",
    "appointmentStart": "2026-08-01T21:00:00Z",
}


def test_paid_booking_carries_the_flight_through_stripe_metadata(monkeypatch):
    _reset()
    _finalize_receipt(monkeypatch, {**PAID_META, "flightNumber": "DL4089",
                                    "arrivalAirport": "COS"})

    call = _RecordingDb.calls[0]
    assert call["flight_number"] == "DL4089"
    assert call["expected_dest"] == "COS"


def test_paid_non_airport_booking_writes_nulls(monkeypatch):
    # Stripe metadata has no null — absent values arrive as "". They must not
    # be stored as empty strings.
    _reset()
    _finalize_receipt(monkeypatch, {**PAID_META, "flightNumber": "",
                                    "arrivalAirport": ""})

    call = _RecordingDb.calls[0]
    assert call["flight_number"] is None
    assert call["expected_dest"] is None


def test_paid_metadata_missing_the_keys_entirely(monkeypatch):
    # Sessions created before this shipped have no such keys at all.
    _reset()
    _finalize_receipt(monkeypatch, PAID_META)

    call = _RecordingDb.calls[0]
    assert call["flight_number"] is None
    assert call["expected_dest"] is None


def test_checkout_puts_the_flight_into_stripe_metadata(monkeypatch):
    # The paid path's ONLY store between checkout and finalize is Stripe
    # metadata. If the keys don't go in here, nothing downstream can recover
    # them — the booking is written without its flight and no error is raised.
    import stripe
    import api.checkout as checkout

    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(id="cs_test_1", url="https://stripe.test/x")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))

    import json
    req = func.HttpRequest(
        method="POST", url="/api/create-checkout-session",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "customerName": "Ada Lovelace", "customerEmail": "ada@example.com",
            "pickup": "A", "dropoff": "B", "price": "$85.00",
            "appointmentStart": "2026-08-01T21:00:00Z",
            "flightNumber": " dl4089 ", "arrivalAirport": " cos ",
            "successUrl": "https://x/success", "cancelUrl": "https://x/cancel",
        }).encode("utf-8"),
    )
    checkout.create_checkout_session(req)

    meta = captured["metadata"]
    assert meta["flightNumber"] == "DL4089"
    assert meta["arrivalAirport"] == "COS"


# ── the two paths must not drift ─────────────────────────────────────────────
def test_both_booking_paths_store_identical_values(monkeypatch):
    """Same messy input, same stored result — whichever way it was paid.

    These are two separate implementations in two separate files. Nothing but
    this test stops one of them from being changed alone.
    """
    messy_flight, messy_dest = "  dl4089 ", " cos "

    _reset()
    api = _patch_common(monkeypatch)
    api.book(_post({**BASE_BOOKING, "flightNumber": messy_flight,
                    "arrivalAirport": messy_dest}))
    unpaid = _RecordingDb.calls[0]

    _reset()
    _finalize_receipt(monkeypatch, {**PAID_META, "flightNumber": messy_flight,
                                    "arrivalAirport": messy_dest})
    paid = _RecordingDb.calls[0]

    assert unpaid["flight_number"] == paid["flight_number"]
    assert unpaid["expected_dest"] == paid["expected_dest"]
