"""
send-invoice Azure Function
POST /api/send-invoice

Generates and emails a post-trip custom invoice with:
  - Venmo, Zelle, and Stripe payment options
  - Thor telemetry: electric energy used vs gas equivalent
"""

import logging
import json
import os
import azure.functions as func
from datetime import datetime

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

def _json_response(data: dict, status: int = 200):
    return func.HttpResponse(
        json.dumps(data),
        status_code=status,
        headers=_cors_headers(),
        mimetype="application/json"
    )


@bp.route(route="send-invoice", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def send_invoice(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST body (JSON):
    {
      "customerName":  "Jacquelyn Heslep",
      "customerEmail": "jackie@example.com",
      "amountUSD":     100.00,
      "pickup":        "Colorado Springs, CO",
      "dropoff":       "Denver International Airport",
      "tripDate":      "2026-04-16",          // YYYY-MM-DD or readable string
      "distanceMiles": 75.2,                  // optional, improves telemetry
      "energyUsedKwh": 19.4,                  // optional, from Tessie
      "notes":         "Thank you for riding!", // optional
      "generateStripe": true                  // optional, default true
    }
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        body = req.get_json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    # ── Required Fields ───────────────────────────────────────────────────────
    customer_name  = body.get("customerName", "").strip()
    customer_email = body.get("customerEmail", "").strip()
    amount_usd     = body.get("amountUSD")
    pickup         = body.get("pickup", "").strip()
    dropoff        = body.get("dropoff", "").strip()
    trip_date_raw  = body.get("tripDate", datetime.now().strftime("%Y-%m-%d"))

    if not customer_email:
        return _json_response({"error": "customerEmail is required"}, 400)
    if amount_usd is None:
        return _json_response({"error": "amountUSD is required"}, 400)

    # ── Optional Fields ───────────────────────────────────────────────────────
    distance_miles  = float(body.get("distanceMiles", 0) or 0)
    energy_kwh      = float(body.get("energyUsedKwh", 0) or 0)
    notes           = body.get("notes", "").strip()
    gen_stripe      = body.get("generateStripe", True)

    # ── Format trip date ──────────────────────────────────────────────────────
    try:
        trip_date_obj = datetime.strptime(trip_date_raw[:10], "%Y-%m-%d")
        trip_date_fmt = trip_date_obj.strftime("%A, %B %-d, %Y")
    except Exception:
        trip_date_fmt = trip_date_raw

    # ── Import services ───────────────────────────────────────────────────────
    try:
        from services.invoice import (
            calculate_thor_telemetry,
            create_stripe_payment_link,
            build_invoice_html,
            build_invoice_id,
        )
        from services.graph import GraphClient
    except Exception as e:
        logging.error(f"Service import error: {e}")
        return _json_response({"error": f"Internal service error: {str(e)}"}, 500)

    # ── Try to pull Tessie telemetry if not provided ──────────────────────────
    if distance_miles == 0 or energy_kwh == 0:
        try:
            from services.tessie import TessieClient
            vin = os.environ.get("TESLA_VIN", "")
            if vin:
                tessie = TessieClient()
                import time
                trip_ts = int(trip_date_obj.timestamp()) + (18 * 3600)  # assume ~6pm
                drive = tessie.match_drive_to_trip(vin, trip_ts, is_private=True)
                if drive:
                    if distance_miles == 0:
                        distance_miles = float(drive.get("distance", 0) or 0)
                    if energy_kwh == 0:
                        energy_kwh = float(drive.get("energy_used", 0) or 0)
                    logging.info(f"Tessie auto-match: {distance_miles} mi, {energy_kwh} kWh")
        except Exception as te:
            logging.warning(f"Tessie auto-match failed (non-fatal): {te}")

    # ── Build invoice ID ──────────────────────────────────────────────────────
    invoice_id = build_invoice_id(customer_name, trip_date_raw)

    # ── Generate Stripe URL ───────────────────────────────────────────────────
    stripe_url = None
    if gen_stripe:
        trip_label = f"{pickup} → {dropoff} on {trip_date_fmt}"
        stripe_url = create_stripe_payment_link(customer_name, customer_email, float(amount_usd), trip_label)

    # ── Calculate Thor Telemetry ──────────────────────────────────────────────
    telemetry = calculate_thor_telemetry(distance_miles, energy_kwh if energy_kwh > 0 else None)

    # ── Build HTML Email ──────────────────────────────────────────────────────
    html_body = build_invoice_html(
        customer_name=customer_name,
        customer_email=customer_email,
        trip_date=trip_date_fmt,
        pickup=pickup or "N/A",
        dropoff=dropoff or "N/A",
        amount_usd=float(amount_usd),
        invoice_id=invoice_id,
        telemetry=telemetry,
        stripe_url=stripe_url,
        notes=notes
    )

    # ── Send via Microsoft Graph ──────────────────────────────────────────────
    try:
        graph = GraphClient()
        graph.send_mail(
            to_email=customer_email,
            subject=f"Your SummitOS Invoice – {invoice_id}",
            body_html=html_body,
            from_email="peter.teehan@costesla.com"
        )
        logging.info(f"Invoice {invoice_id} sent to {customer_email}")
    except Exception as email_err:
        logging.error(f"Graph email failed: {email_err}")
        # Return partial success so caller knows email failed but data was built
        return _json_response({
            "success": False,
            "invoiceId": invoice_id,
            "error": f"Email delivery failed: {str(email_err)}",
            "stripeUrl": stripe_url,
            "telemetry": telemetry
        }, 500)

    return _json_response({
        "success": True,
        "invoiceId": invoice_id,
        "sentTo": customer_email,
        "amountUSD": float(amount_usd),
        "stripeGenerated": stripe_url is not None,
        "stripeUrl": stripe_url,
        "telemetry": telemetry
    })
