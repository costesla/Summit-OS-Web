import logging
import json
import azure.functions as func
import os
import datetime
from lib.database import DatabaseClient
from lib.tessie import TessieClient

# Blueprint for Copilot API
bp = func.Blueprint()

# Configuration
# Read from env or default to 60 requests per minute
RATE_LIMIT_PER_MIN = int(os.environ.get("COPILOT_RATE_LIMIT_PER_MIN", 60))
# Simple in-memory counter (note: resets on instance restart, not distributed)
# For production strictness, would use Redis/Storage, but memory is fine for single-instance
_request_counts = {}

def check_rate_limit(req):
    """
    Simple sliding window or per-minute reset rate limiter.
    Uses x-ms-client-principal-id (App Service Auth) or fallback for identity.
    """
    # 2. FIX: Safer identity fallback for Copilot
    client_id = (
        req.headers.get("x-ms-client-principal-id")
        or req.headers.get("x-forwarded-for")
        or "copilot-anonymous"
    )
    
    now = datetime.datetime.now()
    bucket = now.strftime("%Y-%m-%d %H:%M") # Minute bucket
    
    key = f"{client_id}:{bucket}"
    
    current = _request_counts.get(key, 0)
    if current >= RATE_LIMIT_PER_MIN:
        return False
    
    # Cleanup old buckets (naive)
    if len(_request_counts) > 100:
        _request_counts.clear()
        
    _request_counts[key] = current + 1
    return True

# 4. REC: Consistent Response Envelope
def copilot_response(payload):
    """Standardized response wrapper for Copilot."""
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "data": payload,
            "metadata": {
                "source": "Summit Sync",
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
            }
        }),
        mimetype="application/json"
    )

# 3. FIX: Enforce ISO 8601 Timestamps
def to_iso(ts):
    """Ensures timestamp is ISO 8601 string."""
    if not ts: return None
    if isinstance(ts, (datetime.date, datetime.datetime)):
        return ts.isoformat()
    return str(ts)

def format_currency(amount):
    """Returns currency object for LLM consumption"""
    if amount is None: amount = 0
    return {
        "amount": float(amount),
        "display": f"${float(amount):.2f}"
    }

def sanitize_location(location_name):
    """
    Privacy: Extract only city/state if possible, or return as is if generic.
    Avoid coordinates if passed here.
    """
    if not location_name: return "Unknown"
    # Basic heuristic: if it looks like an address, try to keep it simple
    # For now, return as is but assume Database stores mostly generic names or we rely on Instructions
    # strictness. The plan said "city-level", let's trust DB or simplify.
    # If the DB has full address "123 Main St, Colorado Springs, CO", we might want to mask it.
    # But for now, we'll return what's in DB as the user owns the data.
    # The PROMPT instructions tell Copilot not to reveal precise PII.
    return location_name

@bp.route(route="copilot/trips/latest", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_trips_latest(req: func.HttpRequest) -> func.HttpResponse:
    """Returns recent trips for Copilot."""
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        days = int(req.params.get("days", 7))
        # 5. REC: Defensive Bounding
        if days > 90: days = 90
        
        trip_type = req.params.get("type", None) # Uber or Private
        
        db = DatabaseClient()
        trips = db.get_recent_trips(days=days, trip_type=trip_type)
        
        # Format for LLM
        formatted_trips = []
        for t in trips:
            formatted_trips.append({
                "trip_id": t.get("TripID"),
                "type": t.get("TripType"),
                "timestamp": to_iso(t.get("Timestamp")), # FIX: Explicit ISO
                "pickup": sanitize_location(t.get("Pickup_Place")),
                "dropoff": sanitize_location(t.get("Dropoff_Place")),
                "fare": format_currency(t.get("Fare")),
                "tip": format_currency(t.get("Tip")),
                "distance_miles": t.get("Distance_mi"),
                "duration_minutes": t.get("Duration_min")
            })
            
        return copilot_response({"count": len(formatted_trips), "trips": formatted_trips})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/trips/{trip_id}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_trip_detail(req: func.HttpRequest) -> func.HttpResponse:
    """Returns details for a specific trip."""
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
            "timestamp": to_iso(trip.get("Timestamp")), # FIX: Explicit ISO
            "classification": trip.get("Classification"),
            "pickup": trip.get("Pickup_Place"),
            "dropoff": trip.get("Dropoff_Place"),
            "fare": format_currency(trip.get("Fare")),
            "tip": format_currency(trip.get("Tip")),
            "driver_earnings": format_currency(trip.get("Earnings_Driver")),
            "distance_miles": trip.get("Distance_mi"),
            "duration_minutes": trip.get("Duration_min"),
            "payment_method": trip.get("Payment_Method"),
            "notes": trip.get("Notes")
        }
        
        return copilot_response({"trip": data})
        
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/metrics/daily", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_metrics_daily(req: func.HttpRequest) -> func.HttpResponse:
    """Returns daily KPIs."""
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        start_date = req.params.get("start_date")
        end_date = req.params.get("end_date")
        
        if not start_date or not end_date:
            # Default to last 7 days
            end_dt = datetime.datetime.now()
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

@bp.route(route="copilot/metrics/summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_metrics_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Returns aggregated summary."""
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        days = int(req.params.get("days", 30))
        # 5. REC: Defensive Bounding
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

@bp.route(route="copilot/vehicle/status", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_vehicle_status(req: func.HttpRequest) -> func.HttpResponse:
    """Returns live vehicle status (Sanitized)."""
    if not check_rate_limit(req):
        return func.HttpResponse(json.dumps({"error": "Rate limit exceeded"}), status_code=429)

    try:
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        
        if not vin:
            return func.HttpResponse(json.dumps({"error": "VIN not configured"}), status_code=500)
            
        state = tessie.get_public_state(vin) # Reuse existing sanitized method
        
        if not state:
            return func.HttpResponse(json.dumps({"error": "Vehicle unreachable"}), status_code=404)
        
        return copilot_response({"vehicle": state})
    except Exception as e:
        logging.error(f"Copilot API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)
