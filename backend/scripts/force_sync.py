import os
import time
import logging
import re
import pyodbc
import argparse
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
import sys

# Add parent directory to sys.path so 'lib' can be found
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lib.ocr import OCRClient
from lib.tessie import TessieClient
from lib.database import DatabaseClient

# Load environment variables
load_dotenv()

# --- Configuration ---
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Suppress verbose Azure SDK logs
logging.getLogger('azure.identity').setLevel(logging.WARNING)
logging.getLogger('azure.core').setLevel(logging.WARNING)
logging.getLogger('azure.storage').setLevel(logging.WARNING)

def process_file_locally(local_path, ocr, tessie, db):
    try:
        logging.info(f"--- Processing: {os.path.basename(local_path)} ---")
        
        # 1. Detect Context from Path
        block_match = re.search(r"Block\s?(\d+)", local_path, re.IGNORECASE)
        trip_match = re.search(r"Trip\s?(\d+)", local_path, re.IGNORECASE)
        block_name = f"Block {block_match.group(1)}" if block_match else "Unknown Block"
        trip_id_raw = f"Trip {trip_match.group(1)}" if trip_match else "Unknown Trip"
        
        # 2. Upload to Azure (so the image is stored)
        storage_conn = os.environ.get("AZUREWEBJOBSSTORAGE")
        if not storage_conn:
            logging.error("Missing AZUREWEBJOBSSTORAGE connection string.")
            return

        blob_service = BlobServiceClient.from_connection_string(storage_conn)
        container_client = blob_service.get_container_client("function-releases")
        relative_path = os.path.relpath(local_path, WATCH_DIR)
        blob_name = relative_path.replace("\\", "/")
        
        with open(local_path, "rb") as data:
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)
        blob_url = f"https://summitstoreus23436.blob.core.windows.net/function-releases/{blob_name}"

        # 3. OCR & Processing (Using Stream to bypass PermissionDenied)
        raw_text = ocr.extract_text_from_stream(local_path)
        if not raw_text:
            logging.error("OCR failed to get text via stream.")
            return

        classification = ocr.classify_image(raw_text)
        
        # 3. Extract Timestamp (Filenames are more reliable than mtime for backfills)
        timestamp_epoch = os.path.getmtime(local_path)
        filename = os.path.basename(local_path)
        # Pattern: Screenshot_20260116_075250
        time_match = re.search(r"(\d{8})_(\d{6})", filename)
        if time_match:
            date_str = time_match.group(1)
            time_str = time_match.group(2)
            try:
                from datetime import datetime
                dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                timestamp_epoch = dt.timestamp()
                logging.info(f"Using filename timestamp: {dt}")
            except Exception as e:
                logging.warning(f"Failed to parse timestamp from filename {filename}: {e}")

        trip_data = {
            "block_name": block_name,
            "trip_id": trip_id_raw,
            "classification": classification,
            "source_url": blob_url,
            "timestamp_epoch": timestamp_epoch,
            "raw_text": raw_text[:500]
        }

        # Uber Financials
        if classification == "Uber_Core":
            parsed_data = ocr.parse_ubertrip(raw_text)
            trip_data.update(parsed_data)
        elif classification == "Expense":
            trip_data["type"] = "Business Expense"
        else:
            trip_data.update({
                "fare": 20.00,
                "tip": 0.00,
                "payment_method": "Venmo" if "Venmo" in raw_text else "Pending",
                "rider": "Private Trip"
            })

        # 4. Tessie Enrichment
        vin = os.environ.get("TESSIE_VIN")
        if vin:
            is_private = (classification != "Uber_Core") or ("Venmo" in raw_text)
            drive = tessie.match_drive_to_trip(vin, timestamp_epoch, is_private=is_private)
            if drive:
                trip_data['tessie_drive_id'] = drive.get('id')
                trip_data['tessie_distance'] = drive.get('distance_miles')
                trip_data['tessie_duration'] = drive.get('duration_minutes')
                trip_data['start_location'] = drive.get('starting_address')
                trip_data['end_location'] = drive.get('ending_address')

        # 5. Save to Database DIRECTLY
        db.save_trip(trip_data)
        logging.info(f"✅ SUCCESSFULLY SYNCED: {trip_id_raw}")

    except Exception as e:
        logging.error(f"Failed to process {local_path}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Force sync local images to Azure.")
    parser.add_argument("--date", type=str, help="Specific date to filter (YYYYMMDD), e.g., 20260116")
    args = parser.parse_args()

    # Initialize shared clients
    ocr = OCRClient()
    tessie = TessieClient()
    db = DatabaseClient()

    logging.info(f"Starting LOCAL FORCE SYNC... (Filter: {'None' if not args.date else args.date})")
    
    total_found = 0
    total_processed = 0
    
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                total_found += 1
                
                # Date filtering logic
                if args.date:
                    if args.date not in file:
                        continue
                
                full_path = os.path.join(root, file)
                process_file_locally(full_path, ocr, tessie, db)
                total_processed += 1
                
                # Small delay to avoid 429 Rate Limit (F0 tier is quite strict: 20 per min)
                time.sleep(3.5)
    
    logging.info(f"\n--- COMPLETE ---")
    logging.info(f"Total files found: {total_found}")
    logging.info(f"Total files processed: {total_processed}")
