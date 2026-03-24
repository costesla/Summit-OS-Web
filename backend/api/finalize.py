import logging
import azure.functions as func
import json
import os
import stripe
import time
import re

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="finalize-booking", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def finalize_booking(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            raise Exception("STRIPE_SECRET_KEY not configured!")

        req_body = req.get_json()
        session_id = req_body.get("session_id")
        if not session_id:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "No session ID provided"}),
                status_code=400,
                headers=_cors_headers(),
                mimetype="application/json"
            )

        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return func.HttpResponse(
                json.dumps({"success": False, "error": "Payment not completed"}),
                status_code=400,
                headers=_cors_headers(),
                mimetype="application/json"
            )

        meta = session.metadata
        if not meta:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "No booking metadata found"}),
                status_code=400,
                headers=_cors_headers(),
                mimetype="application/json"
            )

        # 1. Create calendar booking
        import requests as http_requests
        booking_res = http_requests.post(
            "https://summitos-api.azurewebsites.net/api/calendar-book",
            json={
                "customerName": meta.get("customerName"),
                "customerEmail": meta.get("customerEmail"),
                "customerPhone": meta.get("customerPhone"),
                "pickup": meta.get("pickup"),
                "dropoff": meta.get("dropoff"),
                "appointmentStart": meta.get("appointmentStart"),
                "duration": 60,
                "price": meta.get("fareString"),
                "passengers": int(meta.get("passengers", "1")),
                "paymentMethod": "Stripe"
            }
        )
        booking_data = booking_res.json()
        event_id = booking_data.get("eventId")

        # 2. Send receipt email + log to DB via /api/book
        try:
            http_requests.post(
                "https://summitos-api.azurewebsites.net/api/book",
                json={
                    "customerName": meta.get("customerName"),
                    "customerEmail": meta.get("customerEmail"),
                    "customerPhone": meta.get("customerPhone"),
                    "pickup": meta.get("pickup"),
                    "dropoff": meta.get("dropoff"),
                    "appointmentStart": meta.get("appointmentStart"),
                    "price": meta.get("fareString"),
                    "passengers": int(meta.get("passengers", "1")),
                    "tripDistance": meta.get("tripDistance"),
                    "tripDuration": meta.get("tripDuration"),
                    "paymentMethod": "Stripe"
                }
            )
        except Exception as email_err:
            logging.warning(f"Receipt email failed (non-fatal): {email_err}")

        return func.HttpResponse(
            json.dumps({"success": True, "eventId": event_id}),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )

    except Exception as e:
        import traceback
        logging.error(f"Finalize Booking Error: {str(e)}\n{traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )
