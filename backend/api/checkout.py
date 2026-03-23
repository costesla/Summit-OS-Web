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
        pickup = req_body.get("pickup", "")
        dropoff = req_body.get("dropoff", "")
        appointment_start = req_body.get("appointmentStart", "")
        price = req_body.get("price", "$0.00")
        passengers = req_body.get("passengers", 1)
        trip_distance = req_body.get("tripDistance", "N/A")
        trip_duration = req_body.get("tripDuration", "N/A")
        success_url = req_body.get("successUrl")
        cancel_url = req_body.get("cancelUrl")
        
        if not success_url or not cancel_url:
            raise Exception("successUrl and cancelUrl are required in the payload")
        
        # Convert formatted price string (e.g., "$100.00") to number for Stripe
        amount_num = float(re.sub(r'[^0-9.]', '', str(price)))
        amount_cents = int(round(amount_num * 100))
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_email=customer_email if customer_email else None,
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
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'customerName': customer_name,
                'customerEmail': customer_email,
                'customerPhone': customer_phone,
                'pickup': pickup,
                'dropoff': dropoff,
                'appointmentStart': appointment_start,
                'passengers': str(passengers),
                'tripDistance': trip_distance,
                'tripDuration': trip_duration,
                'fareString': str(price)
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
