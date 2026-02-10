import logging
import azure.functions as func
import json
import os
import googlemaps
from services.pricing import PricingEngine

bp = func.Blueprint()

@bp.route(route="quote", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def quote(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Pricing quote requested via Blueprint")
    
    try:
        req_body = req.get_json()
        pickup = req_body.get('pickup', '')
        dropoff = req_body.get('dropoff', '')
        customer_email = req_body.get('email', req_body.get('customerEmail', ''))
        
        gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not gmaps_key:
            raise Exception("Google Maps API Key missing from environment")
            
        gmaps = googlemaps.Client(key=gmaps_key)
        res = gmaps.distance_matrix(origins=[pickup], destinations=[dropoff], mode="driving")
        
        if res['status'] != 'OK':
            raise Exception(f"Google Maps Error: {res['status']}")
            
        element = res['rows'][0]['elements'][0]
        if element.get('status') != 'OK':
             raise Exception(f"Route not found: {element.get('status')}")
             
        dist_miles = element['distance']['value'] * 0.000621371
        dur_text = element['duration']['text']

        pricing = PricingEngine()
        quote_data = pricing.calculate_trip_price(
            distance_miles=dist_miles,
            customer_email=customer_email  # Pass customer email for pricing lookup
        )
        quote_data["debug"] = {"duration": dur_text, "miles": f"{dist_miles:.1f}"}
        
        import re
        try:
            quote_data["time"] = int(re.search(r"(\d+)\s*min", dur_text).group(1))
        except:
            quote_data["time"] = 0
            
        return func.HttpResponse(
            json.dumps({"success": True, "quote": quote_data}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Pricing Error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
