import logging
import azure.functions as func
import json
import os
import stripe

bp = func.Blueprint()


@bp.route(route="stripe-webhook", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def stripe_webhook(req: func.HttpRequest) -> func.HttpResponse:
    payload = req.get_body()
    sig_header = req.headers.get("Stripe-Signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logging.error("STRIPE_WEBHOOK_SECRET not configured")
        return func.HttpResponse("Webhook secret not configured", status_code=500)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.SignatureVerificationError:
        logging.warning("Invalid Stripe webhook signature")
        return func.HttpResponse("Invalid signature", status_code=400)
    except Exception as e:
        logging.error(f"Webhook parse error: {e}")
        return func.HttpResponse(str(e), status_code=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        logging.info(f"Webhook: checkout.session.completed for {session_id}")
        try:
            from services.finalize_service import finalize_stripe_session

            result = finalize_stripe_session(session_id)
            logging.info(f"Webhook finalization result: {result}")
        except Exception as e:
            logging.error(f"Webhook finalization failed: {e}")
            # Still return 200 so Stripe doesn't retry indefinitely

    return func.HttpResponse(
        json.dumps({"received": True}),
        status_code=200,
        mimetype="application/json",
    )
