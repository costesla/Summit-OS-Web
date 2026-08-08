import logging
import azure.functions as func
import json
import os
import stripe
import re

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="create-checkout-session", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def create_checkout_session(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
        
    try:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            raise Exception("STRIPE_SECRET_KEY not configured in backend!")
            
        req_body = req.get_json()
        
        customer_name = req_body.get("customerName", "")
        customer_email = req_body.get("customerEmail", "")
        customer_phone = req_body.get("customerPhone", "")

        # A non-chargeable client reaching an upfront-payment flow is incoherent:
        # this endpoint exists to take money from someone whose rides generate
        # none. REFUSE rather than quietly rerouting to the invoice path.
        #
        # A silent redirect would take an impossible request and make it look
        # handled — the same shape as every masked failure found in this codebase
        # — and it would destroy the signal. If a non-chargeable client keeps
        # arriving here, something upstream is routing them wrong and that is
        # worth seeing. Suppressing the link in /api/book while leaving this door
        # open would only move the payment request to a different surface.
        from services.database import is_non_chargeable, client_token
        if is_non_chargeable(customer_name):
            logging.warning(
                f"NON_CHARGEABLE client reached create-checkout-session: "
                f"token={client_token(customer_name)} quoted={req_body.get('price')} — "
                f"REFUSED. Upstream routing sent a no-revenue client to an "
                f"upfront-payment flow; investigate rather than retry."
            )
            return func.HttpResponse(
                json.dumps({
                    "error": "This booking cannot be paid online. Please book without payment.",
                    "code": "non_chargeable_client",
                }),
                status_code=409, headers=_cors_headers(), mimetype="application/json"
            )

        pickup = req_body.get("pickup", "")
        dropoff = req_body.get("dropoff", "")
        appointment_start = req_body.get("appointmentStart", "")
        price = req_body.get("price", "$0.00")
        passengers = req_body.get("passengers", 1)
        trip_distance = req_body.get("tripDistance", "N/A")
        trip_duration = req_body.get("tripDuration", "N/A")
        duration = req_body.get("duration", 60)
        return_start = req_body.get("returnStart") or ""
        # Airport-pickup context. Stripe metadata values are capped at 500
        # chars; a flight number and an airport code are far inside that, so
        # they ride along as their own keys rather than needing packing.
        # Empty strings when absent — Stripe metadata has no null.
        flight_number = (req_body.get("flightNumber") or "").strip().upper()
        arrival_airport = (req_body.get("arrivalAirport") or "").strip().upper()
        # Ordered stops as numbered keys — see encode_route_metadata for why
        # they can't share one value.
        from services.bookings import encode_route_metadata
        route_metadata = encode_route_metadata(req_body.get("stops"))
        success_url = req_body.get("successUrl")
        cancel_url = req_body.get("cancelUrl")
        
        if not success_url or not cancel_url:
            raise Exception("successUrl and cancelUrl are required in the payload")
        
        # Convert formatted price string (e.g., "$100.00") to number for Stripe
        amount_num = float(re.sub(r'[^0-9.]', '', str(price)))
        amount_cents = int(round(amount_num * 100))

        # Mint the invoice number BEFORE creating the session. Stripe does not
        # allow invoice_creation.invoice_data to be updated after Session.create,
        # so anything that should appear on the invoice PDF has to be known now —
        # which rules out the old session-id-derived form. finalize_service reads
        # this back out of metadata so the PDF, the confirmation page, the receipt
        # email, and the Rides.Rides row all carry the same number.
        import datetime as _dt
        from services.invoice import build_invoice_id
        safe_name = (customer_name or "").strip() or "Client"
        invoice_date = (appointment_start or "").strip() or _dt.date.today().isoformat()
        invoice_id = build_invoice_id(safe_name, invoice_date)

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_email=customer_email if customer_email else None,
            payment_intent_data={
                'receipt_email': customer_email if customer_email else None,
            },
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'SummitOS Booking',
                        'description': f"{pickup} \n-> {dropoff}",
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            # Generates a real Stripe invoice (hosted page + PDF) for the
            # passenger. Previously a paid booking produced no invoice at all,
            # so there was nothing to show on the confirmation page and nothing
            # durable if the Graph receipt email failed to send.
            invoice_creation={
                'enabled': True,
                'invoice_data': {
                    'custom_fields': [
                        {'name': 'Invoice #', 'value': invoice_id},
                    ],
                },
            },
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'invoiceId': invoice_id,
                'customerName': customer_name,
                'customerEmail': customer_email,
                'customerPhone': customer_phone,
                'pickup': pickup,
                'dropoff': dropoff,
                'appointmentStart': appointment_start,
                'passengers': str(passengers),
                'tripDistance': trip_distance,
                'tripDuration': trip_duration,
                'duration': str(duration),
                'returnStart': return_start,
                'fareString': str(price),
                'flightNumber': flight_number,
                'arrivalAirport': arrival_airport,
                **route_metadata
            }
        )
        
        return func.HttpResponse(
            json.dumps({"id": session.id, "url": session.url}),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.error(f"Stripe Checkout Error: {str(e)}\n{tb}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )
