import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.ocr import OCRClient
from lib.database import DatabaseClient
from lib.tessie import TessieClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONTAINER_NAME = "uploads"
STORAGE_ACCOUNT = "stsummitosprod" 

def ingest_today():
    ocr = OCRClient()
    db = DatabaseClient()
    tessie = TessieClient()
    
    vin = os.environ.get("TESSIE_VIN")
    
    # Target date: Today Jan 30, 2026
    TARGET_DATE_STR = "20260130"
    logging.info(f"🚀 Starting Catch-up Ingestion for {TARGET_DATE_STR} (Mountain Time)...")
    
    count = 0
    for root, dirs, files in os.walk(WATCH_DIR):
        # Sort files to try and process in chronological order
        files.sort()
        for file in files:
            # Process files from today
            if TARGET_DATE_STR not in file:
                continue

            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                
                # Rate Limiting
                import time
                time.sleep(1)
                
                relative_path = os.path.relpath(full_path, WATCH_DIR)
                blob_name = relative_path.replace("\\", "/")
                blob_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
                
                logging.info(f"Processing: {file}")
                
                try:
                    # 1. OCR (Local Stream)
                    raw_text = ocr.extract_text_from_stream(full_path)
                    if not raw_text:
                        logging.warning(f"No text found in {file}")
                        continue
                        
                    # 2. Extract Suffix (e.g. FD, RD, ST, ED)
                    import re
                    suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", file)
                    suffix = suffix_match.group(1) if suffix_match else None
                    
                    # 3. Classify & Parse
                    classification = "Uber_Core" if suffix in ["FD", "ST", "ED", "RD"] else ocr.classify_image(raw_text)
                    
                    # Estimate timestamp from filename or modified time
                    # Filename: Screenshot_20260130_193608...
                    ts_match = re.search(r"(\d{8})_(\d{6})", file)
                    if ts_match:
                        dt_str = f"{ts_match.group(1)} {ts_match.group(2)}"
                        t_offer = datetime.strptime(dt_str, "%Y%m%d %H%M%S")
                        timestamp_epoch = t_offer.timestamp()
                    else:
                        timestamp_epoch = os.path.getmtime(full_path)

                    trip_data = {
                        "classification": classification,
                        "source_url": blob_url,
                        "timestamp_epoch": timestamp_epoch,
                        "raw_text": raw_text[:500],
                        "is_cdot_reportable": False
                    }
                    
                    # 4. Routing Logic (Same as function_app.py)
                    if suffix == "RD": # Route Details
                        route_data = ocr.parse_route_details(raw_text)
                        trip_data["pickup_address_full"] = route_data.get("pickup_address")
                        trip_data["dropoff_address_full"] = route_data.get("dropoff_address")
                        basic_data = ocr.parse_ubertrip(raw_text, suffix)
                        trip_data.update(basic_data)
                    elif suffix in ["FD", "ST", "ED"] or classification == "Uber_Core":
                        parsed_data = ocr.parse_ubertrip(raw_text, suffix)
                        trip_data.update(parsed_data)
                    else:
                        # Private Trip Check (Venmo etc)
                        STATIC_PASSENGERS = ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"]
                        pass_data = ocr.parse_passenger_context(raw_text, STATIC_PASSENGERS)
                        if pass_data.get("passenger_firstname"):
                            trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
                            trip_data["classification"] = "Private_Trip"
                            trip_data["is_cdot_reportable"] = True
                            trip_data["payment_method"] = pass_data.get("payment_method", "Venmo")
                        elif "Venmo" in raw_text or "Call" in file or "Message" in file:
                            trip_data["is_cdot_reportable"] = True
                            trip_data["classification"] = "Private_Trip"
                            trip_data["payment_method"] = "Venmo"

                    # 5. Tessie Match
                    if vin:
                         is_private = trip_data.get("is_cdot_reportable", False)
                         drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
                         if drive:
                             trip_data['tessie_drive_id'] = drive.get('id')
                             trip_data['tessie_distance'] = drive.get('distance_miles')
                             trip_data['tessie_distance_mi'] = drive.get('distance_miles')
                             trip_data['tessie_duration'] = drive.get('duration_minutes')
                             if not trip_data.get('start_location'): trip_data['start_location'] = drive.get('starting_address')
                             if not trip_data.get('end_location'): trip_data['end_location'] = drive.get('ending_address')

                    # 6. Save
                    db.save_trip(trip_data)
                    count += 1
                    logging.info(f" ✅ Saved: {classification} - {file}")
                    
                except Exception as e:
                    logging.error(f" ❌ Failed {file}: {e}")

    logging.info(f"\n✨ Catch-up Complete. Successfully processed {count} records for Jan 30th.")

if __name__ == "__main__":
    ingest_today()
