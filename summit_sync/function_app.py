import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import time
import datetime
import os
import json
import traceback
import sys
import azure.functions as func
from lib import datetime_utils

# Enforce 32-bit Python environment
datetime_utils.ensure_32bit_python()

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
            "versions": _versions(),
            "azure_cli": datetime_utils.check_azure_cli(),
            "home_state": datetime_utils.get_home_state()
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

        # Extract suffix from filename
        # Uber_20260128_1030_FD.png
        filename = os.path.basename(decoded_url)
        suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", filename)
        suffix = suffix_match.group(1) if suffix_match else None
        
        logging.info(f"Filename Suffix Detected: {suffix}")

        # OCR & Classification
        ocr = OCRClient()
        raw_text = ocr.extract_text(blob_url)
        
        if not raw_text:
            raise Exception("OCR returned no text. Check if the blob is accessible and correctly formatted.")

        # Default classification
        classification = "Uber_Core" if suffix in ["FD", "ST", "ED", "RD"] else ocr.classify_image(raw_text)
        logging.info(f"Classification result: {classification}")

        trip_data = {
            "block_name": block_name,
            "trip_id": trip_id,
            "classification": classification,
            "source_url": blob_url,
            "timestamp_epoch": timestamp_epoch,
            "raw_text": raw_text[:500],
            "is_cdot_reportable": False # Default Uber trips to False
        }

        # Routing Logic based on Suffix or Class
        if suffix == "RD": # Route Details
             route_data = ocr.parse_route_details(raw_text)
             trip_data["pickup_address_full"] = route_data.get("pickup_address")
             trip_data["dropoff_address_full"] = route_data.get("dropoff_address")
             # Merge basic info too just in case
             basic_data = ocr.parse_ubertrip(raw_text, suffix)
             trip_data.update(basic_data)
             
        elif suffix in ["FD", "ST", "ED"] or classification == "Uber_Core":
             parsed_data = ocr.parse_ubertrip(raw_text, suffix)
             trip_data.update(parsed_data)
             
        elif classification == "Expense":
             trip_data["type"] = "Business Expense"
             # Check for Venmo/Passenger in Expense (Just in case)
             pass_data = ocr.parse_passenger_context(raw_text, ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"])
             if pass_data.get("passenger_firstname"):
                  trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
                  trip_data["classification"] = "Private_Trip"
                  trip_data["is_cdot_reportable"] = True
                  trip_data["payment_method"] = "Venmo"

        else:
             trip_data["fare"] = 20.00
             trip_data["tip"] = 0.00
             
             # Attempt to identify Private Trip Passenger
             STATIC_PASSENGERS = ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"]
             pass_data = ocr.parse_passenger_context(raw_text, STATIC_PASSENGERS)
             
             if pass_data.get("passenger_firstname"):
                  trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
                  trip_data["classification"] = "Private_Trip"
                  trip_data["is_cdot_reportable"] = True
                  trip_data["payment_method"] = pass_data.get("payment_method", "Venmo")
             else:
                  trip_data["payment_method"] = "Venmo" if "Venmo" in raw_text else "Pending"
                  if "Venmo" in raw_text or "Call" in filename or "Message" in filename:
                      trip_data["is_cdot_reportable"] = True
                      trip_data["classification"] = "Private_Trip"

        # Enrich with Tessie
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if vin:
            is_private = trip_data.get("is_cdot_reportable", False)
            drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
            if drive:
                trip_data['tessie_drive_id'] = drive.get('id')
                trip_data['tessie_distance'] = drive.get('distance_miles')
                trip_data['tessie_distance_mi'] = drive.get('distance_miles') # Map to new column
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
        # Use dynamic home state for "Today" to match user's local day
        tz_name = datetime_utils.get_sql_timezone()
        
        query = f"SELECT TOP 1 * FROM v_DailyKPIs WHERE [Date] = CAST(SYSDATETIMEOFFSET() AT TIME ZONE '{tz_name}' AS DATE)"
        daily_stats = db.execute_query_with_results(query)
        stats = daily_stats[0] if daily_stats else {"TotalEarnings": 0, "TotalTips": 0, "TripCount": 0, "TotalExpenses": 0}
        
        # 1.1 Fetch Expense Breakdown
        expense_query = f"SELECT Notes as name, Earnings_Driver as amount FROM Trips WHERE TripType = 'Expense' AND CAST(CreatedAt AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE '{tz_name}' AS DATE)"
        expenses = db.execute_query_with_results(expense_query)

        # 1.2 Calculate Tessie Mission Summary (Miles, FSD, Charging)
        # Fix: Calculate start of MST day relative to now
        import time
        from datetime import datetime, timedelta
        
        # Get current time in UTC
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        # Adjusted for home state
        now_local = datetime_utils.utc_to_local(now_utc)
        # Start of local day
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        # Back to UTC to get timestamp
        start_day_ts = int(start_local.astimezone(pytz.utc).timestamp())
        
        drives = tessie.get_drives(vin, start_day_ts, int(time.time())) if vin else []
        charges = tessie.get_charges(vin, start_day_ts, int(time.time())) if vin else []
        
        total_miles = sum(d.get('odometer_distance', 0) for d in drives)
        total_auto = sum(d.get('autopilot_distance', 0) for d in drives)
        fsd_pct = (total_auto / total_miles * 100) if total_miles > 0 else 0
        
        charge_count = len(charges)
        charge_cost = sum(float(c.get('cost') or 0) for c in charges)

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
            "summary": {
                "total_miles": round(total_miles, 1),
                "fsd_pct": round(fsd_pct, 1),
                "elevation_flux": 1240, 
                "total_expenses": stats.get("TotalExpenses", 0),
                "expense_list": expenses,
                "charge_count": charge_count,
                "charge_cost": round(charge_cost, 2)
            },
            "compliance": {
                "platform_cut": stats.get("TotalPlatformCut", 0),
                "service_fees": stats.get("TotalServiceFees", 0),
                "insurance_fees": stats.get("TotalInsuranceFees", 0),
                "other_fees": float(stats.get("TotalPlatformCut", 0)) - float(stats.get("TotalServiceFees", 0)) - float(stats.get("TotalInsuranceFees", 0)),
                "is_profitable": float(stats.get("TotalEarnings", 0)) > float(stats.get("TotalPlatformCut", 0))
            },
            "server_time": datetime_utils.format_local_time(datetime.datetime.utcnow())
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
            "driver_total": price,
            "distance_miles": dist,
            "duration_minutes": dur,
            "payment_method": req_body.get('paymentMethod', "Website Booking"),
            "raw_text": f"Private Booking: {name} ({email})",
            "timestamp_epoch": time.time(),
            
            # Compliance Fields
            "is_cdot_reportable": True, # Private trips are ALWAYS reportable
            "passenger_firstname": name.split()[0] if name else "Guest",
            "pickup_address_full": pickup, # Assuming website sends clean addr
            "dropoff_address_full": dropoff
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

@app.route(route="calendar-availability", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def calendar_availability(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns available time slots from Microsoft Bookings.
    """
    logging.info("Calendar availability check requested")
    try:
        date_param = req.params.get('date')
        if not date_param:
            return func.HttpResponse(json.dumps({"error": "Date required"}), status_code=400)
        
        # Parse ISO date to YYYY-MM-DD
        from dateutil.parser import parse
        date_obj = parse(date_param)
        date_str = date_obj.strftime("%Y-%m-%d")

        from lib.bookings import BookingsClient
        client = BookingsClient()
        slots = client.get_availability(date_str)

        return func.HttpResponse(
            json.dumps({"success": True, "date": date_param, "slots": slots}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error in calendar_availability: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@app.route(route="calendar-book", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def calendar_book(req: func.HttpRequest) -> func.HttpResponse:
    """
    Creates a new booking in Microsoft Bookings.
    """
    logging.info("New booking creation requested")
    try:
        req_body = req.get_json()
        from lib.bookings import BookingsClient
        client = BookingsClient()
        
        # Call Microsoft Bookings
        booking_result = client.create_appointment(
            customer_data={
                "name": req_body.get('customerName'),
                "email": req_body.get('customerEmail'),
                "phone": req_body.get('customerPhone'),
                "pickup": req_body.get('pickup'),
                "dropoff": req_body.get('dropoff'),
            },
            start_time_iso=req_body.get('appointmentStart')
        )

        # Log to SQL (optional but good for history)
        from lib.database import DatabaseClient
        db = DatabaseClient()
        db.save_trip({
            "trip_id": booking_result.get('id'),
            "classification": "Microsoft_Booking",
            "start_location": req_body.get('pickup'),
            "end_location": req_body.get('dropoff'),
            "fare": req_body.get('price', 0),
            "timestamp_epoch": time.time()
        })

        return func.HttpResponse(
            json.dumps({"success": True, "booking": booking_result}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error in calendar_book: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@app.route(route="update-payment", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def update_payment(req: func.HttpRequest) -> func.HttpResponse:
    """
    Updates the payment method for an existing trip.
    """
    logging.info("Payment update requested")
    try:
        req_body = req.get_json()
        booking_id = req_body.get('bookingId')
        payment_method = req_body.get('paymentMethod')

        if not booking_id or not payment_method:
            return func.HttpResponse(json.dumps({"error": "Missing bookingId or paymentMethod"}), status_code=400)

        from lib.database import DatabaseClient
        db = DatabaseClient()
        
        # Direct SQL Update for safety (avoid overwriting other fields in a full Upsert)
        query = "UPDATE Trips SET Payment_Method = ?, LastUpdated = GETDATE() WHERE TripID = ?"
        conn = db.get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(query, (payment_method, booking_id))
            conn.commit()
            conn.close()
            logging.info(f"Updated payment for {booking_id} to {payment_method}")
            return func.HttpResponse(json.dumps({"success": True}), status_code=200, mimetype="application/json")
        else:
            return func.HttpResponse(json.dumps({"error": "Database connection failed"}), status_code=500)

    except Exception as e:
        logging.error(f"Error in update_payment: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@app.schedule(schedule="0 0 * * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def reconcile_trips_timer(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('⏳ Hourly Reconciliation Timer Triggered')
    try:
        from lib.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        engine.reconcile_private_trips()
    except Exception as e:
        logging.error(f"Reconciliation failed: {e}")

@app.route(route="reconcile-trips", methods=["POST", "GET"], auth_level=func.AuthLevel.FUNCTION)
def reconcile_trips_manual(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Manual Reconciliation Triggered")
    try:
        from lib.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        
        # Allow passing days_back as query param
        days = req.params.get('days')
        days = int(days) if days else 7
        
        engine.reconcile_private_trips(days_back=days)
        
        return func.HttpResponse(json.dumps({"success": True, "message": "Reconciliation cycle complete"}), status_code=200)
    except Exception as e:
        logging.error(f"Manual reconciliation failed: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@app.route(route="cabin-api", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def cabin_api(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Cabin API Triggered")
    
    # 1. Setup
    from lib.tessie import TessieClient
    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")
    
    if not vin:
        return func.HttpResponse(json.dumps({"error": "No VIN configured"}), status_code=500)

    # 2. Handle GET (State)
    if req.method == "GET":
        # Basic Token Check (In real app, validate against DB)
        token = req.params.get('token')
        if not token:
             return func.HttpResponse(json.dumps({"error": "Unauthorized"}), status_code=401)

        state = tessie.get_vehicle_state(vin)
        if state:
            # Flatten/Simplify for frontend
            drive_state = state.get('drive_state', {})
            vehicle_state = state.get('vehicle_state', {})
            climate_state = state.get('climate_state', {})
            
            current_speed = drive_state.get('speed') or 0
            
            # Map seats
            seats = {
                'rl': climate_state.get('seat_heater_rear_left', 0),
                'rr': climate_state.get('seat_heater_rear_right', 0)
            }
            
            windows = vehicle_state.get('fd_window', 0) > 0 
            
            return func.HttpResponse(json.dumps({
                "speed": current_speed,
                "elevation": 6035, # Default if missing
                "seats": seats,
                "windows_vented": windows
            }), mimetype="application/json")
        else:
            return func.HttpResponse(json.dumps({"error": "Failed to fetch state"}), status_code=502)

    # 3. Handle POST (Control)
    try:
        req_body = req.get_json()
        
        # Check token in body
        token = req_body.get('token')
        if not token:
             return func.HttpResponse(json.dumps({"error": "Unauthorized"}), status_code=401)

        command = req_body.get('command')
        
        result = None
        if command == 'seat_heater':
            seat = req_body.get('seat') # 'rear_left'
            level = req_body.get('level') # 0-3
            result = tessie.set_seat_heater(vin, seat, level)
            
        elif command == 'vent_windows':
            result = tessie.control_windows(vin, 'vent')
            
        elif command == 'close_windows':
            result = tessie.control_windows(vin, 'close')
            
        if result:
            return func.HttpResponse(json.dumps({"success": True}), mimetype="application/json")
        else:
            return func.HttpResponse(json.dumps({"error": "Command failed"}), status_code=500)
            
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=400)
@app.route(route="catchup-today", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def catchup_today(req: func.HttpRequest) -> func.HttpResponse:
    """
    Manually triggers a scan of the local OneDrive folder for today's data.
    """
    logging.info("🔴 Manual Dashboard Catch-up Triggered")
    try:
        from lib.ocr import OCRClient
        from lib.database import DatabaseClient
        from lib.tessie import TessieClient
        
        ocr = OCRClient()
        db = DatabaseClient()
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        
        # Fixed path for Cloud PC environment
        WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        
        count = 0
        if not os.path.exists(WATCH_DIR):
            return func.HttpResponse(json.dumps({"error": "OneDrive directory not accessible"}), status_code=500)

        for root, dirs, files in os.walk(WATCH_DIR):
            for file in files:
                if today_str in file and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    full_path = os.path.join(root, file)
                    raw_text = ocr.extract_text_from_stream(full_path)
                    if not raw_text: continue
                    
                    # Logic same as catchup_today.py
                    import re
                    suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", file)
                    suffix = suffix_match.group(1) if suffix_match else None
                    classification = "Uber_Core" if suffix in ["FD", "ST", "ED", "RD"] else ocr.classify_image(raw_text)
                    
                    trip_data = {
                        "classification": classification,
                        "source_url": f"local://{file}",
                        "timestamp_epoch": os.path.getmtime(full_path),
                        "raw_text": raw_text[:500]
                    }
                    
                    if suffix == "RD":
                        route_data = ocr.parse_route_details(raw_text)
                        trip_data.update(ocr.parse_ubertrip(raw_text, suffix))
                        trip_data["pickup_address_full"] = route_data.get("pickup_address")
                        trip_data["dropoff_address_full"] = route_data.get("dropoff_address")
                    elif suffix in ["FD", "ST", "ED"] or classification == "Uber_Core":
                        trip_data.update(ocr.parse_ubertrip(raw_text, suffix))
                    
                    db.save_trip(trip_data)
                    count += 1

        return func.HttpResponse(json.dumps({"success": True, "processed": count}), status_code=200)
    except Exception as e:
        logging.error(f"Catch-up failed: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)
