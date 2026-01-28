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

bp = func.Blueprint()

@bp.route(route="calendar-availability", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_availability(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Calendar availability requested via Blueprint")
    try:
        date_param = req.params.get('date')
        if not date_param:
            return func.HttpResponse("Missing date", status_code=400)
            
        target_date = parser.parse(date_param)
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
                evt_start = parser.parse(event['start']['dateTime'])
                evt_end = parser.parse(event['end']['dateTime'])
                
                # Normalize timezones
                if evt_start.tzinfo and buf_start.tzinfo is None:
                    buf_start = buf_start.replace(tzinfo=evt_start.tzinfo)
                    buf_end = buf_end.replace(tzinfo=evt_start.tzinfo)

                if time_ranges_overlap(buf_start, buf_end, evt_start, evt_end):
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
        appt_start = req_body.get('appointmentStart')
        pickup = req_body.get('pickup')
        dropoff = req_body.get('dropoff')

        start_time = parser.parse(appt_start)
        buffers = calculate_buffers(start_time, int(req_body.get('duration', 60)))
        
        graph = GraphClient()
        subject = f"Private Trip: {pickup} -> {dropoff}"
        body = f"Customer: {name}\nEmail: {email}\nPickup: {pickup}\nDropoff: {dropoff}"
        
        event = graph.create_calendar_event(
            subject=subject,
            body=body,
            start_dt=buffers['buffer_start'],
            end_dt=buffers['buffer_end'],
            location=pickup,
            attendee_email=email
        )
        
        return func.HttpResponse(
            json.dumps({"success": True, "eventId": event.get('id')}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
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
        booking_id = f"R-{int(time.time())}"
        
        # Build HTML
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; border-top: 5px solid #000;">
                <h2>SummitOS Receipt</h2>
                <p>Hello {name},</p>
                <p>Thank you for choosing SummitOS. Here is your trip summary:</p>
                <div style="background: #f9f9f9; padding: 15px; border-radius: 5px;">
                    <p><strong>Pickup:</strong> {pickup}</p>
                    <p><strong>Dropoff:</strong> {dropoff}</p>
                    <p><strong>Total:</strong> {price}</p>
                    <p><strong>Booking ID:</strong> #{booking_id}</p>
                </div>
                <p style="font-size: 12px; color: #888; margin-top: 20px;">
                    Driven by Precision | COS Tesla LLC
                </p>
            </div>
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
