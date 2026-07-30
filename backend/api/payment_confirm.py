"""Passenger-facing payment confirmation.

Backs the /invoice/success and /book/success pages. Both Stripe flows
(booking Checkout Sessions and post-trip Payment Links) land here with a
session_id, and this is the only thing standing between the passenger and a
blank page after they've been charged.

Security posture: the endpoint is deliberately anonymous — it is called by a
static page with no credential to present — so it returns a hand-written
whitelist and never the raw Stripe session. A leaked session_id must reveal
nothing the payer doesn't already have: their own first name, their own trip,
their own amount, and links Stripe already emailed them. No surname, no email,
no phone, no PaymentIntent id, no card details.
"""

import logging
import os

import azure.functions as func
import json
import stripe

bp = func.Blueprint()


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        headers=_cors_headers(),
        mimetype="application/json",
    )


def _format_amount(minor_units, currency: str) -> str:
    """Stripe amounts are in minor units; passengers read major units."""
    major = (minor_units or 0) / 100.0
    if (currency or "usd").lower() == "usd":
        return f"${major:,.2f}"
    return f"{major:,.2f} {(currency or '').upper()}"


def _unwrap(value):
    """Expanded fields come back as objects, unexpanded ones as bare id strings.

    Checked by shape rather than by class: StripeObject's import path moves
    across the 8.6–14 range this project allows.
    """
    if value is None or isinstance(value, str):
        return None
    return value


@bp.route(route="payments/confirm", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_confirm(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    session_id = (req.params.get("session_id") or "").strip()
    if not session_id or not session_id.startswith("cs_"):
        return _json({"status": "not_found"}, 404)

    try:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            raise Exception("STRIPE_SECRET_KEY not configured")

        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["invoice", "payment_intent.latest_charge"],
        )
    except Exception as e:
        # A bad, forged, or long-expired id is the common case here and is not
        # an error worth alarming on. Never leak the Stripe message to the page.
        logging.warning(f"payments_confirm lookup failed for {session_id[:20]}: {e}")
        return _json({"status": "not_found"}, 404)

    # A session that can never be paid is not "pending" — telling the page to
    # keep retrying one would spin forever.
    if getattr(session, "status", None) == "expired":
        return _json({"status": "not_found"}, 404)

    # Nothing but the status until the money is actually confirmed.
    if session.payment_status != "paid":
        return _json({"status": "pending"})

    meta = session.metadata or {}

    invoice = _unwrap(session.get("invoice"))
    payment_intent = _unwrap(session.get("payment_intent"))
    charge = _unwrap(payment_intent.get("latest_charge")) if payment_intent else None

    from services.finalize_service import canonical_invoice_id

    raw_name = (meta.get("customerName") or "").strip()
    first_name = raw_name.split()[0] if raw_name else None

    payload = {
        "status": "paid",
        "amountTotal": _format_amount(session.amount_total, session.currency),
        "currency": (session.currency or "usd").lower(),
        "firstName": first_name,
        "invoiceNumber": canonical_invoice_id(session, meta),
        "stripeInvoiceNumber": invoice.get("number") if invoice else None,
        # These two lag the redirect by a few seconds while Stripe finalizes the
        # invoice, so they are legitimately null on the first call. The page
        # retries rather than rendering a dead "Download PDF" button.
        "hostedInvoiceUrl": invoice.get("hosted_invoice_url") if invoice else None,
        "invoicePdf": invoice.get("invoice_pdf") if invoice else None,
        # Available immediately, which is why it is the page's fallback.
        "receiptUrl": charge.get("receipt_url") if charge else None,
        "source": meta.get("source") or "booking",
    }

    # Trip context, booking flow only — a post-trip invoice has no upcoming ride.
    for field in ("pickup", "dropoff", "appointmentStart", "fareString"):
        value = (meta.get(field) or "").strip()
        if value:
            payload[field] = value

    return _json(payload)
