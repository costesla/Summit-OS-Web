
import os
import sys
import re
import time
import logging
from datetime import datetime

# Add path for lib imports
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.ocr import OCRClient
from lib.database import DatabaseClient
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "uploads"

# Setup Clients
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)
ocr = OCRClient()
db = DatabaseClient()

def process_file_locally(filename):
    logging.info(f"Processing local file: {filename}")
    
    # 1. Upload to Blob (to have a URL)
    full_path = os.path.join(WATCH_DIR, filename)
    blob_name = filename # Simple name for manual process
    
    with open(full_path, "rb") as data:
        container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    
    # Construct URL
    account_name = CONNECTION_STRING.split("AccountName=")[1].split(";")[0]
    blob_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
    
    # 2. Extract Text (Use Stream to avoid URL access issues)
    logging.info("Extracting text from stream...")
    raw_text = ocr.extract_text_from_stream(full_path)
    if not raw_text:
        logging.error("OCR returned empty text.")
        return

    # 3. Logic (Simplified from function_app.py)
    suffix = None
    suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", filename)
    if suffix_match:
         suffix = suffix_match.group(1)

    classification = "Uber_Core" if "Uber" in filename else ocr.classify_image(raw_text)
    
    import hashlib
    file_hash = hashlib.md5(filename.encode()).hexdigest()[:10]
    trip_data = {
        "block_name": "Manual Run",
        "trip_id": f"M_{int(time.time())}_{file_hash}",
        "classification": classification,
        "source_url": blob_url,
        "timestamp_epoch": time.time(),
        "raw_text": raw_text[:500],
        "is_cdot_reportable": False
    }

    if suffix == "RD":
         route_data = ocr.parse_route_details(raw_text)
         trip_data["pickup_address_full"] = route_data.get("pickup_address")
         trip_data["dropoff_address_full"] = route_data.get("dropoff_address")
         basic_data = ocr.parse_ubertrip(raw_text, suffix)
         trip_data.update(basic_data)
         
    elif "Uber" in filename or classification == "Uber_Core":
         parsed_data = ocr.parse_ubertrip(raw_text, suffix)
         trip_data.update(parsed_data)
         
    elif classification == "Expense":
         trip_data["type"] = "Business Expense"
         pass_data = ocr.parse_passenger_context(raw_text, ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"])
         if pass_data.get("passenger_firstname"):
              trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
              trip_data["classification"] = "Private_Trip"
              trip_data["is_cdot_reportable"] = True
              trip_data["payment_method"] = "Venmo"
    else:
         # Private Trip Logic
         trip_data["fare"] = 20.00
         
         STATIC_PASSENGERS = ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"]
         pass_data = ocr.parse_passenger_context(raw_text, STATIC_PASSENGERS)
         
         if pass_data.get("passenger_firstname"):
              trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
              trip_data["classification"] = "Private_Trip"
              trip_data["is_cdot_reportable"] = True
              trip_data["payment_method"] = pass_data.get("payment_method", "Venmo")
         else:
              trip_data["payment_method"] = "Venmo" if "Venmo" in raw_text else "Pending"
              if "Venmo" in raw_text or "Call" in filename or "Message" in filename:
                  trip_data["is_cdot_reportable"] = True
                  trip_data["classification"] = "Private_Trip"

    logging.info(f"Saving Trip: {trip_data.get('classification')} - {trip_data.get('passenger_firstname')}")
    db.save_trip(trip_data)


def run():
    target_files = [
        "Screenshot_20260129_110004_Uber Driver.jpg",
        "Screenshot_20260129_111136_Uber Driver.jpg",
        "Screenshot_20260129_111758_Uber Driver.jpg",
        "Screenshot_20260129_112632_Uber Driver.jpg",
        "Screenshot_20260129_153920_Call.jpg",
        "Screenshot_20260129_153955_Call.jpg"
    ]
    
    for f in target_files:
        try:
            process_file_locally(f)
        except Exception as e:
            logging.error(f"Failed to process {f}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    run()
