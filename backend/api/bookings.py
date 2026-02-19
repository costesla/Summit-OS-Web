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
from services.datetime_utils import normalize_to_utc

bp = func.Blueprint()

@bp.route(route="calendar-availability", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_availability(req: func.HttpRequest) -> func.HttpResponse:
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
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="calendar-book", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_book(req: func.HttpRequest) -> func.HttpResponse:
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

        start_time = parser.parse(appt_start)
        buffers = calculate_buffers(start_time, int(req_body.get('duration', 60)))
        
        # Import BookingsClient
        from services.bookings import BookingsClient
        
        # Create booking via Microsoft Bookings API
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
                service_id=service_id
            )
            logging.info(f"Appointment created successfully: {appointment.get('id')}")
        except Exception as inner_e:
            logging.error(f"Inner Booking Error: {inner_e}")
            raise inner_e
        
        return func.HttpResponse(
            json.dumps({"success": True, "eventId": appointment.get('id')}),
            status_code=200,
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
        
        trip_data = {
            "trip_id": req_body.get('bookingId') or f"P-{int(time.time())}",
            "classification": "Private_Booking",
            "fare": price,
            "timestamp_epoch": time.time(),
            "raw_text": f"Booking for {name}"
        }
        db.save_trip(trip_data)
        return func.HttpResponse(json.dumps({"status": "success"}), status_code=200)
    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)
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
        from datetime import datetime
        
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
            
        booking_id = f"R-{int(time.time())}"

        # Generate cabin access token (valid 24h)
        try:
            db_early = DatabaseClient()
            cabin_token = db_early.create_cabin_token(booking_id, valid_hours=24)
        except Exception:
            import secrets
            cabin_token = str(secrets.randbelow(900000) + 100000)  # fallback: 6-digit code

        site_url = os.environ.get("SITE_URL", "https://gentle-plant-0f873710f.4.azurestaticapps.net")
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
                                    <h1 style="margin: 0; font-size: 24px; font-weight: bold;">SummitOS LLC</h1>
                                    <p style="margin: 5px 0 0; color: #aaaaaa; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Trip Confirmation</p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 30px 20px;">
                                    <p style="margin: 0 0 20px; font-size: 16px; color: #333333;">Hello {name},</p>
                                    <p style="margin: 0 0 25px; font-size: 14px; color: #666666; line-height: 1.5;">
                                        Thank you for choosing SummitOS. Your booking has been confirmed. Please review the details below:
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
                                                
                                                <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💵 Cash</p>
                                                <p style="margin: 0; padding-left: 20px;">
                                                    Pay your driver directly at pickup or dropoff
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
                                    <p style="margin: 0 0 5px; font-size: 14px; font-weight: bold; color: #333333;">SummitOS LLC</p>
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
        
        # Send mail via Graph
        graph = GraphClient()
        # 1. To Customer
        graph.send_mail(email, f"Trip Receipt: {booking_id}", html)
        # 2. To Admin
        graph.send_mail("peter.teehan@costesla.com", f"New Booking: {name} - {price}", html)
        
        # Log to Database
        db = DatabaseClient()
        try:
            db.save_trip({
                "trip_id": booking_id,
                "classification": "Private_Booking",
                "fare": float(price.replace('$', '').replace(',', '')) if '$' in price else 0,
                "timestamp_epoch": time.time(),
                "raw_text": f"Booking for {name} from {pickup} to {dropoff}"
            })
        except:
            pass
            
        return func.HttpResponse(
            json.dumps({"success": True, "message": "Booking confirmed & Receipt Sent"}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Booking Bridge Error: {e}")
        return func.HttpResponse(json.dumps({"success": False, "error": str(e)}), status_code=500)
