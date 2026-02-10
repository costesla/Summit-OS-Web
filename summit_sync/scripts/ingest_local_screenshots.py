import os
import sys
import logging
import hashlib
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
STORAGE_ACCOUNT = "stsummitosprod" # From .env knowledge

def ingest_folder():
    ocr = OCRClient()
    db = DatabaseClient()
    tessie = TessieClient()
    
    vin = os.environ.get("TESSIE_VIN")
    
    logging.info(f"Scanning {WATCH_DIR}...")
    
    count = 0
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            # Filter: Process ONLY Jan 27th, 2026
            if "20260127" not in file:
                continue

            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                
                # Rate Limiting: Sleep 3s between calls to avoid 429
                import time
                time.sleep(3)
                
                # 1. Construct the "Source URL" to maintain ID consistency with Cloud
                relative_path = os.path.relpath(full_path, WATCH_DIR)
                blob_name = relative_path.replace("\\", "/")
                blob_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
                
                logging.info(f"Processing: {file}")
                
                try:
                    # 2. OCR (Local Stream)
                    raw_text = ocr.extract_text_from_stream(full_path)
                    if not raw_text:
                        logging.warning(f"No text found in {file}")
                        continue
                        
                    # 3. Classify & Parse
                    classification = ocr.classify_image(raw_text)
                    trip_data = {
                        "classification": classification,
                        "source_url": blob_url,
                        "timestamp_epoch": os.path.getmtime(full_path), # Use file modified time as approximation
                        "raw_text": raw_text[:500]
                    }
                    
                    if classification == "Uber_Core":
                        parsed = ocr.parse_ubertrip(raw_text)
                        trip_data.update(parsed)
                        logging.info(f" > Identified Uber Trip: ${trip_data.get('driver_total')} Earnings")
                        
                    elif classification == "Expense":
                        # Skip expenses for now or log generic
                        logging.info(" > Identified Expense (Skipping for now)")
                        continue
                    else:
                        logging.info(f" > Classified as {classification} (Skipping if not Uber)")
                        # strict mode for this run
                        if "Uber" not in classification: 
                            continue

                    # 4. Tessie Match (if available)
                    if vin:
                        # Attempt to find a drive near the screenshot time
                        drive = tessie.match_drive_to_trip(vin, trip_data['timestamp_epoch'])
                        if drive:
                            trip_data['tessie_drive_id'] = drive.get('id')
                            trip_data['tessie_distance'] = drive.get('distance_miles')
                            trip_data['tessie_duration'] = drive.get('duration_minutes')
                            logging.info(f" > Matched Tessie Drive: {drive.get('distance_miles')} mi")

                    # 5. Save
                    db.save_trip(trip_data)
                    count += 1
                    
                except Exception as e:
                    logging.error(f"Failed to process {file}: {e}")

    logging.info(f"Ingestion Complete. Processed {count} files.")

if __name__ == "__main__":
    ingest_folder()
