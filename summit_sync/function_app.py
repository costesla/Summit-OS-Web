import logging
import time
import datetime
import os
import json
import traceback
import sys
import azure.functions as func

app = func.FunctionApp()

def _env_snapshot():
    try:
        import platform
        return {
            "python": sys.version,
            "platform": platform.platform(),
            "path_entries": len(sys.path),
            "site_packages_hint": [p for p in sys.path if "site-packages" in p][:3],
        }
    except Exception:
        return {}

def _versions():
    versions = {}
    for name in ("azure.storage.blob", "azure.identity", "msrest", "requests", "pyodbc", "azure.core"):
        try:
            m = __import__(name, fromlist=['*'])
            versions[name] = getattr(m, "__version__", "unknown")
        except Exception as e:
            versions[name] = f"IMPORT FAIL: {e.__class__.__name__}: {e}"
    return versions

@app.route(route="process-blob", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_blob_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP endpoint that processes a blob URL.
    Diagnostic wrapper included.
    """
    logging.info("HTTP trigger: process-blob invoked")
    
    try:
        # 1. Parse request
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )
            
        blob_url = req_body.get('blob_url')
        if not blob_url:
            return func.HttpResponse(
                json.dumps({"error": "Missing blob_url parameter"}),
                status_code=400,
                mimetype="application/json"
            )

        # 2. Log Environment Snapshot
        diag_info = {
            "env": _env_snapshot(),
            "versions": _versions()
        }
        logging.info(f"Diagnostic Snapshot: {json.dumps(diag_info)}")

        # 3. Late Imports to isolate failures
        logging.info("Attempting library imports...")
        from lib.ocr import OCRClient
        from lib.tessie import TessieClient
        from lib.database import DatabaseClient
        
        logging.info(f"Processing blob: {blob_url}")
        
        # Extract Block and Trip context from URL
        from urllib.parse import unquote
        import re
        decoded_url = unquote(blob_url)
        block_match = re.search(r"Block\s?(\d+)", decoded_url, re.IGNORECASE)
        trip_match = re.search(r"Trip\s?(\d+)", decoded_url, re.IGNORECASE)
        
        block_name = f"Block {block_match.group(1)}" if block_match else "Unknown Block"
        trip_id = f"Trip {trip_match.group(1)}" if trip_match else "Unknown Trip"
        
        # Use current time as event time
        timestamp_epoch = time.time()

        # OCR & Classification
        ocr = OCRClient()
        raw_text = ocr.extract_text(blob_url)
        
        if not raw_text:
            raise Exception("OCR returned no text. Check if the blob is accessible and correctly formatted.")

        classification = ocr.classify_image(raw_text)
        logging.info(f"Classification result: {classification}")

        trip_data = {
            "block_name": block_name,
            "trip_id": trip_id,
            "classification": classification,
            "source_url": blob_url,
            "timestamp_epoch": timestamp_epoch,
            "raw_text": raw_text[:500]
        }

        # Routing Logic
        if classification == "Uber_Core":
            parsed_data = ocr.parse_ubertrip(raw_text)
            trip_data.update(parsed_data)
        elif classification == "Expense":
            trip_data["type"] = "Business Expense"
        else:
            trip_data["fare"] = 20.00
            trip_data["tip"] = 0.00
            trip_data["payment_method"] = "Venmo" if "Venmo" in raw_text else "Pending"

        # Enrich with Tessie
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if vin:
            is_private = (classification != "Uber_Core") or ("Venmo" in raw_text)
            drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
            if drive:
                trip_data['tessie_drive_id'] = drive.get('id')
                trip_data['tessie_distance'] = drive.get('distance_miles')
                trip_data['tessie_duration'] = drive.get('duration_minutes')
                trip_data['start_location'] = drive.get('starting_address')
                trip_data['end_location'] = drive.get('ending_address')

        # Save to Database
        db = DatabaseClient()
        db.save_trip(trip_data)

        # Handle Contextual Data (Weather, etc.)
        if classification == "Environmental_Context":
            weather_data = ocr.parse_weather(raw_text)
            weather_data["source_url"] = blob_url
            db.save_weather(weather_data)
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "trip_id": trip_id,
                "classification": classification,
                "diagnostics": diag_info
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"FATAL ERROR in process-blob: {str(e)}\n{tb}")
        return func.HttpResponse(
            json.dumps({
                "error": str(e),
                "traceback": tb,
                "diagnostics": _env_snapshot() # Limited diag on crash
            }),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="sql-probe", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def sql_probe(req: func.HttpRequest) -> func.HttpResponse:
    """
    SQL connectivity test probe
    """
    logging.info("SQL probe endpoint invoked")
    try:
        import pyodbc
        conn_str = os.environ.get("SQL_CONNECTION_STRING")
        with pyodbc.connect(conn_str, timeout=10) as conn:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("INSERT INTO dbo._probe (note) VALUES (?);", "hardening check")
            cur.execute("SELECT TOP 1 id, stamp, note FROM dbo._probe ORDER BY id DESC;")
            row = cur.fetchone()
            return func.HttpResponse(
                json.dumps({"status": "success", "last_probe_id": row[0]}),
                status_code=200,
                mimetype="application/json"
            )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
@app.route(route="dashboard-summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard_summary(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns a unified summary for the Command Center:
    - Daily Revenue & Trip KPIs
    - Recent Weather Context
    - Live Tessie Telematics
    """
    logging.info("Dashboard summary requested")
    
    try:
        from lib.database import DatabaseClient
        from lib.tessie import TessieClient
        
        db = DatabaseClient()
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        
        # 1. Fetch Daily KPIs
        query = "SELECT TOP 1 * FROM v_DailyKPIs WHERE [Date] = CAST(GETDATE() AS DATE)"
        daily_stats = db.execute_query_with_results(query)
        stats = daily_stats[0] if daily_stats else {"TotalEarnings": 0, "TotalTips": 0, "TripCount": 0}
        
        # 2. Fetch Latest Weather
        weather_query = "SELECT TOP 1 Temperature_F, Condition FROM WeatherLog ORDER BY timestamp DESC"
        weather_data = db.execute_query_with_results(weather_query)
        weather = weather_data[0] if weather_data else {"Temperature_F": "N/A", "Condition": "N/A"}
        
        # 3. Fetch Live Tessie State
        vehicle_state = tessie.get_vehicle_state(vin) if vin else None
        telematics = {}
        if vehicle_state:
            # Extract high-level details for the dashboard
            charge_state = vehicle_state.get('charge_state', {})
            drive_state = vehicle_state.get('drive_state', {})
            telematics = {
                "battery_level": charge_state.get('battery_level'),
                "charge_limit_soc": charge_state.get('charge_limit_soc'),
                "charging_state": charge_state.get('charging_state'),
                "latitude": drive_state.get('latitude'),
                "longitude": drive_state.get('longitude'),
                "speed": drive_state.get('speed'),
                "power": drive_state.get('power'),
                "timestamp": vehicle_state.get('last_state_received')
            }

        response_data = {
            "stats": stats,
            "weather": weather,
            "telematics": telematics,
            "server_time": datetime.datetime.now().isoformat()
        }
        
        return func.HttpResponse(
            json.dumps(response_data, default=str),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error in dashboard_summary: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
@app.route(route="log-private-trip", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def log_private_trip(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP endpoint to log a private booking from the website directly to SQL.
    """
    logging.info("Remote booking sync requested")
    try:
        req_body = req.get_json()
        from lib.database import DatabaseClient
        db = DatabaseClient()
        
        # Extract fields from Next.js payload
        booking_id = req_body.get('bookingId')
        name = req_body.get('name')
        email = req_body.get('email')
        pickup = req_body.get('pickup')
        dropoff = req_body.get('dropoff')
        price_str = req_body.get('price', '$0')
        
        # Parse price (remove $ and convert to float)
        import re
        price = 0.0
        match = re.search(r"[\d.]+", price_str)
        if match:
            price = float(match.group())

        # Trip details (distance/time)
        details = req_body.get('tripDetails', {})
        dist = float(details.get('dist', 0))
        dur = float(details.get('time', 0))

        trip_data = {
            "trip_id": booking_id,
            "classification": "Private_Booking",
            "start_location": pickup,
            "end_location": dropoff,
            "fare": price,
            "driver_total": price, # For private bookings, it's 100% earnings
            "distance_miles": dist,
            "duration_minutes": dur,
            "payment_method": "Website Booking",
            "raw_text": f"Private Booking: {name} ({email})",
            "timestamp_epoch": time.time()
        }

        db.save_trip(trip_data)

        return func.HttpResponse(
            json.dumps({"status": "success", "bookingId": booking_id}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error in log_private_trip: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
@app.route(route="calendar-availability", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_availability(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns available time slots for a given date.
    Integrates with Microsoft Graph to check for conflicts.
    """
    logging.info("Calendar availability requested")
    
    try:
        from lib.calendar import generate_time_slots_for_day, calculate_buffers, time_ranges_overlap
        from lib.graph import GraphClient
        from dateutil import parser
        
        # 1. Parse Date Param
        date_param = req.params.get('date')
        if not date_param:
            return func.HttpResponse(
                json.dumps({"error": "Date parameter required"}),
                status_code=400, 
                mimetype="application/json"
            )
            
        try:
            target_date = parser.parse(date_param)
        except Exception:
            return func.HttpResponse(
                json.dumps({"error": "Invalid date format"}),
                status_code=400,
                mimetype="application/json"
            )

        # 2. Generate Slots
        all_slots = generate_time_slots_for_day(target_date)
        
        # 3. Fetch Graph Events
        graph = GraphClient()
        existing_events = graph.get_calendar_events(target_date)
        
        # 4. Filter Availability
        available_slots = []
        for slot_start in all_slots:
            buffers = calculate_buffers(slot_start)
            buf_start = buffers["buffer_start"]
            buf_end = buffers["buffer_end"]
            
            has_conflict = False
            for event in existing_events:
                # Graph API returns ISO strings in event['start']['dateTime']
                evt_start = parser.parse(event['start']['dateTime'])
                evt_end = parser.parse(event['end']['dateTime'])
                
                # Normalize timezones (naive vs aware comparison fix)
                # Ideally convert everything to UTC or comparison-compatible
                if evt_start.tzinfo and buf_start.tzinfo is None:
                    buf_start = buf_start.replace(tzinfo=evt_start.tzinfo)
                    buf_end = buf_end.replace(tzinfo=evt_start.tzinfo)
                elif buf_start.tzinfo and evt_start.tzinfo is None:
                    evt_start = evt_start.replace(tzinfo=buf_start.tzinfo)
                    evt_end = evt_end.replace(tzinfo=buf_start.tzinfo)

                if time_ranges_overlap(buf_start, buf_end, evt_start, evt_end):
                    has_conflict = True
                    break
            
            if not has_conflict:
                available_slots.append({
                    "start": slot_start.isoformat(),
                    "end": buffers["appointment_end"].isoformat()
                })

        return func.HttpResponse(
            json.dumps({
                "success": True, 
                "date": target_date.isoformat(), 
                "slots": available_slots
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error in calendar_availability: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="calendar-book", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def calendar_book(req: func.HttpRequest) -> func.HttpResponse:
    """
    Creates a calendar appointment with buffers.
    """
    logging.info("Calendar booking requested")
    
    try:
        from lib.calendar import calculate_buffers, get_hours_for_day
        from lib.graph import GraphClient
        from dateutil import parser
        
        req_body = req.get_json()
        
        # Extract fields
        customer_name = req_body.get('customerName')
        customer_email = req_body.get('customerEmail')
        customer_phone = req_body.get('customerPhone')
        pickup = req_body.get('pickup')
        dropoff = req_body.get('dropoff')
        appointment_start_str = req_body.get('appointmentStart')
        duration = int(req_body.get('duration', 60))
        price = req_body.get('price')
        passengers = req_body.get('passengers')

        # Validation
        if not all([customer_name, customer_email, appointment_start_str, pickup, dropoff]):
             return func.HttpResponse(
                json.dumps({"success": False, "error": "Missing required fields"}),
                status_code=400,
                mimetype="application/json"
            )

        start_time = parser.parse(appointment_start_str)

        # Calculate Buffers
        # calculate_buffers returns dict with datetime objects
        buffers = calculate_buffers(start_time, duration)
        
        buffer_start = buffers['buffer_start']
        appointment_end = buffers['appointment_end']
        buffer_end = buffers['buffer_end']
        
        # Create Calendar Event
        graph = GraphClient()
        subject = f"Private Trip: {pickup} -> {dropoff}"
        body = f"""
        <h2>Private Trip Booking</h2>
        <p><strong>Customer:</strong> {customer_name}</p>
        <p><strong>Email:</strong> {customer_email}</p>
        <p><strong>Phone:</strong> {customer_phone}</p>
        <p><strong>Passengers:</strong> {passengers}</p>
        <p><strong>Pickup:</strong> {pickup}</p>
        <p><strong>Dropoff:</strong> {dropoff}</p>
        <p><strong>Price:</strong> {price}</p>
        <hr>
        <p><strong>Appointment Time:</strong> {start_time.isoformat()}</p>
        <p><strong>Buffer Start (Arrival):</strong> {buffer_start.isoformat()}</p>
        <p><strong>Buffer End (Break):</strong> {buffer_end.isoformat()}</p>
        """
        
        # We book the FULL buffer duration in Outlook to block the time
        event = graph.create_calendar_event(
            subject=subject,
            body=body,
            start_dt=buffer_start,
            end_dt=buffer_end,
            location=pickup,
            attendee_email=customer_email
        )
        
        logging.info(f"Calendar event created: {event.get('id')}")

        return func.HttpResponse(
            json.dumps({
                "success": True, 
                "eventId": event.get('id'),
                "appointmentStart": start_time.isoformat(),
                "bufferStart": buffer_start.isoformat(),
                "bufferEnd": buffer_end.isoformat()
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error in calendar_book: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="flight-status", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def flight_status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns flight status from AviationStack (or demo data).
    """
    logging.info("Flight status requested")
    
    try:
        from lib.flight import AviationStackClient
        
        req_body = req.get_json()
        flight_number = req_body.get('flightNumber')
        
        if not flight_number:
             return func.HttpResponse(
                json.dumps({"success": False, "error": "Missing flight number"}),
                status_code=400,
                mimetype="application/json"
            )

        client = AviationStackClient()
        data = client.get_flight_status(flight_number)
        
        if data:
             return func.HttpResponse(
                json.dumps({"success": True, "data": data}),
                status_code=200,
                mimetype="application/json"
            )
        else:
             return func.HttpResponse(
                json.dumps({"success": False, "error": "Flight not found"}),
                status_code=404,
                mimetype="application/json"
            )

    except Exception as e:
        logging.error(f"Error in flight_status: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="vehicle-location", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_location(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns public vehicle telemetry (sanitized).
    """
    logging.info("Vehicle location requested")
    
    try:
        from lib.tessie import TessieClient
        
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        
        if not vin:
             return func.HttpResponse(
                json.dumps({"error": "TESSIE_VIN not configured"}),
                status_code=500,
                mimetype="application/json"
            )

        data = tessie.get_public_state(vin)
        
        # Determine status code based on data availability
        # Note: Frontend handles null/privacy gracefully
        if not data:
             return func.HttpResponse(
                json.dumps({"error": "Vehicle not reachable"}),
                status_code=404,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps(data), # Helper returns dict directly
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error in vehicle_location: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


