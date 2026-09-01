import logging
import json
import pyodbc
import os
import azure.functions as func
from services.auth_guard import require_function_key, cors_headers
from services.database import DatabaseClient

bp = func.Blueprint()

DEFAULT_ENERGY_RATE = 0.45  # $/kWh (unvalidated placeholder)
DEFAULT_WEAR_RATE = 0.13    # $/mile (unvalidated placeholder)

@bp.route(route="analytics/trip-yield", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def get_trip_yield(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns commercial trip yields as a GeoJSON FeatureCollection.
    Supports 'corridors' (LineString) and 'points' (Point) geometry formats.
    Properties include dynamic net $/hour, gross, distance, duration, and estimation flags.
    Raw PII address strings, client classification names, and duplicate coordinate properties are omitted.
    """
    # 1. Handle CORS Preflight
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=cors_headers(req))

    # 2. Defense-in-Depth Auth Guard
    auth_failure = require_function_key(req)
    if auth_failure:
        return auth_failure

    try:
        # 3. Parse Query Parameters
        trip_type_param = (req.params.get("trip_type") or "all").lower().strip()
        format_param = (req.params.get("format") or "corridors").lower().strip()
        from_date = req.params.get("from")
        to_date = req.params.get("to")
        energy_rate_param = req.params.get("energy_rate")
        wear_rate_param = req.params.get("wear_rate")

        energy_rate = float(energy_rate_param) if energy_rate_param else DEFAULT_ENERGY_RATE
        wear_rate = float(wear_rate_param) if wear_rate_param else DEFAULT_WEAR_RATE

        # 4. Build Query Filters against Rides.vw_TripYield
        where_clauses = ["1=1"]
        params = []

        if trip_type_param == "uber":
            where_clauses.append("TripType = 'Uber'")
        elif trip_type_param == "private":
            where_clauses.append("TripType = 'Private'")

        if from_date:
            where_clauses.append("CAST(Timestamp_Start AS DATE) >= ?")
            params.append(from_date)

        if to_date:
            where_clauses.append("CAST(Timestamp_Start AS DATE) <= ?")
            params.append(to_date)

        query = f"""
        SELECT 
            RideID, TripType, Timestamp_Start,
            Start_Latitude, Start_Longitude, End_Latitude, End_Longitude,
            Distance_mi, Duration_min, Energy_Used_kWh, gross, engaged_hours, is_estimated
        FROM Rides.vw_TripYield
        WHERE {' AND '.join(where_clauses)}
        ORDER BY Timestamp_Start ASC;
        """

        db = DatabaseClient()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # 5. Build GeoJSON FeatureCollection
        features = []
        for r in rows:
            ride_id = r[0]
            trip_type = r[1]
            ts_start = r[2]
            s_lat = float(r[3])
            s_lng = float(r[4])
            e_lat = float(r[5]) if r[5] is not None else None
            e_lng = float(r[6]) if r[6] is not None else None
            dist_mi = float(r[7] or 0.0)
            dur_min = int(r[8] or 0)
            kwh = float(r[9] or 0.0) if r[9] is not None else 0.0
            gross = float(r[10] or 0.0)
            engaged_hours = float(r[11] or (dur_min / 60.0))
            is_estimated = int(r[12] or 0)

            # Dynamic Yield Math
            energy_cost = round(kwh * energy_rate, 2)
            wear_cost = round(dist_mi * wear_rate, 2)
            net = round(gross - energy_cost - wear_cost, 2)
            net_per_hour = round(net / engaged_hours, 2) if engaged_hours > 0 else 0.0

            # Determine Geometry based on format_param and coordinate availability
            if format_param == "corridors" and e_lat is not None and e_lng is not None:
                geometry = {
                    "type": "LineString",
                    "coordinates": [
                        [s_lng, s_lat],
                        [e_lng, e_lat]
                    ]
                }
            else:
                geometry = {
                    "type": "Point",
                    "coordinates": [s_lng, s_lat]
                }

            feature = {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "ride_id": ride_id,
                    "trip_type": trip_type,
                    "timestamp_start": ts_start.isoformat() if ts_start else None,
                    "gross": gross,
                    "distance_mi": dist_mi,
                    "duration_min": dur_min,
                    "energy_used_kwh": kwh if not is_estimated else None,
                    "energy_cost": energy_cost,
                    "wear_cost": wear_cost,
                    "net": net,
                    "net_per_hour": net_per_hour,
                    "is_estimated": bool(is_estimated)
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "metadata": {
                "count": len(features),
                "format": format_param,
                "energy_rate_applied": energy_rate,
                "wear_rate_applied": wear_rate,
                "is_unvalidated_rates": True,
                "trip_type_filter": trip_type_param
            },
            "features": features
        }

        return func.HttpResponse(
            json.dumps(geojson),
            status_code=200,
            headers=cors_headers(req),
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Trip Yield Endpoint Error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers=cors_headers(req),
            mimetype="application/json"
        )
