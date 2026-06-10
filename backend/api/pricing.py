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

        return_dist_miles = 0.0
        return_duration_sec = 0

        if trip_type == 'round-trip':
            return_res = gmaps.directions(
                origin=dropoff,
                destination=pickup,
                waypoints=valid_return_stops,
                mode="driving",
                region="us"
            )
            if return_res:
                return_legs = return_res[0].get('legs', [])
                return_dist_miles = sum(leg['distance']['value'] for leg in return_legs) * 0.000621371
                return_duration_sec = sum(leg['duration']['value'] for leg in return_legs)
            else:
                # Couldn't route the return leg — assume it mirrors the outbound
                return_dist_miles = dist_miles
                return_duration_sec = total_duration_sec

        total_dist_miles = dist_miles + return_dist_miles

        layover_hours = float(req_body.get('layoverHours', 0))
        simple_wait_time = req_body.get('simpleWaitTime', False)
        wait_time_hours_input = float(req_body.get('waitTimeHours', 0))
        quote_type = req_body.get('quoteType', 'single')
        
        wait_hours = layover_hours
        if trip_type == 'one-way' and simple_wait_time:
            wait_hours = max(wait_hours, 1.0)
            
        wait_hours = max(wait_hours, wait_time_hours_input)

        # Determine if out of county — ask Google for the actual county, since
        # city-name matching misses El Paso County places like Security-Widefield,
        # Black Forest, Cimarron Hills, and Ellicott. The city list stays as a
        # fallback for when geocoding returns no county.
        origin_lower = actual_origin.lower()
        dest_lower = actual_dest.lower()

        el_paso_cities = [
            "colorado springs", "monument", "manitou springs", "fountain",
            "peyton", "falcon", "calhan", "ramah", "green mountain falls",
            "palmer lake", "cascade", "chipita park", "usaf academy",
            "schriever", "peterson", "fort carson", "el paso county"
        ]
        teller_cities = ["woodland park", "divide", "florissant", "cripple creek", "victor", "teller county"]

        def county_of(address: str) -> str:
            try:
                geo = gmaps.geocode(address)
                if geo:
                    for comp in geo[0].get('address_components', []):
                        if 'administrative_area_level_2' in comp.get('types', []):
                            return comp.get('long_name', '').lower()
            except Exception as geo_err:
                logging.warning(f"County lookup failed for {address}: {geo_err}")
            return ""

        origin_county = county_of(actual_origin)
        dest_county = county_of(actual_dest)

        is_origin_local = 'el paso' in origin_county if origin_county else any(city in origin_lower for city in el_paso_cities)
        is_dest_local = 'el paso' in dest_county if dest_county else any(city in dest_lower for city in el_paso_cities)
        is_teller_county = (
            'teller' in origin_county or 'teller' in dest_county
            or any(city in origin_lower for city in teller_cities)
            or any(city in dest_lower for city in teller_cities)
        )
        is_out_of_county = not (is_origin_local and is_dest_local)

        pricing = PricingEngine()
        
        if quote_type == 'bundle':
            quote_data = pricing.calculate_bundle_price(
                distance_miles=total_dist_miles,
                is_teller_county=is_teller_county
            )
        else:
            quote_data = pricing.calculate_trip_price(
                distance_miles=dist_miles,
                stops_count=len(valid_stops),
                wait_time_hours=wait_hours,
                customer_email=customer_email,
                is_out_of_county=is_out_of_county,
                is_teller_county=is_teller_county
            )
            if trip_type == 'round-trip':
                # Price the return leg exactly like a separate a-la-carte trip:
                # its own base fare, free-mile window, and stop fees. The
                # layover wait fee is already counted on the outbound leg.
                return_quote = pricing.calculate_trip_price(
                    distance_miles=return_dist_miles,
                    stops_count=len(valid_return_stops),
                    wait_time_hours=0.0,
                    customer_email=customer_email,
                    is_out_of_county=is_out_of_county,
                    is_teller_county=is_teller_county
                )
                for key in ("baseFare", "overage", "deadheadFee", "stopFee", "tellerFee", "waitFee", "total"):
                    quote_data[key] = round(quote_data[key] + return_quote[key], 2)

        if trip_type == 'round-trip':
            dur_text = f"{(total_duration_sec + return_duration_sec) // 60} mins (round trip)"

        quote_data["debug"] = {
            "duration": dur_text,
            "miles": f"{total_dist_miles:.1f}",
            "origin": actual_origin,
            "destination": actual_dest
        }
        quote_data["time"] = (total_duration_sec + return_duration_sec) // 60
        quote_data["distance"] = round(total_dist_miles, 1)
            
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
        
        # We now return 200 for ALL errors we catch here, to allow the frontend to show the message
        # instead of a generic 500 Error toast.
        return func.HttpResponse(
            json.dumps({
                "success": False, 
                "error": error_msg,
                "type": e.__class__.__name__,
                "traceback": tb if os.environ.get("DEBUG_PRICING", "true") == "true" else None
            }),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
