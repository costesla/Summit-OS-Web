import logging
import azure.functions as func
import json
import os
import googlemaps
import requests

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

def _json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data, default=str),
        status_code=status_code,
        headers=_cors_headers(),
        mimetype="application/json"
    )

@bp.route(route="weather/search", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def weather_search(req: func.HttpRequest) -> func.HttpResponse:
    """
    Searches for cities using Google Maps Geocoding API.
    Returns: List of locations {name, lat, lng}
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    query = req.params.get("q")
    if not query:
        return _json_response({"error": "Missing query 'q'"}, 400)

    try:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return _json_response({"error": "Server configuration error"}, 500)

        gmaps = googlemaps.Client(key=api_key)
        
        # Geocode the query to find candidates
        # Region biasing could be added (e.g. region='us') if needed
        results = gmaps.geocode(query)
        
        candidates = []
        for r in results:
            candidates.append({
                "name": r.get("formatted_address"),
                "lat": r["geometry"]["location"]["lat"],
                "lng": r["geometry"]["location"]["lng"]
            })
            
        return _json_response({"results": candidates})
            
    except Exception as e:
        logging.error(f"Weather Search Error: {e}")
        return _json_response({"error": str(e)}, 500)


@bp.route(route="weather/forecast", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def weather_forecast(req: func.HttpRequest) -> func.HttpResponse:
    """
    Proxies request to Open-Meteo for the given lat/lng.
    Returns: Current weather + daily forecast.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    lat = req.params.get("lat")
    lng = req.params.get("lng")
    
    if not lat or not lng:
        return _json_response({"error": "Missing lat/lng"}, 400)

    try:
        # WMO Weather Codes Map
        wmo_map = {
            0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Fog", 48: "Fog",
            51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
            56: "Freezing Drizzle", 57: "Freezing Drizzle",
            61: "Rain", 63: "Rain", 65: "Heavy Rain",
            66: "Freezing Rain", 67: "Freezing Rain",
            71: "Snow", 73: "Snow", 75: "Heavy Snow",
            77: "Snow Grains",
            80: "Showers", 81: "Showers", 82: "Showers",
            85: "Snow Showers", 86: "Snow Showers",
            95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
        }

        # Temperature unit: Fahrenheit, Wind speed: mph, Precip: inch
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
               "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
               "&daily=weather_code,temperature_2m_max,temperature_2m_min"
               "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
               "&timezone=auto")
               
        resp = requests.get(url, timeout=5)
        if not resp.ok:
            return _json_response({"error": "Weather service unavailable"}, 502)
            
        data = resp.json()
        curr = data.get("current", {})
        daily = data.get("daily", {})
        
        # Format response
        result = {
            "current": {
                "temp_f": curr.get("temperature_2m"),
                "humidity": curr.get("relative_humidity_2m"),
                "wind_mph": curr.get("wind_speed_10m"),
                "condition": wmo_map.get(curr.get("weather_code"), "Unknown"),
                "code": curr.get("weather_code")
            },
            "daily": []
        }
        
        # Process 3 days of forecast
        if daily and "time" in daily:
            for i in range(min(3, len(daily["time"]))):
                result["daily"].append({
                    "date": daily["time"][i],
                    "max_f": daily["temperature_2m_max"][i],
                    "min_f": daily["temperature_2m_min"][i],
                    "condition": wmo_map.get(daily["weather_code"][i], "Unknown")
                })

        return _json_response(result)

    except Exception as e:
        logging.error(f"Weather Forecast Error: {e}")
        return _json_response({"error": str(e)}, 500)
