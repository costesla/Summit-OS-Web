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
        query = "SELECT TOP 1 * FROM Reports.DailyKPIs WHERE [Date] = CAST(GETDATE() AS DATE)"
        daily_stats = db.execute_query_with_results(query)
        stats = daily_stats[0] if daily_stats else {"TotalEarnings": 0, "TotalTips": 0, "RideCount": 0}
        
        # 2. Weather
        weather_query = "SELECT TOP 1 Temperature_F, Condition FROM Rides.WeatherLog ORDER BY timestamp DESC"
        weather_data = db.execute_query_with_results(weather_query)
        weather = weather_data[0] if weather_data else {"Temperature_F": "N/A", "Condition": "N/A"}
        
        # 3. Telematics
        vehicle_state = tessie.get_vehicle_state(vin) if vin else None
        telematics = {}
        if vehicle_state:
            cs = vehicle_state.get('charge_state', {})
            ds = vehicle_state.get('drive_state', {})
            telematics = {
                "battery_level": cs.get('battery_level'),
                "charging_state": cs.get('charging_state'),
                "latitude": ds.get('latitude'),
                "longitude": ds.get('longitude'),
                "speed": ds.get('speed')
            }

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
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
