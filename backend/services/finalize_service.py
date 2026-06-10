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
        try:
            cur.execute(
                "INSERT INTO Bookings.StripeFinalized (SessionID, FinalizedAt) VALUES (?, GETUTCDATE())",
                (session_id,),
            )
        except pyodbc.ProgrammingError:
            # First run: the claim table doesn't exist yet — create and retry
            cur.execute("IF SCHEMA_ID('Bookings') IS NULL EXEC('CREATE SCHEMA Bookings')")
            cur.execute(
                "IF OBJECT_ID('Bookings.StripeFinalized') IS NULL "
                "CREATE TABLE Bookings.StripeFinalized ("
                "SessionID NVARCHAR(255) NOT NULL PRIMARY KEY, "
                "FinalizedAt DATETIME2 NOT NULL)"
            )
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
    # ONE critical step: create the calendar appointment in-process. (This
    # used to HTTP-POST to this same function app's /api/calendar-book, which
    # starves the Python worker that is waiting on it — the request hangs
    # until the platform kills it.) If it fails, release the claim so a
    # Stripe redelivery or page refresh can retry cleanly.
    try:
        from services.bookings import BookingsClient
        from services.calendar import calculate_buffers
        from services.datetime_utils import normalize_to_utc

        start_time = normalize_to_utc(meta.get("appointmentStart"))
        try:
            duration_minutes = max(30, min(int(float(meta.get("duration", "60"))), 720))
        except (TypeError, ValueError):
            duration_minutes = 60
        buffers = calculate_buffers(start_time, duration_minutes)
        appointment = BookingsClient().create_appointment(
            customer_data={
                "name": meta.get("customerName"),
                "email": customer_email,
                "phone": meta.get("customerPhone"),
                "pickup": meta.get("pickup"),
                "dropoff": meta.get("dropoff"),
                "notes": "Payment Method: Stripe (paid)",
            },
            start_dt=buffers["buffer_start"],
            end_dt=buffers["buffer_end"],
            service_id=os.environ.get("MS_BOOKINGS_SERVICE_ID", "dc16877c-160d-436e-b53b-52ae6f419604"),
        )
        event_id = appointment.get("id")
    except Exception as booking_err:
        logging.error(f"Calendar booking failed for {session_id}: {booking_err}")
        _release_claim(session_id)
        raise  # caller returns an error / Stripe retries

    # Success with no eventId is a soft failure — treat it as a failed booking,
    # not a success, so we don't record a non-booking and strand the claim.
    if not event_id:
        logging.error(f"Calendar booking returned no eventId for {session_id}")
        _release_claim(session_id)
        raise RuntimeError(f"create_appointment returned no event id for {session_id}")

    # Scheduled-return round trip: book the return leg as its own appointment.
    # Best-effort — the outbound is already booked, so don't fail the flow
    # (and don't release the claim) if only the return leg fails.
    return_start = meta.get("returnStart")
    if return_start:
        try:
            ret_buffers = calculate_buffers(normalize_to_utc(return_start), duration_minutes)
            BookingsClient().create_appointment(
                customer_data={
                    "name": meta.get("customerName"),
                    "email": customer_email,
                    "phone": meta.get("customerPhone"),
                    "pickup": meta.get("dropoff"),
                    "dropoff": meta.get("pickup"),
                    "notes": "Return leg — Payment Method: Stripe (paid)",
                },
                start_dt=ret_buffers["buffer_start"],
                end_dt=ret_buffers["buffer_end"],
                service_id=os.environ.get("MS_BOOKINGS_SERVICE_ID", "dc16877c-160d-436e-b53b-52ae6f419604"),
            )
        except Exception as ret_err:
            logging.error(f"Return-leg booking failed for {session_id} (outbound is booked, schedule manually): {ret_err}")

    # 2. Receipt email + DB log, in-process and best-effort: the booking
    #    already exists in the calendar, so a failed email doesn't warrant
    #    releasing the claim. (Previously posted to /api/book, which sent
    #    paid customers the legacy invoice template with payment options.)
    try:
        _send_paid_receipt(session, meta)
    except Exception as email_err:
        logging.warning(f"Receipt email failed (non-fatal): {email_err}")
    try:
        _log_trip(session, meta)
    except Exception as db_err:
        logging.warning(f"DB trip log failed (non-fatal): {db_err}")

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


OWNER_EMAIL = "peter.teehan@costesla.com"


def _log_trip(session, meta):
    import time
    db = DatabaseClient()
    db.save_trip({
        "trip_id": session.id,
        "classification": "Private_Booking",
        "trip_type": "Private",
        "fare": (session.amount_total or 0) / 100.0,
        "timestamp_epoch": time.time(),
        "pickup_place": meta.get("pickup"),
        "dropoff_place": meta.get("dropoff"),
        "raw_text": f"Stripe booking for {meta.get('customerName')} ({meta.get('fareString')})",
    })


