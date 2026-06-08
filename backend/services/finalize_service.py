"""
Shared Stripe session finalization logic.

Used by both the frontend-facing /api/finalize-booking endpoint
and the Stripe webhook (checkout.session.completed).

Idempotency is enforced at the SQL layer via a unique constraint
on Bookings.StripeFinalized.SessionID – the first caller wins,
subsequent calls return a duplicate marker without side effects.
"""

import logging
import os
import re
import stripe
import pyodbc
from services.database import DatabaseClient
from services.graph import GraphClient


def _claim_session(session_id: str) -> bool:
    """Atomically claim a session for finalization.

    Returns True if this call successfully claimed the session,
    False if it was already finalized by a prior call.
    Raises on transient DB errors so the caller can decide how to react.
    """
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        raise Exception("Database unavailable for idempotency check")
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Bookings.StripeFinalized (SessionID, FinalizedAt) VALUES (?, GETUTCDATE())",
            (session_id,),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True  # Successfully claimed
    except pyodbc.IntegrityError:
        conn.close()
        return False  # Already finalized
    except Exception:
        conn.close()
        raise


def _release_claim(session_id: str) -> None:
    """Compensating delete: release a claimed session so retries can re-run.

    Called when the post-claim finalization work fails (calendar timeout,
    DB blip, etc.).  Without this, the durable claim row would cause all
    future attempts to short-circuit to "already finalized", silently
    losing the booking.
    """
    try:
        db = DatabaseClient()
        conn = db.get_connection()
        if not conn:
            logging.error(f"Cannot release claim for {session_id}: DB unavailable")
            return
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM Bookings.StripeFinalized WHERE SessionID = ?",
            (session_id,),
        )
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"Released claim for {session_id} after finalization failure")
    except Exception as e:
        logging.error(f"Failed to release claim for {session_id}: {e}")


def finalize_stripe_session(session_id: str) -> dict:
    """Finalize a paid Stripe Checkout session.

    1. Validate payment status & metadata
    2. Claim the session atomically (SQL idempotency)
    3. Post-trip invoice path  → send confirmation email
       Normal booking path     → create calendar event + send receipt
    4. On failure, release the claim (compensating delete) so retries work
    5. Mark Stripe metadata as finalized (non-authoritative fast path)

    Returns a dict suitable for JSON serialization to the frontend.
    """
    # ── Stripe setup ──────────────────────────────────────────────────────
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise Exception("STRIPE_SECRET_KEY not configured!")

    session = stripe.checkout.Session.retrieve(session_id)

    if session.payment_status != "paid":
        return {"success": False, "error": "Payment not completed"}

    meta = session.metadata
    if not meta:
        return {"success": False, "error": "No booking metadata found"}

    # ── Idempotency gate ──────────────────────────────────────────────────
    claimed = _claim_session(session_id)
    if not claimed:
        logging.info(f"Session {session_id} already finalized (duplicate)")
        return {
            "success": True,
            "message": "Already finalized",
            "duplicate": True,
        }

    # ── Shared data ───────────────────────────────────────────────────────
    customer_name = meta.get("customerName", "Valued Customer")
    customer_email = meta.get("customerEmail")
    amount_cents = session.amount_total or 0
    amount_usd = amount_cents / 100.0
    event_id = None

    # ── Post-trip invoice path ────────────────────────────────────────────
    if meta.get("source") == "post_trip_invoice":
        logging.info(f"Post-trip invoice paid for {customer_name}. Skipping calendar booking.")

        # Email is best-effort for this path — the "booking" is the invoice
        # payment itself, which Stripe already recorded.  A failed email
        # doesn't constitute a lost booking, so we do NOT release the claim.
        if customer_email:
            try:
                graph = GraphClient()
                html_confirmation = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px;">
                    <div style="text-align: center; background-color: #000; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1 style="color: #fff; margin: 0;">Payment Received</h1>
                    </div>
                    <div style="padding: 20px;">
                        <p>Hi {customer_name.split()[0]},</p>
                        <p>Thank you! We've successfully received your payment of <strong>${amount_usd:,.2f}</strong> for your recent SummitOS trip.</p>
                        <p>This email confirms that your invoice has been settled in full. We appreciate your business and look forward to driving you again soon.</p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
                        <p style="font-size: 12px; color: #666; text-align: center;">COS Tesla LLC · Colorado Springs, CO</p>
                    </div>
                </div>
                """
                graph.send_mail(
                    to_email=customer_email,
                    subject="Payment Received – Thank You! | SummitOS",
                    body_html=html_confirmation,
                )
                logging.info(f"Confirmation email sent to {customer_email}")
            except Exception as e:
                logging.error(f"Failed to send payment confirmation email: {e}")

        # Optional: tag Stripe metadata
        try:
            stripe.checkout.Session.modify(session_id, metadata={"finalized": "true"})
        except Exception:
            pass

        return {
            "success": True,
            "message": "Invoice payment confirmed",
            "duplicate": False,
            "customerEmail": customer_email,
            "amount": amount_usd,
        }

    # ── Normal booking path ──────────────────────────────────────────────
    # ONE critical call to /api/calendar-book. If it fails, release the claim
    # so a Stripe redelivery or page refresh can retry cleanly.
    import requests as http_requests

    try:
        booking_res = http_requests.post(
            "https://summitos-api.azurewebsites.net/api/calendar-book",
            json={
                "sessionId": session_id,   # idempotency key — calendar-book MUST dedupe on this
                "customerName": meta.get("customerName"),
                "customerEmail": meta.get("customerEmail"),
                "customerPhone": meta.get("customerPhone"),
                "pickup": meta.get("pickup"),
                "dropoff": meta.get("dropoff"),
                "appointmentStart": meta.get("appointmentStart"),
                "duration": 60,
                "price": meta.get("fareString"),
                "passengers": int(meta.get("passengers", "1")),
                "paymentMethod": "Stripe",
            },
            timeout=30,
        )
        booking_res.raise_for_status()
        booking_data = booking_res.json()
        event_id = booking_data.get("eventId")
    except Exception as booking_err:
        logging.error(f"Calendar booking failed for {session_id}: {booking_err}")
        _release_claim(session_id)
        raise  # caller returns an error / Stripe retries

    # A 200 with no eventId is a soft failure — treat it as a failed booking,
    # not a success, so we don't record a non-booking and strand the claim.
    if not event_id:
        logging.error(f"Calendar booking returned no eventId for {session_id}")
        _release_claim(session_id)
        raise RuntimeError(f"calendar-book returned no eventId for {session_id}")

    # 2. Send receipt email + log to DB via /api/book
    #    This is best-effort: the booking already exists in the calendar.
    #    A failed email doesn't warrant releasing the claim.
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
                "paymentMethod": "Stripe",
            },
            timeout=30,
        )
    except Exception as email_err:
        logging.warning(f"Receipt email failed (non-fatal): {email_err}")

    # Optional: tag Stripe metadata
    try:
        stripe.checkout.Session.modify(session_id, metadata={"finalized": "true"})
    except Exception:
        pass

    return {
        "success": True,
        "eventId": event_id,
        "message": "Booking finalized",
        "duplicate": False,
        "customerEmail": customer_email,
        "amount": amount_usd,
    }

