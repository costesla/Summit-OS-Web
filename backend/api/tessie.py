import logging
import azure.functions as func
import json
import os
from services.tessie import TessieClient

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="vehicle-location", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_location(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Vehicle location requested via Blueprint")
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())
    
    try:
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return func.HttpResponse("TESSIE_VIN not configured", status_code=500)
            
        data = tessie.get_public_state(vin)
        return func.HttpResponse(
            json.dumps(data),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Tessie Error: {str(e)}")
        return func.HttpResponse(str(e), status_code=500)
