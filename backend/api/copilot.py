import logging
import json
import azure.functions as func
import os
import datetime
import pytz
import re
from services.database import DatabaseClient
from services.tessie import TessieClient
from services.vector_store import VectorStore
from services.agent_orchestrator import SystemOrchestrator

# Mountain Time — automatically handles MST (UTC-7) and MDT (UTC-6)
_MT = pytz.timezone("America/Denver")

def _utc_to_mt(utc_dt: datetime.datetime) -> datetime.datetime:
    """Convert a naive UTC datetime to aware Mountain Time (handles DST)."""
    return pytz.utc.localize(utc_dt).astimezone(_MT)

def _ts_to_mt(unix_ts: float) -> datetime.datetime:
    """Convert a UNIX timestamp to aware Mountain Time datetime."""
    return datetime.datetime.fromtimestamp(unix_ts, tz=pytz.utc).astimezone(_MT)


bp = func.Blueprint()

RATE_LIMIT_PER_MIN = int(os.environ.get("COPILOT_RATE_LIMIT_PER_MIN", 60))
_request_counts = {}

def check_rate_limit(req):
    client_id = (
        req.headers.get("x-ms-client-principal-id")
        or req.headers.get("x-forwarded-for")
        or "copilot-anonymous"
    )
    
    now = datetime.datetime.now()
    bucket = now.strftime("%Y-%m-%d %H:%M")
    key = f"{client_id}:{bucket}"
    
    current = _request_counts.get(key, 0)
    if current >= RATE_LIMIT_PER_MIN:
        return False
    
    if len(_request_counts) > 100:
        _request_counts.clear()
        
    _request_counts[key] = current + 1
    return True

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, x-functions-key"
}

def copilot_response(payload):
    current_mt = _utc_to_mt(datetime.datetime.utcnow())
    response_body = {
        "success": True,
        "_system_time_directive": f"CRITICAL: The user is physically in Mountain Time. It is currently {current_mt.strftime('%Y-%m-%d %I:%M %p')}. If asked for 'today', you MUST filter for {current_mt.strftime('%Y-%m-%d')}."
    }
    if isinstance(payload, dict):
        response_body.update(payload)
    return func.HttpResponse(
        json.dumps(response_body),
        mimetype="application/json",
        headers=CORS_HEADERS
    )

def to_iso(ts):
    if not ts: return None
    if isinstance(ts, (datetime.date, datetime.datetime)):
        return ts.isoformat()
    return str(ts)

def format_currency(amount):
    if amount is None: amount = 0
    return {
        "amount": float(amount),
        "display": f"${float(amount):.2f}"
    }

def sanitize_location(location_name):
    if not location_name: return "Unknown"
    return location_name

def _sanitize_pii_address(address: str) -> str:
    if not address or not isinstance(address, str):
        return address
    
    address = address.strip()
    
    # We want to match street numbers.
    # Refined pattern:
    # 1. Word boundary \b
    # 2. Negative lookahead to ensure the word starting with digits does NOT end with st, nd, rd, th (case-insensitive)
    # 3. Match the digits \d+
    # 4. Match any trailing parts of the street number like letters, dashes, slashes [-/\w]*
    # 5. Match the space \s+
    # 6. Followed by either:
    #    - A letter [a-zA-Z]
    #    - An ordinal number starting with digits (e.g. 1st, 2nd, 3rd, 16th)
    pattern = r'\b(?!\d+(?:st|nd|rd|th|ST|ND|RD|TH)\b)\d+[-/\w]*\s+(?=[a-zA-Z]|\d+(?:st|nd|rd|th|ST|ND|RD|TH)\b)'
    
    # Replace matches with empty string
    return re.sub(pattern, '', address)

def classify_drive(tag, location):
    tag_lower = (tag or "").lower()
    loc_lower = (location or "").lower()
    
    meals = ["ihop", "mcdonalds", "starbucks", "dunkin", "taco bell", "burger king", "wendy's", "subway", "chipotle", "panera", "carl's jr", "dutch bros", "coffee", "grocery", "king soopers", "safeway", "walmart"]
    maintenance = ["quickquack", "car wash", "supercharge", "service", "tesla service", "tire", "maintenance", "autozone"]
    personal = ["park", "gym", "museum", "home", "residence", "private"]
    private_clients = ["jackie", "jacquelyn", "esmeralda", "daniel", "private_trip", "private_pickup"]
    
    for m in meals:
        if m in tag_lower or m in loc_lower:
            return "Meal Stop"
            
    for maint in maintenance:
        if maint in tag_lower or maint in loc_lower:
            return "Maintenance/Operational"

    for p in personal:
        if p in tag_lower or p in loc_lower:
            return "Personal"

    for client in private_clients:
        if client in tag_lower:
            return "Private Client"
            
    # If it has a specific mission tag, it's business
    if tag and tag != "Uncategorized":
         return "Business/Mission"
         
    return "Personal"

