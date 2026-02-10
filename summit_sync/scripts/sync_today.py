
import os
import sys
import time
import logging
import hashlib
import re
from datetime import datetime, timedelta

# Add path for lib imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.ocr import OCRClient
from lib.database import DatabaseClient
from lib.tessie import TessieClient
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "uploads"

# Clients
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)
ocr = OCRClient()
db = DatabaseClient()
tessie = TessieClient()

def get_today_file_candidates():
    candidates = []
    now = datetime.now()
    today_str = now.strftime("%Y%m%d") # e.g., 20260129
    
    logging.info(f"Scanning {WATCH_DIR} for files matching {today_str}...")
    
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.png')) and today_str in file:
                candidates.append(os.path.join(root, file))
    
    return candidates

def is_trip_in_db(filename):
    # Check if a trip with this source URL exists
    # Approximate check using filename in SourceURL
    query = "SELECT COUNT(*) as count FROM Trips WHERE SourceURL LIKE ?"
    params = (f"%{filename}%",)
    try:
        results = db.execute_query_with_results(query.replace("?", f"'%{filename}%'")) # Safe enough for local script
        count = results[0]['count']
        return count > 0
    except:
        return False

def process_file(full_path):
    filename = os.path.basename(full_path)
    if is_trip_in_db(filename):
        logging.info(f"Skipping {filename} (Already in DB)")
        return

    logging.info(f"Processing new file: {filename}")
    
    # 1. Upload to Blob
    blob_name = filename
    with open(full_path, "rb") as data:
        container_client.upload_blob(name=blob_name, data=data, overwrite=True)
    
    account_name = CONNECTION_STRING.split("AccountName=")[1].split(";")[0]
    blob_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"

    # 2. OCR (Local Stream)
    raw_text = ocr.extract_text_from_stream(full_path)
    if not raw_text:
        logging.warning(f"OCR failed for {filename}")
        return

    # 3. Classify & Parse
    classification = "Uber_Core" if "Uber" in filename else ocr.classify_image(raw_text)
    
    # Generate ID
    file_hash = hashlib.md5(filename.encode()).hexdigest()[:10]
    trip_id = f"M_{int(time.time())}_{file_hash}"
    
    trip_data = {
        "block_name": "Sync Run",
        "trip_id": trip_id,
        "classification": classification,
        "source_url": blob_url,
        "timestamp_epoch": os.path.getmtime(full_path),
        "raw_text": raw_text[:500],
        "is_cdot_reportable": False
    }

    # Extract Details based on type
    suffix = None
    suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", filename)
    if suffix_match: suffix = suffix_match.group(1)

    if "Uber" in filename or classification == "Uber_Core":
         parsed_data = ocr.parse_ubertrip(raw_text, suffix)
         trip_data.update(parsed_data)
         trip_data["trip_type"] = "Uber"
         
    else:
         # Private Trip Logic
         trip_data["trip_type"] = "Private"
         trip_data["fare"] = 0.00
         
         STATIC_PASSENGERS = ["Esmeralda Dsilva", "Jacuelyn Heslep", "Omar Stovall"]
         pass_data = ocr.parse_passenger_context(raw_text, STATIC_PASSENGERS)
         
         if pass_data.get("passenger_firstname"):
              trip_data["passenger_firstname"] = pass_data["passenger_firstname"]
              trip_data["classification"] = "Private_Trip"
              trip_data["is_cdot_reportable"] = True
              trip_data["payment_method"] = pass_data.get("payment_method", "Venmo")
         else:
              # Check for "Call" or "Message" context
              if "Call" in filename or "Message" in filename:
                  trip_data["classification"] = "Private_Trip"
                  trip_data["is_cdot_reportable"] = True
                  trip_data["payment_method"] = "Pending"

    logging.info(f"Saving Trip: {trip_data.get('classification')} | Pass: {trip_data.get('passenger_firstname')}")
    db.save_trip(trip_data)


def file_time_match(file_datetime, drive):
    # Helper to match file time (end of trip) to drive time
    if not drive.get('ending_time'): return False
    drive_end = datetime.fromtimestamp(drive['ending_time'])
    diff = abs((file_datetime - drive_end).total_seconds())
    return diff < 3600 # 1 hour tolerance

def sync_tessie_data():
    logging.info("Syncing Tessie Data...")
    vin = os.environ.get("TESSIE_VIN")
    if not vin: return

    now = int(time.time())
    start_of_day = now - (24 * 3600) # Last 24h
    drives = tessie.get_drives(vin, start_of_day, now)
    
    if not drives:
        logging.info("No recent Tessie drives found.")
        return

    # Fetch today's trips from DB. Use Timestamp_Offer (File Creation Time) for accurate matching.
    query = "SELECT TripID, Timestamp_Offer, TripType FROM Trips WHERE CreatedAt > CAST(GETDATE() AS DATE)"
    db_trips = db.execute_query_with_results(query)
    
    updated_count = 0
    
    for trip in db_trips:
         trip_id = trip['TripID']
         # Use Timestamp_Offer if available, otherwise fall back to CreatedAt
         trip_time = trip.get('Timestamp_Offer') or trip['CreatedAt'] 
         
         # Match with Tessie Drive
         matched_drive = None
         
         for drive in drives:
             if not drive.get('ending_time'): continue
             drive_end = datetime.fromtimestamp(drive['ending_time'])
             
             delta = abs((trip_time - drive_end).total_seconds())
             if delta < 3600: # 1 hour match window
                 matched_drive = drive
                 break
         
         if matched_drive:
             # Prepare update
             update_fields = {}
             
             # Map Stats
             miles = matched_drive.get('distance_miles') or (matched_drive.get('odometer_distance') if matched_drive.get('odometer_distance') else 0)
             # Tessie might return meters or arbitrary units, assuming miles based on previous code context, but verify API. 
             # Usually output is user pref. Assuming miles for now.
             
             if miles:
                 update_fields["Distance_Miles"] = float(miles)
             
             duration = matched_drive.get('duration_minutes')
             if duration:
                  update_fields["Duration_Minutes"] = int(duration)
                  
             # Map Tag -> Classification or Notes
             tag = matched_drive.get('tag')
             if tag:
                 # If tag contains "PT", map to Private_Trip
                 if "PT" in tag.upper():
                     update_fields["Classification"] = "Private_Trip"
                     update_fields["TripType"] = "Private"
                 update_fields["Notes"] = tag # Save tag to notes

             # Perform Update
             if update_fields:
                 set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
                 values = list(update_fields.values())
                 values.append(trip_id)
                 
                 sql = f"UPDATE Trips SET {set_clause} WHERE TripID = ?"
                 try:
                    db.execute_non_query(sql, tuple(values))
                    updated_count += 1
                    logging.info(f"Updated Trip {trip_id} with Tessie Data (Tag: {tag})")
                 except Exception as e:
                    logging.error(f"Failed to update trip {trip_id}: {e}")

    logging.info(f"Sync Complete. Updated {updated_count} trips with Tessie data.")


def run():
    logging.info("--- STARTING SYNC ---")
    
    # 1. Process New Files
    candidates = get_today_file_candidates()
    for c in candidates:
        process_file(c)
        
    # 2. Sync Tessie
    sync_tessie_data()
    
    logging.info("--- SYNC FINISHED ---")

if __name__ == "__main__":
    run()
