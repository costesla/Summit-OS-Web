import logging
import json
import azure.functions as func
import os
import datetime
from services.database import DatabaseClient
from services.tessie import TessieClient
from services.vector_store import VectorStore
from services.agent_orchestrator import SystemOrchestrator

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
    current_mt = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
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
            end_dt = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
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
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "VIN not configured"}), status_code=500)
        state = tessie.get_public_state(vin)
        if not state:
            return func.HttpResponse(json.dumps({"error": "Vehicle unreachable"}), status_code=404)
        return copilot_response({"vehicle": state})
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
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse(json.dumps({"error": "Vehicle VIN not configured"}), status_code=500)

        tessie = TessieClient()
        charging_state = tessie.get_live_charging_state(vin)
        
        if not charging_state:
            return func.HttpResponse(json.dumps({"error": "Live charging data is not available right now"}), status_code=404)

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

        # Determine time range
        now = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
        if month_param:
            try:
                year, month = int(month_param.split("-")[0]), int(month_param.split("-")[1])
                from_dt = datetime.datetime(year, month, 1)
                # First day of the NEXT month
                if month == 12:
                    to_dt = datetime.datetime(year + 1, 1, 1)
                else:
                    to_dt = datetime.datetime(year, month + 1, 1)
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid month format. Use YYYY-MM."}), status_code=400)
        else:
            days = int(req.params.get("days", 30))
            if days > 365: days = 365
            from_dt = now - datetime.timedelta(days=days)
            to_dt = now

        from_ts = int(from_dt.timestamp())
        to_ts = int(to_dt.timestamp())

        tessie = TessieClient()
        raw_drives = tessie.get_tagged_drives(vin, from_ts, to_ts)

        # Grouping/Blending Logic
        from collections import defaultdict
        grouped = defaultdict(list)
        
        tag_lower = tag_filter.lower()
        for d in raw_drives:
            raw_tag = str(d.get("tag") or "Uncategorized")
            # Filter if tag_filter is provided
            if tag_filter and tag_lower not in raw_tag.lower():
                continue
                
            # Create base_tag by stripping mission descriptors
            base_tag = raw_tag
            for suffix in [" en route", " drop off", " pickup", " arrival", " - en route", " - drop off"]:
                 if suffix in base_tag.lower():
                     idx = base_tag.lower().find(suffix)
                     base_tag = base_tag[:idx]
            
            # Map start time to MST for date grouping (prevents midnight splits)
            start_ts = d.get("started_at", 0)
            start_dt_mst = (datetime.datetime.utcfromtimestamp(start_ts) - datetime.timedelta(hours=7)) if start_ts else None
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
            
            total_dist = sum(float(d.get("odometer_distance") or 0) for d in drives)
            total_energy = sum(float(d.get("energy_used") or 0) for d in drives)
            total_autopilot = sum(float(d.get("autopilot_distance") or 0) for d in drives)
            
            # Calculate MST time for the mission start
            start_ts = first.get("started_at", 0)
            start_dt_mst = (datetime.datetime.utcfromtimestamp(start_ts) - datetime.timedelta(hours=7)) if start_ts else None
            
            # Aggregated Speeds
            max_speed_kph = max((float(d.get("max_speed") or 0) for d in drives), default=0)
            if total_dist > 0:
                weighted_speed_sum = sum((float(d.get("average_speed") or 0) * float(d.get("odometer_distance") or 0)) for d in drives)
                avg_speed_kph = weighted_speed_sum / total_dist
            else:
                avg_speed_kph = sum(float(d.get("average_speed") or 0) for d in drives) / len(drives)

            efficiency = round((total_energy * 1000) / total_dist, 1) if total_dist > 0 else None
            
            processed.append({
                "date": start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else None,
                "time_mst": start_dt_mst.strftime("%H:%M") if start_dt_mst else None,
                "tag": key.split("|")[1] if "|" in key else "Uncategorized",
                "leg_count": len(drives),
                "is_blended": len(drives) > 1,
                "distance_miles": round(total_dist, 2),
                "average_speed_mph": round(avg_speed_kph * 0.621371, 1),
                "max_speed_mph": round(max_speed_kph * 0.621371, 1),
                "energy_used_kwh": round(total_energy, 2),
                "efficiency_wh_mi": efficiency,
                "autopilot_miles": round(total_autopilot, 2),
                "start": first.get("starting_location"),
                "end": last.get("ending_location"),
                "starting_battery": first.get("starting_battery"),
                "ending_battery": last.get("ending_battery"),
                "tessie_drive_id": first.get("id")
            })

        # Sort by most recent first
        processed.sort(key=lambda x: (x['date'], x['time_mst']), reverse=True)

        return copilot_response({
            "tag_filter": tag_filter or None,
            "count": len(processed),
            "drives": processed
        })

    except Exception as e:
        logging.error(f"Tessie Drives API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


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

        month_param = req.params.get("month", "").strip()
        now = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
        if month_param:
            try:
                year, month = int(month_param.split("-")[0]), int(month_param.split("-")[1])
                from_dt = datetime.datetime(year, month, 1)
                to_dt = datetime.datetime(year + 1, 1, 1) if month == 12 else datetime.datetime(year, month + 1, 1)
            except Exception:
                return func.HttpResponse(json.dumps({"error": "Invalid month format. Use YYYY-MM."}), status_code=400)
        else:
            days = int(req.params.get("days", 30))
            if days > 365: days = 365
            from_dt = now - datetime.timedelta(days=days)
            to_dt = now

        from_ts = int(from_dt.timestamp())
        to_ts = int(to_dt.timestamp())

        tessie = TessieClient()
        raw_charges = tessie.get_charges(vin, from_ts, to_ts)

        sessions = []
        for c in (raw_charges or []):
            start_ts = c.get("started_at") or c.get("start_time") or 0
            start_dt_mst = (datetime.datetime.utcfromtimestamp(start_ts) - datetime.timedelta(hours=7)) if start_ts else None
            sessions.append({
                "date": start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else None,
                "time_mst": start_dt_mst.strftime("%H:%M") if start_dt_mst else None,
                "energy_added_kwh": round(float(c.get("energy_added") or 0), 2),
                "starting_soc": c.get("starting_battery_level") or c.get("battery_level"),
                "ending_soc": c.get("ending_battery_level") or c.get("battery_level_end"),
                "duration_minutes": round(float(c.get("duration") or 0) / 60, 1) if c.get("duration") else None,
                "location": c.get("location") or c.get("charging_location"),
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
        now = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
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
            dist = float(d.get("odometer_distance") or 0)
            total_miles += dist
            total_energy_kwh += float(d.get("energy_used") or 0)
            total_autopilot_miles += float(d.get("autopilot_distance") or 0)
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