@bp.route(route="copilot/trips/latest", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_trips_latest(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        days = int(req.params.get("days", 7))
        if days > 90: days = 90
        trip_type = req.params.get("type", None)
        
        db = DatabaseClient()
        trips = db.get_recent_trips(days=days, trip_type=trip_type)
        
        formatted_trips = []
        for t in trips:
            formatted_trips.append({
                "trip_id": t.get("TripID"),
                "type": t.get("TripType"),
                "timestamp": to_iso(t.get("Timestamp")),
                "pickup": sanitize_location(t.get("Pickup_Place")),
                "dropoff": sanitize_location(t.get("Dropoff_Place")),
                "fare": format_currency(t.get("Fare")),
                "tip": format_currency(t.get("Tip")),
                "distance_miles": float(t.get("Distance_mi")) if t.get("Distance_mi") is not None else 0.0,
                "duration_minutes": float(t.get("Duration_min")) if t.get("Duration_min") is not None else 0.0
            })
            
        return copilot_response({"count": len(formatted_trips), "trips": formatted_trips})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/trips/{trip_id}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_trip_detail(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    trip_id = req.route_params.get('trip_id')
    try:
        db = DatabaseClient()
        trip = db.get_trip_by_id(trip_id)
        if not trip:
            return func.HttpResponse(json.dumps({"error": "Trip not found"}), status_code=404)
            
        data = {
            "trip_id": trip.get("TripID"),
            "type": trip.get("TripType"),
            "timestamp": to_iso(trip.get("Timestamp")),
            "classification": trip.get("Classification"),
            "pickup": trip.get("Pickup_Place"),
            "dropoff": trip.get("Dropoff_Place"),
            "fare": format_currency(trip.get("Fare")),
            "tip": format_currency(trip.get("Tip")),
            "driver_earnings": format_currency(trip.get("Earnings_Driver")),
            "distance_miles": float(trip.get("Distance_mi")) if trip.get("Distance_mi") is not None else 0.0,
            "duration_minutes": float(trip.get("Duration_min")) if trip.get("Duration_min") is not None else 0.0,
            "payment_method": trip.get("Payment_Method"),
            "notes": trip.get("Notes")
        }
        return copilot_response({"trip": data})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/metrics/daily", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_metrics_daily(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        start_date = req.params.get("start_date")
        end_date = req.params.get("end_date")
        
        for d in [start_date, end_date]:
            if d:
                try:
                    datetime.datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    return copilot_response({"success": False, "error": f"Invalid date. You MUST reformat the date strictly to YYYY-MM-DD instead of {d} and use the tool again."})

        if not start_date or not end_date:
            end_dt = _utc_to_mt(datetime.datetime.utcnow())
            start_dt = end_dt - datetime.timedelta(days=7)
            end_date = end_dt.strftime("%Y-%m-%d")
            start_date = start_dt.strftime("%Y-%m-%d")
            
        db = DatabaseClient()
        metrics = db.get_daily_metrics(start_date, end_date)
        formatted = []
        for m in metrics:
            formatted.append({
                "date": m.get("DateStr"),
                "earnings": format_currency(m.get("TotalEarnings")),
                "tips": format_currency(m.get("TotalTips")),
                "trip_count": m.get("TripCount"),
                "miles": float(m.get("TotalMiles") or 0),
                "drive_hours": float(m.get("DriveTime_Hours") or 0)
            })
        return copilot_response({"metrics": formatted})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


@bp.route(route="copilot/private-payments", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_private_payments_get(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)
    try:
        start_date = req.params.get("start_date")
        end_date   = req.params.get("end_date")
        if not start_date or not end_date:
            now_mt     = _utc_to_mt(datetime.datetime.utcnow())
            end_date   = now_mt.strftime("%Y-%m-%d")
            start_date = (now_mt - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        for d in [start_date, end_date]:
            try:
                datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return func.HttpResponse(
                    json.dumps({"error": f"Invalid date: {d}. Use YYYY-MM-DD."}),
                    status_code=400, headers=CORS_HEADERS
                )
        db   = DatabaseClient()
        rows = db.get_private_payments(start_date, end_date)
        payments = []
        for r in rows:
            ts = r.get("Timestamp") or ""
            payments.append({
                "id":        int(r["PaymentID"]),
                "client":    r["Client"],
                "amount":    float(r["Amount"]),
                "note":      r.get("Note") or "",
                "date":      r["PaymentDate"],
                "timestamp": ts.replace(" ", "T") if ts else "",
            })
        return copilot_response({"payments": payments})
    except Exception as e:
        logging.error(f"private_payments GET error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS)


@bp.route(route="copilot/private-payments", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_private_payments_post(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)
    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse(json.dumps({"error": "Invalid JSON"}), status_code=400, headers=CORS_HEADERS)
    try:
        payments    = body.get("payments", [])
        deleted_ids = body.get("deleted_ids", [])
        db = DatabaseClient()
        if payments:
            db.upsert_private_payments(payments)
            # Vectorize each payment so the Copilot can answer semantic queries
            try:
                from services.semantic_ingestion import SemanticIngestionService
                ingestion = SemanticIngestionService()
                for p in payments:
                    ingestion.ingest_private_payment(p)
            except Exception as ve:
                logging.warning(f"private_payments vectorization failed (non-fatal): {ve}")
        for pid in deleted_ids:
            db.soft_delete_private_payment(str(pid))
        return copilot_response({"upserted": len(payments), "deleted": len(deleted_ids)})
    except Exception as e:
        logging.error(f"private_payments POST error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS)


@bp.route(route="copilot/metrics/summary", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_metrics_summary(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        days = int(req.params.get("days", 30))
        if days > 90: days = 90
        db = DatabaseClient()
        summary = db.get_summary_metrics(days=days)
        if not summary:
             return func.HttpResponse(json.dumps({"success": False, "message": "No data"}), mimetype="application/json")

        data = {
            "period_days": days,
            "total_trips": summary.get("TotalTrips"),
            "total_earnings": format_currency(summary.get("TotalEarnings")),
            "total_tips": format_currency(summary.get("TotalTips")),
            "total_distance": float(summary.get("TotalDistance") or 0),
            "average_fare": format_currency(summary.get("AvgFare"))
        }
        return copilot_response({"summary": data})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/vehicle/status", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_vehicle_status(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        from services.secret_manager import SecretManager
        secrets = SecretManager()
        tessie = TessieClient()
        vin = secrets.get_secret("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "VIN not configured in Key Vault"}), status_code=500)

        # Always fetch the full raw vehicle state so we can return battery/charge
        # regardless of location privacy. Only GPS coords are suppressed near home.
        raw_state = tessie.get_vehicle_state(vin)
        if not raw_state:
            return func.HttpResponse(json.dumps({"error": "Vehicle unreachable or asleep"}), status_code=404)

        charge_state = raw_state.get("charge_state", {})
        climate_state = raw_state.get("climate_state", {})
        drive_state = raw_state.get("drive_state", {})

        # Apply geofence only to location — never to battery/charge data
        public_location = tessie.get_public_state(vin)
        location_hidden = public_location and public_location.get("privacy", False)

        vehicle = {
            "battery_level": charge_state.get("battery_level"),
            "battery_range_mi": charge_state.get("battery_range"),
            "charging_state": charge_state.get("charging_state"),
            "charge_limit_pct": charge_state.get("charge_limit_soc"),
            "inside_temp_f": round(climate_state.get("inside_temp", 0) * 9/5 + 32, 1) if climate_state.get("inside_temp") else None,
            "outside_temp_f": round(climate_state.get("outside_temp", 0) * 9/5 + 32, 1) if climate_state.get("outside_temp") else None,
            "is_climate_on": climate_state.get("is_climate_on"),
            "speed_mph": drive_state.get("speed"),
            "location": "Location hidden (privacy geofence active)" if location_hidden else public_location,
            "privacy_active": location_hidden,
        }
        return copilot_response({"vehicle": vehicle})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/search", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_search(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    query_text = req.params.get("q")
    keyword_text = req.params.get("keyword")
    classification = req.params.get("classification")
    
    if not query_text and not keyword_text and not classification:
        return func.HttpResponse(json.dumps({"error": "Missing search parameters (q, keyword, or classification)"}), status_code=400)

    try:
        n_results = int(req.params.get("limit", 5))
        vs = VectorStore()
        # Fallback to evidence mode for basic search
        results = vs.query_evidence_mode(
            query_text=query_text or keyword_text or classification, 
            n_results=n_results
        )
        
        # Map DB columns to OpenAPI SemanticSearchResponse schema
        formatted_results = []
        for r in results:
            ts = r.get('timestamp_utc')
            date_str = ts.isoformat() if isinstance(ts, datetime.datetime) else str(ts) if ts else None
            
            formatted_results.append({
                "score": float(r.get("search_confidence", 0)),
                "summary": r.get("derivation_reason", ""),
                "date": date_str,
                "amount": 0.0,
                "classification": r.get("source_type", "Unknown"),
                "source": r.get("source_pointer", "")
            })
        
        return copilot_response({
            "count": len(formatted_results),
            "results": formatted_results
        })
    except Exception as e:
        logging.error(f"Search API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/charging/live", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_charging_live(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        from services.secret_manager import SecretManager
        secrets = SecretManager()
        vin = secrets.get_secret("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured in Key Vault"}), status_code=500)

        tessie = TessieClient()
        charging_state = tessie.get_live_charging_state(vin)

        
        if not charging_state:
            return func.HttpResponse(json.dumps({"error": "Live charging data is not available right now"}), status_code=404)

        if charging_state and "location" in charging_state:
            charging_state["location"] = _sanitize_pii_address(charging_state["location"])

        return copilot_response(charging_state)
    except Exception as e:
        logging.error(f"Live Charging API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/tessie/drives", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_tessie_drives(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    """
    Query live Tessie API drives filtered by tag keyword (e.g. 'Jackie', 'Esmeralda').
    Supports:
      - tag=Jackie (keyword match anywhere in the tag field)
      - days=30    (look-back window, default 30)
      - month=2026-02 (target a specific month, overrides days)
    """
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured"}), status_code=500)

        tag_filter = req.params.get("tag", "").strip()
        month_param = req.params.get("month", "").strip()   # e.g. "2026-02"
        date_param = req.params.get("date", "").strip()     # e.g. "2026-05-12" (specific day)

        # Determine time range
        # IMPORTANT: Use UTC for UNIX timestamps sent to Tessie API.
        # 'now_display' (MST) is only used for date labels in responses.
        now_utc = datetime.datetime.utcnow()
        now_display = _utc_to_mt(now_utc)  # Mountain Time (handles MST/MDT)
        if date_param:
            # Single-day filter: midnight-to-midnight Mountain Time.
            # Use UTC-6 (MDT, in effect Mar–Nov) as the lower bound so early-morning
            # drives are never clipped. An extra 2-hour buffer on both ends is safe.
            try:
                day_dt = datetime.datetime.strptime(date_param, "%Y-%m-%d")
                from_dt_utc = day_dt + datetime.timedelta(hours=6)   # midnight MDT -> UTC
                to_dt_utc   = day_dt + datetime.timedelta(hours=30)  # next midnight MDT -> UTC
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid date format. Use YYYY-MM-DD."}), status_code=400)
        elif month_param:
            try:
                year, month = int(month_param.split("-")[0]), int(month_param.split("-")[1])
                # Month boundaries at midnight MDT (UTC-6 = +6h). Safe for all months since
                # Colorado observes MDT (UTC-6) through November.
                from_dt_utc = datetime.datetime(year, month, 1) + datetime.timedelta(hours=6)
                if month == 12:
                    to_dt_utc = datetime.datetime(year + 1, 1, 1) + datetime.timedelta(hours=6)
                else:
                    to_dt_utc = datetime.datetime(year, month + 1, 1) + datetime.timedelta(hours=6)
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid month format. Use YYYY-MM."}), status_code=400)
        else:
            days = int(req.params.get("days", 30))
            if days > 365: days = 365
            # Snap from_dt_utc to midnight MDT (= 06:00 UTC) of the start date so early-morning
            # drives (e.g. 05:56 AM MDT) are NEVER clipped by a rolling hour-exact cutoff.
            # Using UTC-6 (MDT) is safe year-round: in MST winter it just adds a 1h buffer.
            start_day_utc = (now_utc - datetime.timedelta(days=days)).replace(
                hour=6, minute=0, second=0, microsecond=0
            )
            from_dt_utc = start_day_utc
            to_dt_utc = now_utc + datetime.timedelta(hours=1)  # 1h buffer catches drives still in progress

        from_ts = int(from_dt_utc.timestamp())
        to_ts = int(to_dt_utc.timestamp())

        tessie = TessieClient()
        raw_drives = tessie.get_tagged_drives(vin, from_ts, to_ts)

        # ── DB Classification Override ──────────────────────────────────────────
        # After getting live Tessie drives, apply any manual classification overrides
        # stored in the database. This allows reclassifying drives (e.g. an "Uber Trip N"
        # that is actually a charging session) without needing to edit the Tessie tag.
        if raw_drives:
            try:
                db_override = DatabaseClient()
                conn_ov = db_override.get_connection()
                if conn_ov:
                    cur_ov = conn_ov.cursor()
                    # Fetch all manually reclassified drives (i.e., where our DB
                    # classification conflicts with what the tag would normally produce)
                    cur_ov.execute("""
                        SELECT RideID, Classification, TripType
                        FROM Rides.Rides
                        WHERE RideID LIKE 'TESSIE-%'
                          AND Classification IS NOT NULL
                          AND Classification != 'Untagged'
                    """)
                    db_classifications = {}
                    for ov_row in cur_ov.fetchall():
                        rid = str(ov_row[0])
                        if rid.startswith('TESSIE-'):
                            drive_num = rid[len('TESSIE-'):]
                            db_classifications[drive_num] = {'classification': ov_row[1], 'trip_type': ov_row[2]}
                    cur_ov.close()
                    conn_ov.close()

                    # Apply overrides to raw Tessie drives
                    for rd in raw_drives:
                        drive_id_str = str(rd.get('id') or '')
                        if drive_id_str in db_classifications:
                            db_cls = db_classifications[drive_id_str]
                            cls = db_cls['classification']
                            # Determine the correct tag from DB classification
                            if cls.startswith('Private:'):
                                override_tag = cls[len('Private:'):]
                            elif cls in ('Uber_Dropoff', 'Uber_Matched'):
                                override_tag = None  # keep Tessie tag for genuine Uber drives
                            elif cls == 'Jackie':
                                override_tag = 'Jackie'
                            elif cls == 'Esmeralda':
                                override_tag = 'Esmeralda'
                            else:
                                override_tag = cls

                            # Apply DB classification override when it diverges from the live Tessie tag.
                            # This covers two cases:
                            #   a) Tessie says "Uber Trip N" but DB says it's Private/Jackie/etc.
                            #   b) Tessie has any tag but DB has explicitly reclassified the drive.
                            if override_tag is not None:
                                original_tag = str(rd.get('tag') or '')
                                # Only override if the DB classification produces a different tag
                                if override_tag.lower() != original_tag.lower():
                                    logging.info(f"DB Override: drive {drive_id_str} tag '{original_tag}' -> '{override_tag}' (DB cls: {cls})")
                                    rd['tag'] = override_tag
            except Exception as ov_err:
                logging.warning(f"DB classification override lookup failed: {ov_err}")

        # Database query fallback when raw_drives is empty
        if not raw_drives:
            logging.info(f"Tessie API returned 0 drives for range {from_ts} to {to_ts}. Initiating database fallback.")
            try:
                db = DatabaseClient()
                conn = db.get_connection()
                if conn:
                    # Convert UTC UNIX timestamps back to Mountain Time for database query
                    from_dt_mt = _ts_to_mt(from_ts)
                    to_dt_mt = _ts_to_mt(to_ts)
                    
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT RideID, TripType, Classification, Distance_mi, Duration_min, 
                               Tessie_DriveID, Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi, 
                               Timestamp_Start, Pickup_Location, Dropoff_Location, Sidecar_Artifact_JSON
                        FROM Rides.Rides 
                        WHERE Timestamp_Start >= ? AND Timestamp_Start <= ?
                        ORDER BY Timestamp_Start
                    """, (from_dt_mt.replace(tzinfo=None), to_dt_mt.replace(tzinfo=None)))
                    
                    rows = cur.fetchall()
                    for row in rows:
                        ride_id = row[0]
                        trip_type = row[1]
                        classification = row[2]
                        distance_mi = float(row[3] or 0)
                        duration_min = float(row[4] or 0)
                        tessie_drive_id = row[5]
                        start_soc = float(row[6] or 0)
                        end_soc = float(row[7] or 0)
                        energy_used_kwh = float(row[8] or 0)
                        efficiency_wh_mi = float(row[9] or 0)
                        timestamp_start = row[10]
                        pickup_location = row[11] or "Unknown"
                        dropoff_location = row[12] or "Unknown"
                        sidecar_json = row[13]
                        
                        # Load sidecar if available
                        sidecar = {}
                        if sidecar_json:
                            try:
                                sidecar = json.loads(sidecar_json)
                            except:
                                pass
                        
                        # Reconstruct tag
                        tag = classification
                        if classification in ('Uber_Dropoff', 'Uber_Matched'):
                            tag = 'uber'
                        elif classification == 'Jackie':
                            tag = 'Jackie'
                        elif classification == 'Esmeralda':
                            tag = 'Esmeralda'
                        elif classification and classification.startswith('Private:'):
                            tag = classification[len('Private:'):]
                        elif not tag:
                            tag = 'Uncategorized'
                            
                        # Localize timestamp to Mountain Time to get UTC UNIX timestamp
                        dt_start_mt = _MT.localize(timestamp_start)
                        started_at = int(dt_start_mt.timestamp())
                        
                        # Handle ended_at
                        ended_at = None
                        if "Timestamp_End" in sidecar:
                            try:
                                dt_end_mt = _MT.localize(datetime.datetime.strptime(sidecar["Timestamp_End"], "%Y-%m-%d %H:%M:%S"))
                                ended_at = int(dt_end_mt.timestamp())
                            except:
                                pass
                        if not ended_at:
                            ended_at = started_at + int(duration_min * 60)
                            
                        # average speed in kph
                        avg_speed_kph = 0.0
                        if duration_min > 0 and distance_mi > 0:
                            avg_speed_mph = distance_mi / (duration_min / 60)
                            avg_speed_kph = avg_speed_mph / 0.621371
                            
                        drive_id = tessie_drive_id
                        if not drive_id:
                            if ride_id.startswith("TESSIE-"):
                                drive_id = ride_id[len("TESSIE-"):]
                            else:
                                drive_id = ride_id
                                
                        d = {
                            "id": drive_id,
                            "tag": tag,
                            "started_at": started_at,
                            "ended_at": ended_at,
                            "distance": distance_mi,
                            "distance_miles": distance_mi,
                            "odometer_distance": distance_mi,
                            "energy_used": energy_used_kwh,
                            "autopilot_distance": 0.0,
                            "max_speed": 0.0,
                            "average_speed": avg_speed_kph,
                            "starting_location": pickup_location,
                            "ending_location": dropoff_location,
                            "starting_battery": start_soc,
                            "ending_battery": end_soc,
                            "starting_latitude": sidecar.get("starting_latitude") or sidecar.get("start_lat"),
                            "starting_longitude": sidecar.get("starting_longitude") or sidecar.get("start_lon"),
                            "ending_latitude": sidecar.get("ending_latitude") or sidecar.get("end_lat"),
                            "ending_longitude": sidecar.get("ending_longitude") or sidecar.get("end_lon")
                        }
                        raw_drives.append(d)
                    
                    logging.info(f"Fallback matched {len(raw_drives)} mock raw drives from Rides.Rides.")
                    cur.close()
                    conn.close()
            except Exception as fallback_err:
                logging.error(f"Error during database drives query fallback: {fallback_err}")

        # Grouping/Blending Logic
        from collections import defaultdict
        grouped = defaultdict(list)
        
        tag_lower = tag_filter.lower()
        
        # Suffixes to strip for mission blending (case-insensitive)
        # We handle both space-separated and camelCase variants common in the user's manual tagging
        suffixes_to_strip = [
            " en route", " enroute", " - en route",
            " in route", " inroute", " - in route", " in-route",
            " pickup", " pick up", " pickup", " - pickup", "pickup", "pick up",
            " dropoff", " drop off", " drop-off", " - dropoff", "dropoff", "drop off",
            " arrival", " - arrival", " arrival",
            " stop ", " stop-", " stop"
        ]

        for d in raw_drives:
            raw_tag = str(d.get("tag") or "Uncategorized")
            # Filter if tag_filter is provided
            if tag_filter and tag_lower not in raw_tag.lower():
                continue
                
            # Create base_tag by stripping mission descriptors
            base_tag = raw_tag
            tag_l = base_tag.lower()
            
            # Iteratively strip suffixes from the end of the tag
            changed = True
            while changed:
                changed = False
                for s in suffixes_to_strip:
                    if tag_l.endswith(s):
                        idx = tag_l.rfind(s)
                        base_tag = base_tag[:idx]
                        tag_l = base_tag.lower()
                        changed = True
                        break
            
            base_tag = base_tag.strip()
            
            # Map start time to MST for date grouping (prevents midnight splits)
            start_ts = d.get("started_at", 0)
            start_dt_mst = _ts_to_mt(start_ts) if start_ts else None
            date_str = start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else "Unknown"
            
            # Special Case: If tag was "Uncategorized", treat every drive as unique to avoid blending non-labeled drives
            if raw_tag == "Uncategorized":
                group_key = f"{d.get('id')}|Uncategorized"
            else:
                group_key = f"{date_str}|{base_tag.strip()}"
                
            grouped[group_key].append(d)

        processed = []
        for key, drives in grouped.items():
            # Sort chronologically
            drives.sort(key=lambda x: x.get("started_at", 0))
            
            first = drives[0]
            last = drives[-1]
            
            total_dist = sum(float(d.get("distance") or d.get("distance_miles") or d.get("odometer_distance") or 0) for d in drives)
            total_energy = sum(float(d.get("energy_used") or 0) for d in drives)
            total_autopilot = sum(float(d.get("autopilot_distance") or d.get("autopilot") or 0) for d in drives)
            
            # Calculate MST time for the mission start
            start_ts = first.get("started_at", 0)
            start_dt_mst = _ts_to_mt(start_ts) if start_ts else None
            
            # Aggregated Speeds
            max_speed_kph = max((float(d.get("max_speed") or 0) for d in drives), default=0)
            if total_dist > 0:
                weighted_speed_sum = sum((float(d.get("average_speed") or 0) * float(d.get("distance") or d.get("distance_miles") or d.get("odometer_distance") or 0)) for d in drives)
                avg_speed_kph = weighted_speed_sum / total_dist
            else:
                avg_speed_kph = sum(float(d.get("average_speed") or 0) for d in drives) / len(drives)

            efficiency = round((total_energy * 1000) / total_dist, 1) if total_dist > 0 else None
            
            # Semantic Classification
            base_tag_for_class = key.split("|")[1] if "|" in key else "Uncategorized"
            classification = classify_drive(base_tag_for_class, last.get("ending_location"))

            processed.append({
                "date": start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else None,
                "time_mst": start_dt_mst.strftime("%H:%M") if start_dt_mst else None,
                "tag": base_tag_for_class,
                "classification": classification,
                "leg_count": len(drives),
                "is_blended": len(drives) > 1,
                "distance_miles": round(total_dist, 2),
                "average_speed_mph": round(avg_speed_kph * 0.621371, 1),
                "max_speed_mph": round(max_speed_kph * 0.621371, 1),
                "energy_used_kwh": round(total_energy, 2),
                "efficiency_wh_mi": efficiency,
                "autopilot_miles": round(total_autopilot, 2),
                "start": _sanitize_pii_address(first.get("starting_location")),
                "end": _sanitize_pii_address(last.get("ending_location")),
                "starting_battery": first.get("starting_battery"),
                "ending_battery": last.get("ending_battery"),
                "duration_minutes": round((last.get("ended_at", 0) - first.get("started_at", 0)) / 60, 1) if first.get("started_at") and last.get("ended_at") else 0,
                "tessie_drive_id": first.get("id"),
                "leg_ids": [d.get("id") for d in drives],
                "start_lat": first.get("starting_latitude"),
                "start_lon": first.get("starting_longitude"),
                "_start_lat": first.get("starting_latitude"),
                "_start_lon": first.get("starting_longitude"),
                "end_lat": last.get("ending_latitude"),
                "end_lon": last.get("ending_longitude"),
                "_end_lat": last.get("ending_latitude"),
                "_end_lon": last.get("ending_longitude")
            })

        # Sort by most recent first
        processed.sort(key=lambda x: (x['date'], x['time_mst']), reverse=True)

        # ─── Fare Match Lookup ──────────────────────────────────────────────
        # Match each drive to a ride with earnings using exact ID matching,
        # with a tight 30-minute time-based fallback.
        try:
            db = DatabaseClient()
            conn = db.get_connection()
            cur = conn.cursor()
            # Fetch all rides with earnings for the relevant date range
            cur.execute("""
                SELECT RideID, Tessie_DriveID, Timestamp_Start, Driver_Earnings
                FROM Rides.Rides
                WHERE Driver_Earnings > 0
                  AND Timestamp_Start IS NOT NULL
            """)
            earned_rides = []
            for row in cur.fetchall():
                earned_rides.append({
                    "RideID": row[0],
                    "Tessie_DriveID": row[1],
                    "Timestamp_Start": row[2],
                    "Driver_Earnings": float(row[3])
                })
            cur.close()
            conn.close()
        except Exception as db_err:
            logging.warning(f"Could not fetch fare match data: {db_err}")
            earned_rides = []

        for drive in processed:
            drive["fare_matched"] = False
            drive["driver_earnings"] = None
            
            drive_id = drive.get("tessie_drive_id")
            if not drive_id:
                continue
                
            drive_id_str = str(drive_id)
            matched_ride = None
            
            # 1. Exact ID Match (highly accurate)
            leg_ids = drive.get("leg_ids", [drive_id])
            for ride in earned_rides:
                r_id = str(ride["RideID"] or "")
                t_id = str(ride["Tessie_DriveID"] or "")
                if any(str(lid) in r_id or str(lid) in t_id for lid in leg_ids if lid):
                    matched_ride = ride
                    break
            
            # 2. Tight Proximity Match (within 30 minutes fallback)
            if not matched_ride and drive.get("date") and drive.get("time_mst"):
                try:
                    drive_dt = datetime.datetime.strptime(f"{drive['date']}T{drive['time_mst']}:00", "%Y-%m-%dT%H:%M:%S")
                    best_diff = 999999
                    for ride in earned_rides:
                        diff = abs((ride["Timestamp_Start"] - drive_dt).total_seconds())
                        if diff <= 1800 and diff < best_diff: # 30 minutes
                            best_diff = diff
                            matched_ride = ride
                except Exception:
                    pass
            
            if matched_ride:
                drive["fare_matched"] = True
                drive["driver_earnings"] = matched_ride["Driver_Earnings"]

        return copilot_response({
            "tag_filter": tag_filter or None,
            "count": len(processed),
            "drives": processed
        })

    except Exception as e:
        logging.error(f"Tessie Drives API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


@bp.route(route="copilot/tessie/heatmap", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_tessie_heatmap(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns geocoded lat/lon heat points for the heatmap.
    Addresses are geocoded via Google Maps API and cached in Rides.GeoCache.
    Each call geocodes up to `batch` (default 80) new uncached addresses.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        days = int(req.params.get("days", 30))
        if days > 365:
            days = 365
        geocode_batch = min(int(req.params.get("batch", 20)), 30)

        cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=days)

        db = DatabaseClient()
        conn = db.get_connection()
        if not conn:
            return func.HttpResponse(
                json.dumps({"error": "DB unavailable", "points": []}),
                status_code=500, headers=CORS_HEADERS
            )
        cur = conn.cursor()

        # Fetch rides in the requested date range
        cur.execute("""
            SELECT Pickup_Location, Dropoff_Location, Driver_Earnings
            FROM Rides.Rides
            WHERE Timestamp_Start >= ?
              AND (Pickup_Location IS NOT NULL OR Dropoff_Location IS NOT NULL)
        """, (cutoff_dt,))
        rows = cur.fetchall()

        # Collect unique addresses
        all_addresses = set()
        for pickup, dropoff, _ in rows:
            if pickup: all_addresses.add(pickup)
            if dropoff: all_addresses.add(dropoff)

        # Bulk-load cached geocodes (500 addresses per IN clause to stay under param limits)
        geo_cache = {}
        addr_list = list(all_addresses)
        chunk_size = 500
        for i in range(0, len(addr_list), chunk_size):
            chunk = addr_list[i:i + chunk_size]
            placeholders = ','.join(['?' for _ in chunk])
            cur.execute(
                f"SELECT Address, Lat, Lon FROM Rides.GeoCache WHERE Address IN ({placeholders})",
                chunk
            )
            for addr, lat, lon in cur.fetchall():
                geo_cache[addr] = (float(lat), float(lon)) if (lat is not None and lon is not None) else None

        # Geocode uncached addresses (up to `geocode_batch` per request)
        uncached = [a for a in all_addresses if a not in geo_cache]
        newly_geocoded = 0

        if uncached and geocode_batch > 0:
            api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
            if not api_key:
                try:
                    from services.secret_manager import SecretManager
                    api_key = SecretManager().get_secret("GOOGLE_MAPS_API_KEY")
                except Exception:
                    pass

            if api_key:
                import googlemaps
                gmaps = googlemaps.Client(key=api_key, timeout=5)  # 5s per call — prevents indefinite hang
                for addr in uncached[:geocode_batch]:
                    lat, lon = None, None
                    try:
                        result = gmaps.geocode(addr)
                        if result:
                            loc = result[0]["geometry"]["location"]
                            lat, lon = loc["lat"], loc["lng"]
                    except Exception as ge:
                        logging.warning(f"Geocode failed for {addr[:60]}: {ge}")
                    geo_cache[addr] = (lat, lon) if (lat and lon) else None
                    newly_geocoded += 1
                    try:
                        cur.execute("""
                            MERGE Rides.GeoCache AS t
                            USING (SELECT ? AS Address, ? AS Lat, ? AS Lon) AS s
                            ON t.Address = s.Address
                            WHEN NOT MATCHED THEN
                                INSERT (Address, Lat, Lon) VALUES (s.Address, s.Lat, s.Lon);
                        """, (addr, lat, lon))
                    except Exception:
                        pass
                try:
                    conn.commit()
                except Exception:
                    pass

        # Build heatmap points
        points = []
        for pickup, dropoff, earnings in rows:
            weight = max(0.1, float(earnings or 1.0))
            if pickup and geo_cache.get(pickup):
                lat, lon = geo_cache[pickup]
                points.append({"lat": lat, "lon": lon, "weight": weight, "type": "pickup"})
            if dropoff and geo_cache.get(dropoff):
                lat, lon = geo_cache[dropoff]
                points.append({"lat": lat, "lon": lon, "weight": weight, "type": "dropoff"})

        conn.close()

        return func.HttpResponse(
            json.dumps({
                "points": points,
                "count": len(points),
                "cached_addresses": len([v for v in geo_cache.values() if v]),
                "uncached_remaining": max(0, len(uncached) - newly_geocoded),
                "newly_geocoded": newly_geocoded,
            }),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"copilot_tessie_heatmap error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e), "points": []}),
            status_code=500, headers=CORS_HEADERS
        )


@bp.route(route="copilot/tessie/charges", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_tessie_charges(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    """
    Returns historical charging sessions from the Tessie API.
    Supports: days=30, month=2026-02
    """
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured"}), status_code=500)

        # IMPORTANT: Use UTC for UNIX timestamps sent to Tessie API.
        now_utc = datetime.datetime.utcnow()
        month_param = req.params.get("month", "").strip()   # e.g. "2026-05"
        if month_param:
            try:
                year, month = int(month_param.split("-")[0]), int(month_param.split("-")[1])
                from_dt_utc = datetime.datetime(year, month, 1) + datetime.timedelta(hours=7)
                to_dt_utc = (datetime.datetime(year + 1, 1, 1) if month == 12 else datetime.datetime(year, month + 1, 1)) + datetime.timedelta(hours=7)
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid month format. Use YYYY-MM."}), status_code=400)
        else:
            days = int(req.params.get("days", 30))
            if days > 365: days = 365
            from_dt_utc = now_utc - datetime.timedelta(days=days)
            to_dt_utc = now_utc + datetime.timedelta(hours=1)

        from_ts = int(from_dt_utc.timestamp())
        to_ts = int(to_dt_utc.timestamp())

        tessie = TessieClient()
        raw_charges = tessie.get_charges(vin, from_ts, to_ts)

        sessions = []
        for c in (raw_charges or []):
            start_ts = c.get("started_at") or c.get("start_time") or 0
            start_dt_mst = _ts_to_mt(start_ts) if start_ts else None
            sessions.append({
                "date": start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else None,
                "time_mst": start_dt_mst.strftime("%H:%M") if start_dt_mst else None,
                "energy_added_kwh": round(float(c.get("energy_added") or 0), 2),
                "starting_soc": c.get("starting_battery_level") or c.get("battery_level"),
                "ending_soc": c.get("ending_battery_level") or c.get("battery_level_end"),
                "duration_minutes": round(float(c.get("duration") or 0) / 60, 1) if c.get("duration") else None,
                "location": _sanitize_pii_address(c.get("location") or c.get("charging_location")),
                "lat": c.get("latitude") or c.get("lat"),
                "lon": c.get("longitude") or c.get("lon") or c.get("lng"),
                "charge_type": c.get("charger_type") or c.get("connector_type"),
                "tessie_charge_id": c.get("id")
            })

        return copilot_response({
            "count": len(sessions),
            "sessions": sessions
        })

    except Exception as e:
        logging.error(f"Tessie Charges API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


def _get_elevations_ft(lat_lons: list) -> list:
    """
    Batch-fetches elevations (in feet) for a list of (lat, lon) tuples
    using the Google Elevation API. Returns a list of floats (or None on failure).
    Costs 1 API call per invocation regardless of point count (up to 512 points).
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or not lat_lons:
        return [None] * len(lat_lons)
    fallback = [None] * len(lat_lons)
    try:
        import requests as _requests
        locations = "|".join(f"{lat},{lon}" for lat, lon in lat_lons)
        url = f"https://maps.googleapis.com/maps/api/elevation/json?locations={locations}&key={api_key}"
        resp = _requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "OK":
                results = data.get("results", [])
                out = []
                for r in results:
                    out.append(round(r["elevation"] * 3.28084, 0) if r.get("elevation") is not None else None)
                # Pad out to match requested input length
                while len(out) < len(lat_lons):
                    out.append(None)
                return out[:len(lat_lons)]
            else:
                logging.warning(f"Elevation API status not OK: {data.get('status')}")
    except Exception as e:
        logging.warning(f"Elevation API failed: {e}")
    return fallback


@bp.route(route="copilot/tessie/day-summary", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_tessie_day_summary(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns a rich single-day driving summary.
    Answers: 'How many miles today?', 'What was my battery drain?', 'What was my highest speed?'
    Param: date=YYYY-MM-DD (defaults to today MST)
    """
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured"}), status_code=500)

        now_mt = _utc_to_mt(datetime.datetime.utcnow())
        date_param = req.params.get("date", now_mt.strftime("%Y-%m-%d")).strip()

        try:
            day_dt = datetime.datetime.strptime(date_param, "%Y-%m-%d")
        except Exception:
            return func.HttpResponse(json.dumps({"error": "Invalid date. Use YYYY-MM-DD."}), status_code=400)

        # MST midnight -> UTC window
        from_dt_utc = day_dt + datetime.timedelta(hours=7)
        to_dt_utc   = day_dt + datetime.timedelta(hours=31)
        from_ts = int(from_dt_utc.timestamp())
        to_ts   = int(to_dt_utc.timestamp())

        tessie = TessieClient()
        raw_drives = tessie.get_tagged_drives(vin, from_ts, to_ts)
        raw_charges = tessie.get_charges(vin, from_ts, to_ts) or []

        total_miles = 0.0
        total_energy_kwh = 0.0
        total_autopilot_miles = 0.0
        max_speed_mph = 0.0
        drive_count = 0
        battery_start = None
        battery_end = None
        drive_breakdown = []

        # Sort chronologically to correctly track battery start -> end
        raw_drives_sorted = sorted(raw_drives, key=lambda d: d.get("started_at", 0))

        for d in raw_drives_sorted:
            dist   = float(d.get("distance") or d.get("distance_miles") or d.get("odometer_distance") or 0)
            energy = float(d.get("energy_used") or 0)
            ap     = float(d.get("autopilot_distance") or d.get("autopilot") or 0)
            spd_kph = float(d.get("max_speed") or 0)
            spd_mph = round(spd_kph * 0.621371, 1)
            avg_mph = round(float(d.get("average_speed") or 0) * 0.621371, 1)

            total_miles          += dist
            total_energy_kwh     += energy
            total_autopilot_miles += ap
            if spd_mph > max_speed_mph:
                max_speed_mph = spd_mph
            drive_count += 1

            b_start = d.get("starting_battery")
            b_end   = d.get("ending_battery")
            if battery_start is None and b_start is not None:
                battery_start = b_start
            if b_end is not None:
                battery_end = b_end

            start_ts = d.get("started_at", 0)
            end_ts   = d.get("ended_at", 0)
            start_mst = _ts_to_mt(start_ts) if start_ts else None
            end_mst   = _ts_to_mt(end_ts)   if end_ts   else None
            duration_min = round((end_ts - start_ts) / 60, 1) if start_ts and end_ts else None

            drive_breakdown.append({
                "tag":               d.get("tag") or "Untagged",
                "start_time_mst":    start_mst.strftime("%I:%M %p") if start_mst else None,
                "end_time_mst":      end_mst.strftime("%I:%M %p")   if end_mst   else None,
                "duration_minutes":  duration_min,
                "distance_miles":    round(dist, 2),
                "energy_used_kwh":   round(energy, 2),
                "avg_speed_mph":     avg_mph,
                "max_speed_mph":     spd_mph,
                "autopilot_miles":   round(ap, 2),
                "starting_battery":  b_start,
                "ending_battery":    b_end,
                "battery_drain_pct": (b_start - b_end) if (b_start and b_end) else None,
                "start_location":    _sanitize_pii_address(d.get("starting_location")),
                "end_location":      _sanitize_pii_address(d.get("ending_location")),
                # lat/lon stored for elevation batch lookup below
                "_start_lat":        d.get("starting_latitude"),
                "_start_lon":        d.get("starting_longitude"),
                "_end_lat":          d.get("ending_latitude"),
                "_end_lon":          d.get("ending_longitude"),
            })

        total_energy_charged = sum(float(c.get("energy_added") or 0) for c in raw_charges)
        battery_drain_total  = (battery_start - battery_end) if (battery_start is not None and battery_end is not None) else None
        efficiency           = round((total_energy_kwh * 1000) / total_miles, 1) if total_miles > 0 else None

        # ── Elevation Lookup (Google Elevation API) ──────────────────────────
        # Build batch: 2 points per drive (start + end) — cheap single API call
        elev_points = []
        for drv in drive_breakdown:
            s_lat, s_lon = drv.pop("_start_lat", None), drv.pop("_start_lon", None)
            e_lat, e_lon = drv.pop("_end_lat",   None), drv.pop("_end_lon",   None)
            elev_points.append((s_lat, s_lon) if (s_lat and s_lon) else None)
            elev_points.append((e_lat, e_lon) if (e_lat and e_lon) else None)

        valid_points  = [(p if p else (0, 0)) for p in elev_points]
        elev_results  = _get_elevations_ft(valid_points) if any(elev_points) else [None] * len(elev_points)

        all_elevations = []
        for i, drv in enumerate(drive_breakdown):
            s_elev = elev_results[i * 2]     if (i * 2 < len(elev_results) and elev_points[i * 2])     else None
            e_elev = elev_results[i * 2 + 1] if (i * 2 + 1 < len(elev_results) and elev_points[i * 2 + 1]) else None
            drv["start_elevation_ft"] = s_elev
            drv["end_elevation_ft"]   = e_elev
            if s_elev: all_elevations.append(s_elev)
            if e_elev: all_elevations.append(e_elev)

        max_elevation_ft = max(all_elevations) if all_elevations else None
        min_elevation_ft = min(all_elevations) if all_elevations else None

        return copilot_response({
            "date":                     date_param,
            "drive_count":              drive_count,
            "total_miles":              round(total_miles, 2),
            "total_energy_used_kwh":    round(total_energy_kwh, 2),
            "total_energy_charged_kwh": round(total_energy_charged, 2),
            "total_autopilot_miles":    round(total_autopilot_miles, 2),
            "autopilot_pct":            round((total_autopilot_miles / total_miles) * 100, 1) if total_miles > 0 else None,
            "max_speed_mph":            round(max_speed_mph, 1),
            "efficiency_wh_mi":         efficiency,
            "battery_start_pct":        battery_start,
            "battery_end_pct":          battery_end,
            "battery_drain_pct":        battery_drain_total,
            "max_elevation_ft":         max_elevation_ft,
            "min_elevation_ft":         min_elevation_ft,
            "drives":                   drive_breakdown,
        })

    except Exception as e:
        logging.error(f"Day Summary API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


@bp.route(route="copilot/tessie/summary", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_tessie_summary(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    """
    Returns aggregated driving stats from the Tessie API for a period.
    Supports: days=30, month=2026-02
    Great for: 'Give me my driving stats for February'
    """
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured"}), status_code=500)

        month_param = req.params.get("month", "").strip()
        now = _utc_to_mt(datetime.datetime.utcnow())
        if month_param:
            try:
                year, month = int(month_param.split("-")[0]), int(month_param.split("-")[1])
                from_dt = datetime.datetime(year, month, 1)
                to_dt = datetime.datetime(year + 1, 1, 1) if month == 12 else datetime.datetime(year, month + 1, 1)
                period_label = month_param
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid month format. Use YYYY-MM."}), status_code=400)
        else:
            days = int(req.params.get("days", 30))
            if days > 365: days = 365
            from_dt = now - datetime.timedelta(days=days)
            to_dt = now
            period_label = f"Last {days} days"

        from_ts = int(from_dt.timestamp())
        to_ts = int(to_dt.timestamp())

        tessie = TessieClient()
        raw_drives = tessie.get_tagged_drives(vin, from_ts, to_ts)
        raw_charges = tessie.get_charges(vin, from_ts, to_ts) or []

        # Aggregate drives
        total_miles = 0.0
        total_energy_kwh = 0.0
        total_autopilot_miles = 0.0
        speed_sum = 0.0
        speed_count = 0
        max_speed_mph = 0.0

        for d in raw_drives:
            dist = float(d.get("distance") or d.get("distance_miles") or d.get("odometer_distance") or 0)
            total_miles += dist
            total_energy_kwh += float(d.get("energy_used") or 0)
            total_autopilot_miles += float(d.get("autopilot_distance") or d.get("autopilot") or 0)
            avg_kph = d.get("average_speed") or 0
            max_kph = d.get("max_speed") or 0
            if avg_kph:
                speed_sum += avg_kph * 0.621371
                speed_count += 1
            if max_kph:
                mph = max_kph * 0.621371
                if mph > max_speed_mph:
                    max_speed_mph = mph

        # Aggregate charges
        total_energy_charged_kwh = sum(float(c.get("energy_added") or 0) for c in raw_charges)

        avg_speed_mph = round(speed_sum / speed_count, 1) if speed_count else None
        overall_efficiency = round((total_energy_kwh * 1000) / total_miles, 1) if total_miles > 0 else None
        autopilot_pct = round((total_autopilot_miles / total_miles) * 100, 1) if total_miles > 0 else None

        return copilot_response({
            "period": period_label,
            "total_drives": len(raw_drives),
            "total_miles": round(total_miles, 2),
            "total_energy_used_kwh": round(total_energy_kwh, 2),
            "total_energy_charged_kwh": round(total_energy_charged_kwh, 2),
            "charge_sessions": len(raw_charges),
            "average_speed_mph": avg_speed_mph,
            "max_speed_mph": round(max_speed_mph, 1),
            "autopilot_miles": round(total_autopilot_miles, 2),
            "autopilot_pct": autopilot_pct,
            "efficiency_wh_mi": overall_efficiency
        })

    except Exception as e:
        logging.error(f"Tessie Summary API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/agentic-query", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_agentic_query(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    query_text = req.params.get("q")
    mode = req.params.get("mode", "evidence").lower()
    
    if not query_text:
        return func.HttpResponse(json.dumps({"error": "Missing 'q' query parameter"}), status_code=400)

    if mode not in ["evidence", "insight", "narrative"]:
        return func.HttpResponse(json.dumps({"error": "Invalid mode. Use 'evidence', 'insight', or 'narrative'."}), status_code=400)

    try:
        orchestrator = SystemOrchestrator()
        
        # Enforce Prime Directive via the Orchestrator
        response_text = orchestrator.process_query(query_text, mode=mode)
        
        return copilot_response({
            "query": query_text,
            "mode": mode,
            "agentic_response": response_text
        })
    except Exception as e:
        logging.error(f"Agentic Query API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/artifacts/{artifact_id}/raw", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_artifact_raw(req: func.HttpRequest) -> func.HttpResponse:
    """Rehydration API: Retrieve raw archived bytes via deterministic SharePoint resolution."""
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    artifact_id = req.route_params.get("artifact_id")
    if not artifact_id:
        return func.HttpResponse(json.dumps({"error": "Missing artifact_id"}), status_code=400)

    try:
        from services.sharepoint import SharePointClient
        import requests
        sp = SharePointClient()
        sp.resolve_ids()
        
        if not sp.drive_id:
            return func.HttpResponse(json.dumps({"error": "SharePoint drive not configured"}), status_code=500)
            
        # Target filename format used in archival
        filename = f"{artifact_id[:12]}.jpg"
        
        headers = sp._get_headers()
        # Fast search scoped specifically to the drive
        search_url = f"https://graph.microsoft.com/v1.0/drives/{sp.drive_id}/root/search(q='{filename}')"
        res = requests.get(search_url, headers=headers)
        
        if res.ok:
            items = res.json().get('value', [])
            if not items:
                return func.HttpResponse(json.dumps({"error": "Artifact archived, expired, or not found."}), status_code=404)
                
            item = items[0]
            item_id = item.get('id')
            
            # The search endpoint doesn't always return the downloadUrl
            # We must fetch the specific item to get the short-lived URL
            item_url = f"https://graph.microsoft.com/v1.0/drives/{sp.drive_id}/items/{item_id}"
            item_res = requests.get(item_url, headers=headers)
            
            if item_res.ok:
                full_item = item_res.json()
                download_url = full_item.get('@microsoft.graph.downloadUrl')
                
                if download_url:
                    # Issue HTTP 302 Redirect to the temporary Azure/SharePoint download URL
                    return func.HttpResponse(status_code=302, headers={"Location": download_url})
                else:
                    return func.HttpResponse(json.dumps({"error": "Download URL not available on item"}), status_code=500)
            else:
                 return func.HttpResponse(json.dumps({"error": "Failed to retrieve item details"}), status_code=500)
        else:

            logging.error(f"Graph Search Failed: {res.text}")
            return func.HttpResponse(json.dumps({"error": "Upstream resolution failed"}), status_code=502)
            
    except Exception as e:
        logging.error(f"Rehydration API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


# ─── SUMMIT INTELLIGENCE SKILLS ENDPOINTS ─────────────────────────────────────

@bp.route(route="copilot/skills/trip-query", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_skill_trip_query(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    start_date = req.params.get("start_date")
    end_date = req.params.get("end_date")

    if not start_date or not end_date:
        return func.HttpResponse(
            json.dumps({"error": "Missing required date_range inputs: 'start_date' and 'end_date' are required."}),
            status_code=400,
            mimetype="application/json",
            headers=CORS_HEADERS
        )

    try:
        from services.agents.summit_intelligence import TripsAgent
        db = DatabaseClient()
        agent = TripsAgent(db)
        data = agent.query(start_date=start_date, end_date=end_date)
        
        # Returns trip objects ONLY, wrapped in standard traceability
        return func.HttpResponse(
            json.dumps({
                "source": "trips",
                "schema": "trip_schema",
                "data": data
            }),
            mimetype="application/json",
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.error(f"TripQuery Skill Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json", headers=CORS_HEADERS)


@bp.route(route="copilot/skills/charging-query", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_skill_charging_query(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    start_date = req.params.get("start_date")
    end_date = req.params.get("end_date")

    if not start_date or not end_date:
        return func.HttpResponse(
            json.dumps({"error": "Missing required date_range inputs: 'start_date' and 'end_date' are required."}),
            status_code=400,
            mimetype="application/json",
            headers=CORS_HEADERS
        )

    try:
        from services.agents.summit_intelligence import ChargingAgent
        db = DatabaseClient()
        agent = ChargingAgent(db)
        data = agent.query(start_date=start_date, end_date=end_date)
        
        # Returns charging session objects ONLY, wrapped in standard traceability
        return func.HttpResponse(
            json.dumps({
                "source": "charging",
                "schema": "charging_schema",
                "data": data
            }),
            mimetype="application/json",
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.error(f"ChargingQuery Skill Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json", headers=CORS_HEADERS)


@bp.route(route="copilot/skills/expense-query", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_skill_expense_query(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    start_date = req.params.get("start_date")
    end_date = req.params.get("end_date")

    if not start_date or not end_date:
        return func.HttpResponse(
            json.dumps({"error": "Missing required date_range inputs: 'start_date' and 'end_date' are required."}),
            status_code=400,
            mimetype="application/json",
            headers=CORS_HEADERS
        )

    try:
        from services.agents.summit_intelligence import ExpensesAgent
        db = DatabaseClient()
        agent = ExpensesAgent(db)
        data = agent.query(start_date=start_date, end_date=end_date)
        
        # Returns expense objects ONLY, wrapped in standard traceability
        return func.HttpResponse(
            json.dumps({
                "source": "expenses",
                "schema": "expenses_schema",
                "data": data
            }),
            mimetype="application/json",
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.error(f"ExpenseQuery Skill Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json", headers=CORS_HEADERS)


@bp.route(route="copilot/skills/vehicle-query", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_skill_vehicle_query(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    start_date = req.params.get("start_date")
    end_date = req.params.get("end_date")

    if not start_date or not end_date:
        return func.HttpResponse(
            json.dumps({"error": "Missing required timestamp_range inputs: 'start_date' and 'end_date' are required."}),
            status_code=400,
            mimetype="application/json",
            headers=CORS_HEADERS
        )

    try:
        from services.agents.summit_intelligence import VehicleAgent
        db = DatabaseClient()
        agent = VehicleAgent(db)
        data = agent.query(start_date=start_date, end_date=end_date)
        
        # Returns telemetry objects ONLY, wrapped in standard traceability
        return func.HttpResponse(
            json.dumps({
                "source": "vehicle",
                "schema": "vehicle_schema",
                "data": data
            }),
            mimetype="application/json",
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.error(f"VehicleQuery Skill Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json", headers=CORS_HEADERS)


@bp.route(route="copilot/skills/daily-summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_skill_daily_summary(req: func.HttpRequest) -> func.HttpResponse:
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    date = req.params.get("date")
    start_date = req.params.get("start_date")
    end_date = req.params.get("end_date")

    try:
        from services.agents.summit_intelligence import MasterOrchestrator
        db = DatabaseClient()
        orchestrator = MasterOrchestrator(db)
        
        # Performs TripQuery, ChargingQuery, ExpenseQuery, and VehicleQuery sequentially under the hood
        data = orchestrator.aggregate_dashboard(date_str=date, start_date=start_date, end_date=end_date)
        
        return func.HttpResponse(
            json.dumps({
                "source": "orchestrator",
                "schema": "dashboard_schema",
                "data": data
            }),
            mimetype="application/json",
            headers=CORS_HEADERS
        )
    except Exception as e:
        logging.error(f"DailySummary Skill Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json", headers=CORS_HEADERS)

