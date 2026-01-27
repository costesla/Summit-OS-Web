import logging
import azure.functions as func
import json
import time
import os
import traceback
from services.ocr import OCRClient
from services.tessie import TessieClient
from services.database import DatabaseClient

bp = func.Blueprint()

@bp.route(route="process-blob", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_blob_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("OCR Processing requested via Blueprint")
    try:
        req_body = req.get_json()
        blob_url = req_body.get('blob_url')
        if not blob_url:
            return func.HttpResponse("Missing blob_url", status_code=400)

        ocr = OCRClient()
        db = DatabaseClient()
        tessie = TessieClient()
        
        raw_text = ocr.extract_text(blob_url)
        if not raw_text:
            raise Exception("OCR failed to extract text")

        classification = ocr.classify_image(raw_text)
        timestamp_epoch = time.time()

        trip_data = {
            "classification": classification,
            "source_url": blob_url,
            "timestamp_epoch": timestamp_epoch,
            "raw_text": raw_text[:500]
        }

        if classification == "Uber_Core":
            parsed_data = ocr.parse_ubertrip(raw_text)
            trip_data.update(parsed_data)

        vin = os.environ.get("TESSIE_VIN")
        if vin:
            is_private = (classification != "Uber_Core") or ("Venmo" in raw_text)
            drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
            if drive:
                trip_data.update({
                    'tessie_drive_id': drive.get('id'),
                    'tessie_distance': drive.get('distance_miles'),
                    'start_location': drive.get('starting_address'),
                    'end_location': drive.get('ending_address')
                })

        db.save_trip(trip_data)

        if classification == "Environmental_Context":
            weather_data = ocr.parse_weather(raw_text)
            weather_data["source_url"] = blob_url
            db.save_weather(weather_data)
        
        return func.HttpResponse(
            json.dumps({"status": "success", "classification": classification}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"OCR Error: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
