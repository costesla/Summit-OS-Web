import logging
import azure.functions as func
import json
import os
import googlemaps
from services.pricing import PricingEngine

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="quote", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def quote(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Pricing quote requested via Blueprint")
    
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    
    try:
        req_body = req.get_json()
        pickup = req_body.get('pickup', '')
        dropoff = req_body.get('dropoff', '')
        customer_email = req_body.get('email', req_body.get('customerEmail', ''))
        
        gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not gmaps_key:
            raise Exception("Google Maps API Key missing from environment")
            
        gmaps = googlemaps.Client(key=gmaps_key)
        
        # Directions API
        stops = req_body.get('stops', [])
        valid_stops = [s for s in stops if s and s.strip()]
        
        directions_res = gmaps.directions(
            origin=pickup,
            destination=dropoff,
            waypoints=valid_stops,
            mode="driving",
            region="us"
        )
        
        if not directions_res:
             logging.warning(f"No directions found for {pickup} -> {dropoff}")
             raise Exception(f"Unable to find a driving route between these addresses")
             
        route = directions_res[0]
        legs = route.get('legs', [])
        
        total_dist_meters = sum(leg['distance']['value'] for leg in legs)
        total_duration_sec = sum(leg['duration']['value'] for leg in legs)
        
        dist_miles = total_dist_meters * 0.000621371
        dur_text = legs[0]['duration']['text'] if len(legs) == 1 else f"{total_duration_sec // 60} mins"
        
        actual_origin = legs[0]['start_address']
        actual_dest = legs[-1]['end_address']

        trip_type = req_body.get('tripType', 'one-way')
        return_stops = req_body.get('returnStops', [])
        valid_return_stops = [s for s in return_stops if s and s.strip()]
        
        total_dist_miles = dist_miles
        total_stops = len(valid_stops)
        
        if trip_type == 'round-trip':
            return_res = gmaps.directions(
                origin=dropoff,
                destination=pickup,
                waypoints=valid_return_stops,
                mode="driving",
                region="us"
            )
            if return_res:
                return_route = return_res[0]
                return_legs = return_route.get('legs', [])
                return_dist_meters = sum(leg['distance']['value'] for leg in return_legs)
                total_dist_miles += return_dist_meters * 0.000621371
                total_stops += len(valid_return_stops)
                
        layover_hours = float(req_body.get('layoverHours', 0))
        simple_wait_time = req_body.get('simpleWaitTime', False)
        
        wait_hours = layover_hours
        if trip_type == 'one-way' and simple_wait_time:
            wait_hours = max(wait_hours, 1.0)

        pricing = PricingEngine()
        quote_data = pricing.calculate_trip_price(
            distance_miles=total_dist_miles,
            stops_count=total_stops,
            wait_time_hours=wait_hours,
            customer_email=customer_email
        )
        
        quote_data["debug"] = {
            "duration": dur_text, 
            "miles": f"{dist_miles:.1f}",
            "origin": actual_origin,
            "destination": actual_dest
        }
        quote_data["time"] = total_duration_sec // 60
            
        return func.HttpResponse(
            json.dumps({"success": True, "quote": quote_data}),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        logging.error(f"Pricing Error: {error_msg}\n{tb}")
        
        # Treat route/address errors as 200 Success=False so frontend can show a clean message
        soft_errors = ["Google Maps", "route", "NOT_FOUND", "ZERO_RESULTS", "Unable to find", "INVALID_REQUEST"]
        if any(err in error_msg for err in soft_errors) or any(err in error_msg.lower() for err in soft_errors):
            return func.HttpResponse(
                json.dumps({"success": False, "error": error_msg}),
                status_code=200,
                headers=_cors_headers(),
                mimetype="application/json"
            )
            
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Internal Pricing Engine Error", "details": error_msg}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )
