import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add summit_sync dir to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(root_dir, "summit_sync"))
from lib.ocr import OCRClient
from lib.database import DatabaseClient
from lib.tessie import TessieClient

# Load environment variables from summit_sync
load_dotenv(os.path.join(root_dir, "summit_sync", ".env"))
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def sync_path(target_path):
    endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
    if endpoint and endpoint.endswith("/"):
        os.environ["AZURE_VISION_ENDPOINT"] = endpoint[:-1]
    
    ocr = OCRClient()
    db = DatabaseClient()
    tessie = TessieClient()
    
    vin = os.environ.get("TESSIE_VIN")
    storage_account = "stsummitosprod"
    container_name = "uploads"
    
    # We'll use the root of the "Uber Driver" tree for relative paths to match expected blob structure
    root_watch_dir = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Uber Driver"
    
    logging.info(f"🚀 Starting Ingestion for path: {target_path}")
    
    if not os.path.exists(target_path):
        logging.error(f"Path does not exist: {target_path}")
        return

    count = 0
    for root, dirs, files in os.walk(target_path):
        # Sort files to try and process in chronological order
        files.sort()
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                
                # Rate Limiting
                import time
                time.sleep(1)
                
                # Construct Blob URL (relative to Uber Driver root)
                try:
                    relative_path = os.path.relpath(full_path, root_watch_dir)
                    blob_name = relative_path.replace("\\", "/")
                    blob_url = f"https://{storage_account}.blob.core.windows.net/{container_name}/{blob_name}"
                except ValueError:
                    # If not under Uber Driver root, just use filename
                    blob_url = f"https://{storage_account}.blob.core.windows.net/{container_name}/{file}"

                logging.info(f"Processing: {file}")
                
                try:
                    # 1. OCR (Local Stream)
                    raw_text = ocr.extract_text_from_stream(full_path)
                    if not raw_text:
                        logging.warning(f"No text found in {file}")
                        continue
                        
                    # 2. Extract Date/Time from filename
                    import re
                    # Example: Screenshot_20260504_172506...
                    ts_match = re.search(r"(\d{8})_(\d{6})", file)
                    if ts_match:
                        dt_str = f"{ts_match.group(1)} {ts_match.group(2)}"
                        t_obj = datetime.strptime(dt_str, "%Y%m%d %H%M%S")
                        timestamp_epoch = t_obj.timestamp()
                    else:
                        timestamp_epoch = os.path.getmtime(full_path)

                    # 3. Classify
                    classification = ocr.classify_image(raw_text)
                    
                    trip_data = {
                        "classification": classification,
                        "source_url": blob_url,
                        "timestamp_epoch": timestamp_epoch,
                        "raw_text": raw_text[:500],
                        "is_cdot_reportable": False
                    }
                    
                    # 4. Parse specific types
                    if classification == "Uber_Core":
                        parsed_data = ocr.parse_ubertrip(raw_text)
                        trip_data.update(parsed_data)
                    elif classification == "Private_Trip":
                        trip_data["is_cdot_reportable"] = True
                        # Try to find passenger
                        STATIC_PASSENGERS = ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"]
                        pass_data = ocr.parse_passenger_context(raw_text, STATIC_PASSENGERS)
                        if pass_data.get("passenger_firstname"):
                            trip_data["passenger_firstname"] = pass_data["passenger_firstname"]

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

    logging.info(f"\n✨ Path Sync Complete. Successfully processed {count} records.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sync_path(sys.argv[1])
    else:
        print("Usage: python sync_onedrive_path.py <full_path>")