def _send_paid_receipt(session, meta):
    """Paid receipt for a Stripe checkout booking — no payment options, no
    'pick a slot' instructions (the legacy /api/book template is for invoices)."""
    from services.datetime_utils import format_local_time, normalize_to_utc

    name = meta.get("customerName", "Customer")
    email = meta.get("customerEmail")
    if not email:
        logging.warning(f"No customer email on session {session.id} — skipping receipt")
        return

    amount_paid = (session.amount_total or 0) / 100.0
    pickup = meta.get("pickup", "N/A")
    dropoff = meta.get("dropoff", "N/A")
    phone = meta.get("customerPhone", "N/A")

    pickup_time = "To be scheduled"
    raw_time = meta.get("appointmentStart")
    if raw_time:
        try:
            pickup_time = format_local_time(normalize_to_utc(raw_time))
        except Exception:
            pickup_time = raw_time

    return_row = ""
    raw_return = meta.get("returnStart")
    if raw_return:
        try:
            return_fmt = format_local_time(normalize_to_utc(raw_return))
        except Exception:
            return_fmt = raw_return
        return_row = f'<tr><td style="padding: 6px 0; font-size: 14px; color: #666666;">Return Pickup</td><td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{return_fmt}</td></tr>'

    booking_id = session.id[-8:].upper()

    # Cabin-access token (same behavior as the invoice flow)
    cabin_block = ""
    try:
        from datetime import timedelta
        token_expiry = None
        if raw_time:
            token_expiry = normalize_to_utc(raw_time) + timedelta(hours=6)
        cabin_token = DatabaseClient().create_cabin_token(session.id, expires_at=token_expiry)
        site_url = os.environ.get("SITE_URL", "https://www.costesla.com")
        cabin_block = f"""
        <div style="background: #000000; padding: 20px; border-radius: 8px; margin: 0 0 25px; text-align: center;">
            <p style="margin: 0 0 8px; font-size: 16px; font-weight: bold; color: #ffffff;">🚗 Cabin Controls</p>
            <p style="margin: 0 0 14px; font-size: 13px; color: #aaaaaa;">
                Control the climate, seat heaters, and trunk. Use the secure link below or enter your personal access code manually.
            </p>
            <a href="{site_url}/cabin?token={cabin_token}" style="display: inline-block; padding: 12px 28px; background: #ffffff; color: #000000; font-weight: bold; font-size: 14px; border-radius: 6px; text-decoration: none;">Open Cabin Controls →</a>
            <p style="margin: 15px 0 0; font-size: 11px; color: #666666;">Your Personal Access Code:</p>
            <p style="margin: 5px 0 0; font-size: 24px; font-weight: bold; color: #ffffff; letter-spacing: 2px;">{cabin_token}</p>
        </div>
        """
    except Exception as e:
        logging.warning(f"Cabin token generation failed (omitting from receipt): {e}")

    html = f"""
    <html>
    <body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background: #f4f4f4;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f4f4;">
            <tr><td align="center" style="padding: 20px 10px;">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <tr>
                        <td style="background-color: #000000; color: #ffffff; padding: 30px 20px; text-align: center;">
                            <h1 style="margin: 0; font-size: 20px; font-weight: bold;">COS TESLA LLC</h1>
                            <p style="margin: 5px 0 0; color: #aaaaaa; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Powered by: SummitOS</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 30px 20px;">
                            <p style="margin: 0 0 8px; font-size: 18px; font-weight: bold; color: #16a34a;">✓ Payment received — booking confirmed</p>
                            <p style="margin: 0 0 20px; font-size: 16px; color: #333333;">Hello {name},</p>
                            <p style="margin: 0 0 25px; font-size: 14px; color: #666666; line-height: 1.5;">
                                Thank you for choosing COS Tesla. Your card payment of <strong>${amount_paid:,.2f}</strong> was processed successfully and your trip is booked. No further action is needed.
                            </p>
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                <tr><td colspan="2" style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Trip Details</td></tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Confirmation #</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{booking_id}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Customer Phone</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{phone}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Pickup Time</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{pickup_time}</td>
                                </tr>
                                {return_row}
                                <tr><td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Pickup Location</td></tr>
                                <tr><td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{pickup}</td></tr>
                                <tr><td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Dropoff Location</td></tr>
                                <tr><td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{dropoff}</td></tr>
                                <tr>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; border-top: 2px solid #000000;">Total Paid</td>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; text-align: right; border-top: 2px solid #000000;">${amount_paid:,.2f}</td>
                                </tr>
                            </table>
                            {cabin_block}
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #f5f5f5; padding: 25px 20px; text-align: center;">
                            <p style="margin: 0 0 5px; font-size: 14px; font-weight: bold; color: #333333;">COS Tesla LLC</p>
                            <p style="margin: 0 0 10px; font-size: 11px; color: #666666;">Powered by SummitOS</p>
                            <p style="margin: 0 0 15px; font-size: 12px; color: #888888;">
                                Support: <a href="mailto:{OWNER_EMAIL}" style="color: #06b6d4; text-decoration: none;">{OWNER_EMAIL}</a>
                            </p>
                            <p style="margin: 0; font-size: 11px; color: #999999;">Driven by Precision | COS Tesla LLC</p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """

    graph = GraphClient()
    graph.send_mail(email, f"Receipt & Booking Confirmation: {booking_id}", html)
    graph.send_mail(OWNER_EMAIL, f"New PAID Booking: {name} - ${amount_paid:,.2f}", html)
    logging.info(f"Paid receipt sent to {email} for session {session.id}")

