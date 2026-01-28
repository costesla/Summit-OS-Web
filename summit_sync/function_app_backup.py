import logging
import time
import datetime
import os
import azure.functions as func
from lib.ocr import OCRClient
from lib.tessie import TessieClient
from lib.database import DatabaseClient

app = func.FunctionApp()

@app.blob_trigger(arg_name="myblob", path="function-releases/{name}", connection="AzureWebJobsStorage")
def automation_trigger(myblob: func.InputStream):
    logging.info(f"Python Blob trigger processed blob \nName: {myblob.name}")
    
    # 1. Parse Blob Data
    blob_url = myblob.uri
    # Use current time as fallback for event time
    timestamp_epoch = time.time()
    
    if not blob_url:
        logging.error("No URL found in blob.")
        return

    logging.info(f"Processing blob: {blob_url}")

    # Extract Block and Trip context from URL
    # Expected format: .../Block%201/Trip%204/...
    # Decode URL first
    from urllib.parse import unquote
    decoded_url = unquote(blob_url)
    
    import re
    block_match = re.search(r"Block\s?(\d+)", decoded_url, re.IGNORECASE)
    trip_match = re.search(r"Trip\s?(\d+)", decoded_url, re.IGNORECASE)
    
    block_name = f"Block {block_match.group(1)}" if block_match else "Unknown Block"
    trip_id = f"Trip {trip_match.group(1)}" if trip_match else "Unknown Trip"
    
    logging.info(f"Context: {block_name} | {trip_id}")

    # 2. OCR & Classification
    ocr = OCRClient()
    raw_text = ocr.extract_text(blob_url)
    
    if not raw_text:
        logging.error("OCR returned no text.")
        return

    classification = ocr.classify_image(raw_text)
    logging.info(f"Classification: {classification}")

    trip_data = {
        "block_name": block_name,
        "trip_id": trip_id,
        "classification": classification,
        "source_url": blob_url,
        "raw_text": raw_text[:500] # store partial text for context
    }

    # 3. Routing Logic
    if classification == "Uber_Core":
        # Parse Financials
        parsed_data = ocr.parse_ubertrip(raw_text)
        trip_data.update(parsed_data)
        logging.info(f"Parsed Uber Financials: {parsed_data.get('rider_payment')}")

    elif classification == "Expense":
        trip_data["type"] = "Business Expense"
        # Can add specific expense parsing here if needed
    
    else:
        # Default Private Trip Logic (Evergreen Rules)
        trip_data["fare"] = 20.00 # Default Private Fare
        trip_data["tip"] = 0.00
        if "Venmo" in raw_text:
            trip_data["payment_method"] = "Venmo"
        elif "Cash" in raw_text:
            trip_data["payment_method"] = "Cash"
        else:
            trip_data["payment_method"] = "Pending"

    # 4. Enrich with Tessie (Drive Telemetry)
    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")
    
    # Matches logic: Private trips OR standard Uber trips need telemetry
    # "Private Service Bridge" logic for non-Uber
    is_private = (classification != "Uber_Core") or ("Venmo" in raw_text)

    if vin:
        drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
        if drive:
            trip_data['tessie_drive_id'] = drive.get('id')
            trip_data['tessie_distance'] = drive.get('distance_miles')
            trip_data['tessie_duration'] = drive.get('duration_minutes')
            trip_data['start_location'] = drive.get('starting_address')
            trip_data['end_location'] = drive.get('ending_address')
            
            # Deadhead Efficiency Calculation (Uber Miles vs Actual Miles)
            if trip_data.get("distance_miles") and trip_data.get("tessie_distance"):
                 trip_data["efficiency_gap"] = trip_data["tessie_distance"] - trip_data["distance_miles"]
            
            logging.info(f"Enriched with drive: {drive.get('id')}")
    
    # 5. Save to Database
    db = DatabaseClient()
    db.save_trip(trip_data) # Check if schema supports new columns first
    logging.info(f"Data ready for DB: {trip_data.keys()}")

