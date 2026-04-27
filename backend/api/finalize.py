import logging
import azure.functions as func
import json
import os
import stripe
import time
import re
from services.graph import GraphClient

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

        # If this is a post-trip invoice payment, we don't need to create a calendar booking
        if meta.get("source") == "post_trip_invoice":
            customer_name = meta.get("customerName", "Valued Customer")
            customer_email = meta.get("customerEmail")
            
            logging.info(f"Post-trip invoice paid for {customer_name}. Skipping calendar booking.")
            
            if customer_email:
                try:
                    graph = GraphClient()
                    amount_paid = session.amount_total / 100.0
                    html_confirmation = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px;">
                        <div style="text-align: center; background-color: #000; padding: 20px; border-radius: 10px 10px 0 0;">
                            <h1 style="color: #fff; margin: 0;">Payment Received</h1>
                        </div>
                        <div style="padding: 20px;">
                            <p>Hi {customer_name.split()[0]},</p>
                            <p>Thank you! We've successfully received your payment of <strong>${amount_paid:,.2f}</strong> for your recent SummitOS trip.</p>
                            <p>This email confirms that your invoice has been settled in full. We appreciate your business and look forward to driving you again soon.</p>
                            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
                            <p style="font-size: 12px; color: #666; text-align: center;">COS Tesla LLC · Colorado Springs, CO</p>
                        </div>
                    </div>
                    """
                    graph.send_mail(
                        to_email=customer_email,
                        subject="Payment Received – Thank You! | SummitOS",
                        body_html=html_confirmation
                    )
                    logging.info(f"Confirmation email sent to {customer_email}")
                except Exception as e:
                    logging.error(f"Failed to send payment confirmation email: {e}")

            return func.HttpResponse(
                json.dumps({"success": True, "message": "Invoice payment confirmed"}),
                status_code=200,
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
