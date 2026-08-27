"""Passenger-facing payment confirmation and invoicing.

Covers the two things a passenger is left with after paying: a Stripe invoice
carrying our INV- number, and a confirmation endpoint that proves the payment
without leaking anything they don't already know.
"""

import json
import os
import sys
import types

import azure.functions as func
import pytest
import stripe

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.finalize_service import canonical_invoice_id


class FakeSession(dict):
    """Stands in for a Stripe object: dict-style .get() plus attribute access."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def _confirm_request(session_id):
    params = {"session_id": session_id} if session_id is not None else {}
    return func.HttpRequest(
        method="GET",
        url="/api/payments/confirm",
        params=params,
        body=b"",
    )


# ── the invoice number ───────────────────────────────────────────────────────

def test_minted_invoice_id_wins_when_checkout_supplied_one():
    session = types.SimpleNamespace(id="cs_test_ZZZZ9999")
    meta = {"customerName": "Ada Lovelace", "invoiceId": "INV-ADA-20260801-0930"}
    assert canonical_invoice_id(session, meta) == "INV-ADA-20260801-0930"


def test_legacy_sessions_still_resolve_to_their_original_id():
    """Sessions created before minting existed must not change identity.

    Their Rides.Rides row was written with the session-derived form; if this
    fallback ever drifts, an old booking silently becomes unmatchable.
    """
    session = types.SimpleNamespace(id="cs_test_abcd1234")
    meta = {"customerName": "Ada Lovelace"}
    assert canonical_invoice_id(session, meta) == "INV-Ada-ABCD1234"


def test_blank_customer_name_does_not_crash_the_id():
    session = types.SimpleNamespace(id="cs_test_abcd1234")
    assert canonical_invoice_id(session, {"customerName": "   "}) == "INV-Guest-ABCD1234"
    assert canonical_invoice_id(session, {}) == "INV-Guest-ABCD1234"


# ── flow A: booking checkout sessions ────────────────────────────────────────

def test_checkout_creates_an_invoice_carrying_our_number(monkeypatch):
    """Without invoice_creation a paid booking produced no invoice at all."""
    import api.checkout as checkout

    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(id="cs_test_1", url="https://stripe.test/x")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))

    checkout.create_checkout_session(func.HttpRequest(
        method="POST", url="/api/create-checkout-session",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "customerName": "Ada Lovelace", "customerEmail": "ada@example.com",
            "pickup": "A", "dropoff": "B", "price": "$85.00",
            "appointmentStart": "2026-08-01T21:00:00Z",
            "successUrl": "https://x/success", "cancelUrl": "https://x/cancel",
        }).encode("utf-8"),
    ))

    assert captured["invoice_creation"]["enabled"] is True

    # The number on the PDF and the number in metadata must be the same string —
    # they are what finalize writes to the DB and what the passenger quotes.
    field = captured["invoice_creation"]["invoice_data"]["custom_fields"][0]
    assert field["name"] == "Invoice #"
    assert field["value"] == captured["metadata"]["invoiceId"]
    assert field["value"].startswith("INV-ADA-20260801")

    # Guardrail: the email must still be attached or Stripe sends nothing.
    assert captured["customer_email"] == "ada@example.com"


def test_checkout_id_survives_into_the_canonical_number(monkeypatch):
    """The minted id has to round-trip through metadata into finalize."""
    import api.checkout as checkout

    captured = {}
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(
        stripe.checkout.Session, "create",
        staticmethod(lambda **kw: captured.update(kw) or types.SimpleNamespace(
            id="cs_test_1", url="https://stripe.test/x")),
    )

    checkout.create_checkout_session(func.HttpRequest(
        method="POST", url="/api/create-checkout-session",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "customerName": "Ada Lovelace", "customerEmail": "ada@example.com",
            "pickup": "A", "dropoff": "B", "price": "$85.00",
            "appointmentStart": "2026-08-01T21:00:00Z",
            "successUrl": "https://x/s", "cancelUrl": "https://x/c",
        }).encode("utf-8"),
    ))

    session = types.SimpleNamespace(id="cs_test_abcd1234")
    assert canonical_invoice_id(session, captured["metadata"]) == captured["metadata"]["invoiceId"]


# ── flow B: post-trip payment links ──────────────────────────────────────────

def test_payment_link_returns_the_payer_to_our_site(monkeypatch):
    """These links used to default to stripe.com, so the payer never came back."""
    from services import invoice as invoice_service

    captured = {}

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.Price, "create",
                        staticmethod(lambda **kw: types.SimpleNamespace(id="price_1")))
    monkeypatch.setattr(stripe.PaymentLink, "create",
                        staticmethod(lambda **kw: captured.update(kw) or types.SimpleNamespace(
                            url="https://buy.stripe.com/test")))

    url = invoice_service.create_stripe_payment_link(
        "Ada Lovelace", "ada@example.com", 120.0, "COS → DEN", invoice_id="INV-ADA-1"
    )

    redirect = captured["after_completion"]["redirect"]["url"]
    assert captured["after_completion"]["type"] == "redirect"
    assert redirect.startswith("https://www.costesla.com/invoice/success")
    # Without this template the confirmation page has nothing to look up.
    assert "{CHECKOUT_SESSION_ID}" in redirect

    assert captured["invoice_creation"]["enabled"] is True
    assert captured["invoice_creation"]["invoice_data"]["custom_fields"][0]["value"] == "INV-ADA-1"
    assert captured["metadata"]["source"] == "post_trip_invoice"
    # Payment Links take no receipt_email, so the address reaches Stripe by
    # prefill + customer creation instead.
    assert "prefilled_email" in url


def test_payment_link_survives_stripe_rejecting_customer_creation(monkeypatch):
    """Losing the link would remove the card option entirely — worse than the
    redundant parameter it is retrying without."""
    from services import invoice as invoice_service

    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        if "customer_creation" in kwargs:
            raise Exception("Received unknown parameter: customer_creation")
        return types.SimpleNamespace(url="https://buy.stripe.com/test")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.Price, "create",
                        staticmethod(lambda **kw: types.SimpleNamespace(id="price_1")))
    monkeypatch.setattr(stripe.PaymentLink, "create", staticmethod(_create))

    url = invoice_service.create_stripe_payment_link(
        "Ada Lovelace", "ada@example.com", 120.0, "COS → DEN", invoice_id="INV-ADA-1"
    )

    assert url is not None
    assert len(calls) == 2
    assert calls[1]["invoice_creation"]["enabled"] is True


# ── the confirmation endpoint ────────────────────────────────────────────────

def _paid_session():
    return FakeSession(
        id="cs_test_abcd1234",
        status="complete",
        payment_status="paid",
        amount_total=28500,
        currency="usd",
        metadata={
            "customerName": "Ada Lovelace",
            "customerEmail": "ada@example.com",
            "customerPhone": "719-555-0142",
            "pickup": "1200 Cascade Ave",
            "dropoff": "DEN",
            "fareString": "$285.00",
            "invoiceId": "INV-ADA-20260801-0930",
        },
        invoice={"number": "B12F-0007",
                 "hosted_invoice_url": "https://invoice.stripe.com/x",
                 "invoice_pdf": "https://invoice.stripe.com/x/pdf"},
        payment_intent={"latest_charge": {"receipt_url": "https://pay.stripe.com/r/x"}},
    )


def test_unpaid_session_reveals_only_that_it_is_pending(monkeypatch):
    import api.payment_confirm as pc

    session = _paid_session()
    session["payment_status"] = "unpaid"
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        staticmethod(lambda *a, **kw: session))

    body = json.loads(pc.payments_confirm(_confirm_request("cs_test_abcd1234")).get_body())
    # Exactly one key. An unpaid session must not disclose trip or contact data.
    assert body == {"status": "pending"}


def test_paid_session_returns_the_links_without_leaking_contact_details(monkeypatch):
    import api.payment_confirm as pc

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        staticmethod(lambda *a, **kw: _paid_session()))

    raw = pc.payments_confirm(_confirm_request("cs_test_abcd1234")).get_body().decode()
    body = json.loads(raw)

    assert body["status"] == "paid"
    assert body["amountTotal"] == "$285.00"
    assert body["invoiceNumber"] == "INV-ADA-20260801-0930"
    assert body["stripeInvoiceNumber"] == "B12F-0007"
    assert body["invoicePdf"] == "https://invoice.stripe.com/x/pdf"
    assert body["receiptUrl"] == "https://pay.stripe.com/r/x"
    assert body["firstName"] == "Ada"

    # A leaked session_id must reveal nothing the payer doesn't already have.
    assert "Lovelace" not in raw
    assert "ada@example.com" not in raw
    assert "719-555-0142" not in raw


def test_paid_session_reports_the_receipt_before_the_invoice_finalizes(monkeypatch):
    """Stripe finalizes the invoice seconds after redirect; the page needs the
    receipt immediately and must not be handed a null PDF as if it were a link."""
    import api.payment_confirm as pc

    session = _paid_session()
    session["invoice"] = None

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        staticmethod(lambda *a, **kw: session))

    body = json.loads(pc.payments_confirm(_confirm_request("cs_test_abcd1234")).get_body())

    assert body["status"] == "paid"
    assert body["invoicePdf"] is None
    assert body["hostedInvoiceUrl"] is None
    assert body["receiptUrl"] == "https://pay.stripe.com/r/x"


def test_expired_session_is_not_reported_as_pending(monkeypatch):
    """A session that can never be paid would make the page retry forever."""
    import api.payment_confirm as pc

    session = _paid_session()
    session["status"] = "expired"
    session["payment_status"] = "unpaid"

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        staticmethod(lambda *a, **kw: session))

    resp = pc.payments_confirm(_confirm_request("cs_test_abcd1234"))
    assert resp.status_code == 404
    assert json.loads(resp.get_body())["status"] == "not_found"


@pytest.mark.parametrize("bad", [None, "", "not-a-session", "pi_test_123"])
def test_malformed_session_ids_are_rejected_without_calling_stripe(monkeypatch, bad):
    import api.payment_confirm as pc

    def _boom(*a, **kw):
        raise AssertionError("Stripe must not be called for a malformed id")

    monkeypatch.setattr(stripe.checkout.Session, "retrieve", staticmethod(_boom))

    resp = pc.payments_confirm(_confirm_request(bad))
    assert resp.status_code == 404
    assert json.loads(resp.get_body()) == {"status": "not_found"}


def test_stripe_errors_never_reach_the_passenger(monkeypatch):
    import api.payment_confirm as pc

    def _raise(*a, **kw):
        raise Exception("No such checkout.session: 'cs_x'; sk_live_abc123 leaked")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", staticmethod(_raise))

    resp = pc.payments_confirm(_confirm_request("cs_test_abcd1234"))
    raw = resp.get_body().decode()
    assert resp.status_code == 404
    assert json.loads(raw) == {"status": "not_found"}
    assert "sk_live" not in raw
    assert "No such checkout.session" not in raw
