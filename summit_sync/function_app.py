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
@app.route(route="dashboard-summary", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
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
