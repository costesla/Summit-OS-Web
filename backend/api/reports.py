import logging
import azure.functions as func
import json
import datetime
import os
import traceback
from services.database import DatabaseClient
from services.tessie import TessieClient

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="dashboard-summary", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard_summary(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Dashboard summary requested via Blueprint")
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
        
    try:
        db = DatabaseClient()
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        
        # 1. KPIs
        # Use v_DailyKPIs if it exists (summit_sync uses it), fallback to Reports.DailyKPIs
        stats = {"TotalEarnings": 0, "TotalTips": 0, "TripCount": 0}
        try:
            query = "SELECT TOP 1 * FROM v_DailyKPIs WHERE [Date] = CAST(GETDATE() AS DATE)"
            daily_stats = db.execute_query_with_results(query)
            if not daily_stats:
                query = "SELECT TOP 1 * FROM Reports.DailyKPIs WHERE [Date] = CAST(GETDATE() AS DATE)"
                daily_stats = db.execute_query_with_results(query)
            
            if daily_stats:
                stats = daily_stats[0]
                # Map RideCount to TripCount if needed
                if "RideCount" in stats and "TripCount" not in stats:
                    stats["TripCount"] = stats["RideCount"]
        except Exception as e:
            logging.warning(f"Failed to fetch KPIs: {e}")
        
        # 2. Weather
        weather = {"Temperature_F": "N/A", "Condition": "N/A"}
        try:
            weather_query = "SELECT TOP 1 Temperature_F, Condition FROM Rides.WeatherLog ORDER BY timestamp DESC"
            weather_data = db.execute_query_with_results(weather_query)
            if not weather_data:
                weather_query = "SELECT TOP 1 Temperature_F, Condition FROM WeatherLog ORDER BY timestamp DESC"
                weather_data = db.execute_query_with_results(weather_query)
            
            if weather_data:
                weather = weather_data[0]
        except Exception as e:
            logging.warning(f"Failed to fetch Weather: {e}")
        
        # 3. Telematics
        telematics = {
            "battery_level": 0,
            "charging_state": "Unknown",
            "latitude": 38.8339,
            "longitude": -104.8214,
            "speed": 0
        }
        try:
            vehicle_state = tessie.get_vehicle_state(vin) if vin else None
            if vehicle_state:
                cs = vehicle_state.get('charge_state', {})
                ds = vehicle_state.get('drive_state', {})
                telematics = {
                    "battery_level": cs.get('battery_level', 0),
                    "charging_state": cs.get('charging_state', "Unknown"),
                    "latitude": ds.get('latitude', 38.8339),
                    "longitude": ds.get('longitude', -104.8214),
                    "speed": ds.get('speed', 0)
                }
        except Exception as e:
            logging.warning(f"Failed to fetch Telematics: {e}")

        return func.HttpResponse(
            json.dumps({
                "stats": stats,
                "weather": weather,
                "telematics": telematics,
                "server_time": datetime.datetime.now().isoformat()
            }, default=str),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Reports Error: {traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"error": "Internal Reports Error", "details": str(e)}), 
            status_code=500, 
            headers=_cors_headers(),
            mimetype="application/json"
        )
