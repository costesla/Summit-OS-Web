import logging
import azure.functions as func
import json
import time
import os
import traceback
from dateutil import parser
from services.calendar import generate_time_slots_for_day, calculate_buffers, time_ranges_overlap
from services.graph import GraphClient
from services.database import DatabaseClient
from services.flight import AviationStackClient
from services.datetime_utils import normalize_to_utc, utc_to_local
from services.invoice import create_stripe_payment_link, build_invoice_id
from services.auth_guard import cors_headers as _get_cors

bp = func.Blueprint()

def _cors_headers(req: func.HttpRequest = None):
    """CORS headers with allow-listed origin reflection (no wildcard)."""
    if req is not None:
        return _get_cors(req)
    # Fallback for call sites that don't pass req (legacy compatibility)
    return {
        "Access-Control-Allow-Origin": "https://www.costesla.com",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

@bp.route(route="calendar-availability", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_availability(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    logging.info("Calendar availability requested via Blueprint")
    try:
        date_param = req.params.get('date')
        if not date_param:
            return func.HttpResponse("Missing date", status_code=400)
            
        target_date = normalize_to_utc(date_param)
        all_slots = generate_time_slots_for_day(target_date)
        
        graph = GraphClient()
        existing_events = graph.get_calendar_events(target_date)
        
        available_slots = []
        for slot_start in all_slots:
            buffers = calculate_buffers(slot_start)
            buf_start = buffers["buffer_start"]
            buf_end = buffers["buffer_end"]
            
            has_conflict = False
            for event in existing_events:
                evt_start = normalize_to_utc(event['start']['dateTime'])
                evt_end = normalize_to_utc(event['end']['dateTime'])
                
                # Buffer starts/ends are already normalized (UTC) because all_slots are based on target_date (UTC)
                # But let's be absolutely explicit to prevent any regression
                buf_start_utc = normalize_to_utc(buf_start)
                buf_end_utc = normalize_to_utc(buf_end)

                if time_ranges_overlap(buf_start_utc, buf_end_utc, evt_start, evt_end):
                    has_conflict = True
                    break
            
            if not has_conflict:
                available_slots.append({
                    "start": slot_start.isoformat(),
                    "end": buffers["appointment_end"].isoformat()
                })

        return func.HttpResponse(
            json.dumps({"success": True, "slots": available_slots}),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="calendar-book", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_book(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    logging.info("Calendar booking requested via Blueprint")
    try:
        req_body = req.get_json()
        name = req_body.get('customerName')
        email = req_body.get('customerEmail')
        phone = req_body.get('customerPhone', '')
        appt_start = req_body.get('appointmentStart')
        pickup = req_body.get('pickup')
        dropoff = req_body.get('dropoff')
        passengers = req_body.get('passengers', 1)
        session_id = req_body.get('sessionId')  # Stripe session_id for idempotency

        start_time = parser.parse(appt_start)
        buffers = calculate_buffers(start_time, int(req_body.get('duration', 60)))
        
        from services.bookings import BookingsClient
        
        bookings = BookingsClient()
        service_id = os.environ.get('MS_BOOKINGS_SERVICE_ID', 'dc16877c-160d-436e-b53b-52ae6f419604')
        
        customer_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'pickup': pickup,
            'dropoff': dropoff
        }
        
        logging.info(f"Invoking BookingsClient.create_appointment for {email}")
        try:
            appointment = bookings.create_appointment(
                customer_data=customer_data,
                start_dt=buffers['buffer_start'],
                end_dt=buffers['buffer_end'],
                service_id=service_id,
                transaction_id=session_id,  # Graph rejects duplicate transactionIds with 409
            )
            logging.info(f"Appointment created successfully: {appointment.get('id')}")
        except Exception as inner_e:
            error_str = str(inner_e)

            # Graph returns 409 when transactionId was already used — this IS
            # the idempotency working.  Look up the existing eventId from our
            # cache table and return it so finalize gets a valid eventId.
            if session_id and "409" in error_str:
                logging.info(f"Graph 409 for transactionId {session_id} — looking up existing event")
                # The winner may not have written its cache row yet.
                # Retry briefly (3 × 500ms) to cover the timing window.
                import time as _time
                for attempt in range(3):
                    try:
                        db = DatabaseClient()
                        conn = db.get_connection()
                        if conn:
                            cur = conn.cursor()
                            cur.execute(
                                "SELECT EventId FROM Bookings.CalendarIdempotency WHERE IdempotencyKey = ?",
                                (session_id,),
                            )
                            row = cur.fetchone()
                            cur.close()
                            conn.close()
                            if row and row[0]:
                                logging.info(f"Calendar-book dedupe: returning cached eventId {row[0]} (attempt {attempt + 1})")
                                return func.HttpResponse(
                                    json.dumps({"success": True, "eventId": row[0], "deduplicated": True}),
                                    status_code=200,
                                    headers=_cors_headers(),
                                    mimetype="application/json"
                                )
                    except Exception as lookup_err:
                        logging.warning(f"CalendarIdempotency lookup failed (attempt {attempt + 1}): {lookup_err}")
                    if attempt < 2:
                        _time.sleep(0.5)

                # 409 but no cached eventId after retries — Graph blocked the
                # duplicate but we don't have the original ID.  Return error
                # so finalize can release the claim and Stripe retries.
                logging.error(f"Graph 409 but no cached eventId for {session_id} after 3 attempts")

            logging.error(f"Inner Booking Error: {inner_e}")
            raise inner_e
        
        event_id = appointment.get('id')

        # ── Cache the sessionId → eventId mapping ─────────────────────
        # This is a plain lookup cache, not a lock.  Graph's transactionId
        # is the serialization point; this table just lets us return the
        # eventId on a 409 without querying Graph for it.
        if session_id and event_id:
            try:
                db = DatabaseClient()
                conn = db.get_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO Bookings.CalendarIdempotency (IdempotencyKey, EventId, CreatedAt) "
                        "VALUES (?, ?, GETUTCDATE())",
                        (session_id, event_id),
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
            except Exception as cache_err:
                # Non-fatal: the event was created, we just can't cache
                # the mapping.  A future 409 won't find it, but the event
                # still exists and finalize will succeed.
                logging.warning(f"Failed to cache calendar idempotency mapping: {cache_err}")

        return func.HttpResponse(
            json.dumps({"success": True, "eventId": event_id}),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Booking error: {str(e)}")
        logging.error(traceback.format_exc())
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="flight-status", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def flight_status(req: func.HttpRequest) -> func.HttpResponse:
    try:
        fn = req.get_json().get('flightNumber')
        client = AviationStackClient()
        data = client.get_flight_status(fn)
        return func.HttpResponse(
            json.dumps({"success": True, "data": data}),
            status_code=200,
            mimetype="application/json"
        ) if data else func.HttpResponse("Not found", status_code=404)
    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)

@bp.route(route="log-private-trip", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def log_private_trip(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        db = DatabaseClient()
        
        name = req_body.get('name') or req_body.get('customerName') or "Unknown"
        price = req_body.get('fare') or req_body.get('price', 0)
        
        # Parse scheduled pickup time (pickupTime / appointmentStart)
        raw_time = req_body.get('pickupTime') or req_body.get('appointmentStart')
        timestamp_epoch = time.time()
        dt_utc = None
        if raw_time:
            try:
                from services.datetime_utils import normalize_to_utc
                dt_utc = normalize_to_utc(raw_time)
                if dt_utc:
                    timestamp_epoch = dt_utc.timestamp()
                    # Timezone Drift Validation
                    from dateutil.parser import parse
                    parsed_dt = parse(raw_time)
                    if parsed_dt.tzinfo is None:
                        logging.warning(f"TIMEZONE_DRIFT_DETECTED: Inbound naive sync timestamp '{raw_time}' coerced to UTC.")
            except Exception as pe:
                logging.error(f"Failed to parse raw_time for epoch in log_private_trip: {pe}")

        trip_data = {
            "trip_id": req_body.get('bookingId') or f"P-{int(timestamp_epoch)}",
            "classification": "Private_Booking",
            "fare": price,
            "timestamp_epoch": timestamp_epoch,
            "Timestamp_Offer": utc_to_local(dt_utc).strftime("%Y-%m-%d %H:%M:%S") if dt_utc else None,
            "raw_text": f"Booking for {name}"
        }
        db.save_trip(trip_data)
        return func.HttpResponse(json.dumps({"status": "success"}), status_code=200)
    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)
@bp.route(route="unpaid-trips", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def unpaid_trips(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    try:
        date_str = req.params.get("date")  # optional YYYY-MM-DD — scopes to that day
        trips = DatabaseClient().get_unpaid_trips(date_str=date_str)
        return func.HttpResponse(
            json.dumps({"success": True, "trips": trips}),
            status_code=200, headers=_cors_headers(), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"unpaid-trips error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500, headers=_cors_headers(), mimetype="application/json"
        )

@bp.route(route="mark-paid", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def mark_paid(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    try:
        data = req.get_json()
        ride_id = data.get("rideId")
        if not ride_id:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "rideId is required"}),
                status_code=400, headers=_cors_headers(), mimetype="application/json"
            )
        # Allow undo ('Pending') and explicit channels, default Paid
        status = data.get("status", "Paid")
        if status not in ("Paid", "Pending"):
            status = "Paid"
        ok = DatabaseClient().set_payment_status(ride_id, status)
        return func.HttpResponse(
            json.dumps({"success": ok, "rideId": ride_id, "status": status}),
            status_code=200 if ok else 404, headers=_cors_headers(), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"mark-paid error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500, headers=_cors_headers(), mimetype="application/json"
        )

@bp.route(route="book", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def book(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Legacy/Receipt booking bridge hit")
    try:
        data = req.get_json()
        
        # Extract data
        name = data.get('name') or data.get('customerName') or "Customer"
        email = data.get('email') or data.get('customerEmail')
        pickup = data.get('pickup', "N/A")
        dropoff = data.get('dropoff', "N/A")
        price = data.get('price', "$0.00")
        phone = data.get('phone') or data.get('customerPhone') or "N/A"
        
        # Handle Pickup Time formatting
        from services.datetime_utils import format_local_time, normalize_to_utc
        from datetime import datetime, timedelta
        
        # Capture booking time
        booking_time = format_local_time(datetime.utcnow())

        raw_time = data.get('pickupTime') or data.get('appointmentStart')
        if raw_time:
            try:
                dt_utc = normalize_to_utc(raw_time)
                pickup_time = format_local_time(dt_utc)
            except:
                pickup_time = raw_time
        else:
            pickup_time = "To be scheduled"
            
        # Use centralized ID generation
        booking_id = build_invoice_id(name, pickup_time)

        # Generate Stripe Link for all flows to ensure it appears on the receipt
        stripe_url = None
        payment_method = data.get('paymentMethod', 'Venmo')
        try:
            # Format price to float
            import re
            amount_num = float(re.sub(r'[^0-9.]', '', str(price)))
            if amount_num > 0:
                trip_label = f"{pickup} -> {dropoff} ({pickup_time})"
                stripe_url = create_stripe_payment_link(name, email, amount_num, trip_label, invoice_id=booking_id)
        except Exception as se:
            logging.error(f"Failed to generate pre-trip Stripe link: {se}")

        stripe_button_html = ""
        if stripe_url:
            stripe_button_html = f"""
            <tr>
                <td style="padding: 0 0 20px 0;">
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; text-align: center;">
                        <p style="margin: 0 0 12px 0; font-size: 14px; color: #64748b;">Secure Card / Apple Pay</p>
                        <a href="{stripe_url}" style="display: inline-block; padding: 12px 28px; background: #635bff; color: #ffffff; font-weight: bold; font-size: 14px; border-radius: 6px; text-decoration: none;">Pay {price} via Stripe →</a>
                    </div>
                </td>
            </tr>
            """

        # --- NEW: Create Calendar Event for Invoice/Venmo flows ---
        # (Paid flow handles this in finalize-booking calling calendar-book)
        # Block the calendar for the real trip span (drive time + layover/wait),
        # clamped to sane bounds — round trips were only reserving 1 hour.
        try:
            duration_minutes = max(30, min(int(float(data.get('duration', 60))), 720))
        except (TypeError, ValueError):
            duration_minutes = 60

        if payment_method in ["Invoice", "Venmo", "Cash"] and raw_time:
            try:
                from services.bookings import BookingsClient
                bookings = BookingsClient()
                dt_utc = normalize_to_utc(raw_time)

                # Create appointment in calendar
                bookings.create_appointment(
                    customer_data={
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'pickup': pickup,
                        'dropoff': dropoff,
                        'notes': f"Payment Method: {payment_method}"
                    },
                    start_dt=dt_utc,
                    end_dt=dt_utc + timedelta(minutes=duration_minutes),
                    service_id=os.environ.get('MS_BOOKINGS_SERVICE_ID', 'dc16877c-160d-436e-b53b-52ae6f419604')
                )
                logging.info(f"Calendar event created for {payment_method} booking: {booking_id}")
            except Exception as cal_err:
                logging.error(f"Failed to create calendar event for {payment_method} booking: {cal_err}")

        # Scheduled-return round trip: the return leg gets its own appointment
        return_start = data.get('returnStart')
        return_time_fmt = None
        if return_start:
            try:
                return_time_fmt = format_local_time(normalize_to_utc(return_start))
            except Exception:
                return_time_fmt = str(return_start)
        if payment_method in ["Invoice", "Venmo", "Cash"] and return_start:
            try:
                from services.bookings import BookingsClient
                ret_utc = normalize_to_utc(return_start)
                BookingsClient().create_appointment(
                    customer_data={
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'pickup': dropoff,
                        'dropoff': pickup,
                        'notes': f"Return leg — Payment Method: {payment_method}"
                    },
                    start_dt=ret_utc,
                    end_dt=ret_utc + timedelta(minutes=duration_minutes),
                    service_id=os.environ.get('MS_BOOKINGS_SERVICE_ID', 'dc16877c-160d-436e-b53b-52ae6f419604')
                )
                logging.info(f"Return-leg calendar event created for booking: {booking_id}")
            except Exception as cal_err:
                logging.error(f"Failed to create return-leg calendar event for {booking_id}: {cal_err}")

        # B5b: driver push notification — best-effort, never blocks the booking.
        # Content-free by design (no customer PII in the payload) — see the
        # matching note in finalize_service.py: the push route is publicly
        # reachable and its principal header is forgeable, so details stay
        # behind the Easy-Auth-gated dashboard.
        try:
            from services.push_sender import notify_driver
            notify_driver(
                title="New booking",
                body="A new booking came in. Tap to view details.",
                url="/driver-dashboard/",
            )
        except Exception as push_err:
            logging.warning(f"Driver push failed (non-fatal): {push_err}")

        # Generate cabin access token
        # Valid from now until 6 hours after the trip starts (ensures access on trip day)
        try:
            db_early = DatabaseClient()
            from datetime import timedelta
            
            # Cabin code lifetime = CABIN_TOKEN_HOURS after the scheduled pickup.
            # If there is no pickup time, create_cabin_token falls back to the
            # same constant (it used to fall back to 24h). This window grants
            # trunk access — see docs/security-notes.md §2a.
            from services.database import CABIN_TOKEN_HOURS
            token_expiry = None
            if raw_time:
                try:
                    dt_utc = normalize_to_utc(raw_time)
                    token_expiry = dt_utc + timedelta(hours=CABIN_TOKEN_HOURS)
                except:
                    pass
            
            cabin_token = db_early.create_cabin_token(booking_id, expires_at=token_expiry)
        except Exception as e:
            logging.warning(f"Failed to create persistent cabin token: {e}")
            import secrets
            cabin_token = str(secrets.randbelow(900000) + 100000)  # fallback: 6-digit code

        site_url = os.environ.get("SITE_URL", "https://www.costesla.com")
        cabin_url = f"{site_url}/cabin?token={cabin_token}"
        html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background: #f4f4f4;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f4f4;">
                <tr>
                    <td align="center" style="padding: 20px 10px;">
                        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            
                            <!-- Header -->
                            <tr>
                                <td style="background-color: #000000; color: #ffffff; padding: 30px 20px; text-align: center;">
                                    <img src="{site_url}/logo.png" alt="COS Tesla Logo" style="display: block; margin: 0 auto 15px; height: 60px; width: auto;" />
                                    <h1 style="margin: 0; font-size: 20px; font-weight: bold;">COS TESLA LLC</h1>
                                    <p style="margin: 5px 0 0; color: #aaaaaa; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Powered by: SummitOS</p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 30px 20px;">
                                    <p style="margin: 0 0 20px; font-size: 16px; color: #333333;">Hello {name},</p>
                                    <p style="margin: 0 0 25px; font-size: 14px; color: #666666; line-height: 1.5;">
                                        Thank you for choosing COS Tesla. Your booking has been confirmed. Please review the details below:
                                    </p>
                                    
                                    <!-- Trip Details -->
                                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                        <tr>
                                            <td colspan="2" style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Trip Details</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; font-size: 14px; color: #666666;">Booking ID</td>
                                            <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">#{booking_id}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; font-size: 14px; color: #666666;">Booking Date</td>
                                            <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{booking_time}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; font-size: 14px; color: #666666;">Customer Phone</td>
                                            <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{phone}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 6px 0; font-size: 14px; color: #666666;">Pickup Time</td>
                                            <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{pickup_time}</td>
                                        </tr>
                                        {f'<tr><td style="padding: 6px 0; font-size: 14px; color: #666666;">Return Pickup</td><td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">{return_time_fmt}</td></tr>' if return_time_fmt else ''}
                                        <tr>
                                            <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Pickup Location</td>
                                        </tr>
                                        <tr>
                                            <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{pickup}</td>
                                        </tr>
                                        <tr>
                                            <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Dropoff Location</td>
                                        </tr>
                                        <tr>
                                            <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{dropoff}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; border-top: 2px solid #000000;">Total</td>
                                            <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; text-align: right; border-top: 2px solid #000000;">{price}</td>
                                        </tr>
                                    </table>
                                    
                                    <!-- Payment Options -->
                                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                        <tr>
                                            <td style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Payment Options</td>
                                        </tr>
                                        {stripe_button_html}
                                        <tr>
                                            <td style="padding: 10px 0; font-size: 14px; color: #666666; line-height: 1.6;">
                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💳 Venmo</p>
                                                <p style="margin: 0 0 15px; padding-left: 20px;">
                                                    Send payment to: <a href="https://www.venmo.com/u/costesla" style="color: #008CFF; text-decoration: none; font-weight: 600;">@costesla</a>
                                                </p>
                                                
                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💜 Zelle</p>
                                                <p style="margin: 0 0 15px; padding-left: 20px;">
                                                    Send to: <strong>peter.teehan@costesla.com</strong><br>
                                                    <span style="font-size: 12px; color: #888;">Recipient: COS TESLA LLC</span>
                                                </p>
                                                
                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">🟢 Cash App</p>
                                                <p style="margin: 0 0 15px; padding-left: 20px;">
                                                    Send payment to: <a href="https://cash.app/$peteteehan" style="color: #00D632; text-decoration: none; font-weight: 600;">$peteteehan</a>
                                                </p>
                                                
                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💵 Cash</p>
                                                <p style="margin: 0 0 15px; padding-left: 20px;">
                                                    Pay your driver directly at pickup or dropoff
                                                </p>

                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">✉️ Pay Later (Post-Trip Invoice)</p>
                                                <p style="margin: 0; padding-left: 20px;">
                                                    A professional invoice will be emailed to you after the trip is completed. Suitable for corporate reimbursements.
                                                </p>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <!-- Cabin Controls -->
                                    <div style="background: #000000; padding: 20px; border-radius: 8px; margin: 0 0 25px; text-align: center;">
                                        <p style="margin: 0 0 8px; font-size: 16px; font-weight: bold; color: #ffffff;">🚗 Cabin Controls</p>
                                        <p style="margin: 0 0 14px; font-size: 13px; color: #aaaaaa;">
                                            Control the climate, seat heaters, and trunk. Use the secure link below or enter your personal access code manually.
                                        </p>
                                        <a href="{cabin_url}" style="display: inline-block; padding: 12px 28px; background: #ffffff; color: #000000; font-weight: bold; font-size: 14px; border-radius: 6px; text-decoration: none;">Open Cabin Controls →</a>
                                        <p style="margin: 15px 0 0; font-size: 11px; color: #666666;">Your Personal Access Code:</p>
                                        <p style="margin: 5px 0 0; font-size: 24px; font-weight: bold; color: #ffffff; letter-spacing: 2px;">{cabin_token}</p>
                                    </div>

                                    <!-- Next Steps -->
                                    <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #06b6d4;">
                                        <p style="margin: 0 0 10px; font-size: 14px; font-weight: bold; color: #0e7490;">📅 Next Steps</p>
                                        <p style="margin: 0; font-size: 13px; color: #164e63; line-height: 1.5;">
                                            Please select your preferred time slot by visiting our booking calendar. 
                                            You will receive a confirmation email once your time is confirmed.
                                        </p>
                                    </div>
                                    
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f5f5f5; padding: 25px 20px; text-align: center;">
                                    <p style="margin: 0 0 5px; font-size: 14px; font-weight: bold; color: #333333;">COS Tesla LLC</p>
                                    <p style="margin: 0 0 10px; font-size: 11px; color: #666666;">Powered by SummitOS</p>
                                    <p style="margin: 0 0 15px; font-size: 12px; color: #888888;">
                                        Support: <a href="mailto:peter.teehan@costesla.com" style="color: #06b6d4; text-decoration: none;">peter.teehan@costesla.com</a>
                                    </p>
                                    <p style="margin: 0; font-size: 11px; color: #999999; line-height: 1.5;">
                                        Driven by Precision | COS Tesla LLC
                                    </p>
                                </td>
                            </tr>
                            
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        if not email:
            logging.warning("No customer email provided — skipping receipt email")
        else:
            # Try Graph API first, fall back to SMTP if it fails
            try:
                graph = GraphClient()
                graph.send_mail(email, f"Trip Receipt: {booking_id}", html)
                graph.send_mail("peter.teehan@costesla.com", f"New Booking: {name} - {price}", html)
                logging.info(f"Receipt email sent via Graph API to {email}")
            except Exception as graph_err:
                logging.warning(f"Graph API email failed ({graph_err}), falling back to SMTP")
                try:
                    import smtplib
                    from email.mime.multipart import MIMEMultipart
                    from email.mime.text import MIMEText
                    smtp_user = os.environ.get("SMTP_USER", "PrivateTrips@costesla.com")
                    smtp_pass = os.environ.get("SMTP_PASS", "")
                    if not smtp_pass:
                        raise Exception("SMTP_PASS not configured in app settings")
                    # Send to customer
                    for to_addr in [email, "peter.teehan@costesla.com"]:
                        msg = MIMEMultipart("alternative")
                        msg["Subject"] = f"Trip Receipt: {booking_id}" if to_addr == email else f"New Booking: {name} - {price}"
                        msg["From"] = f"SummitOS Reservations <{smtp_user}>"
                        msg["To"] = to_addr
                        msg.attach(MIMEText(html, "html"))
                        with smtplib.SMTP("smtp.office365.com", 587) as server:
                            server.ehlo()
                            server.starttls()
                            server.login(smtp_user, smtp_pass)
                            server.sendmail(smtp_user, to_addr, msg.as_string())
                    logging.info(f"Receipt email sent via SMTP fallback to {email}")
                except Exception as smtp_err:
                    logging.error(f"SMTP fallback also failed: {smtp_err}")
        
        # Log to Database
        db = DatabaseClient()
        try:
            # Determine the epoch timestamp of the scheduled pickup time, fallback to time.time()
            timestamp_epoch = time.time()
            dt_utc = None
            if raw_time:
                try:
                    dt_utc = normalize_to_utc(raw_time)
                    if dt_utc:
                        timestamp_epoch = dt_utc.timestamp()
                        # Timezone Drift Validation
                        from dateutil.parser import parse
                        parsed_dt = parse(raw_time)
                        if parsed_dt.tzinfo is None:
                            logging.warning(f"TIMEZONE_DRIFT_DETECTED: Inbound timestamp '{raw_time}' is naive. Coerced to UTC. Verifying offset consistency...")
                except Exception as pe:
                    logging.error(f"Failed to parse raw_time for epoch: {pe}")

            # Create a rich metadata object for the DB
            db_data = data.copy()
            db_data.update({
                "trip_id": booking_id,
                "classification": "Private_Booking",
                "fare": float(price.replace('$', '').replace(',', '')) if '$' in price else 0,
                "timestamp_epoch": timestamp_epoch,
                "Timestamp_Offer": utc_to_local(dt_utc).strftime("%Y-%m-%d %H:%M:%S") if dt_utc else None
            })
            db.save_trip(db_data)
            # Invoice/Cash/Venmo bookings start unpaid; cleared via Mark Paid on the dashboard
            db.set_payment_status(booking_id, "Pending")
        except Exception as db_err:
            logging.error(f"Failed to log booking to DB: {db_err}")
            
        return func.HttpResponse(
            json.dumps({"success": True, "message": "Booking confirmed & Receipt Sent"}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Booking Bridge Error: {e}")
        return func.HttpResponse(json.dumps({"success": False, "error": str(e)}), status_code=500)
