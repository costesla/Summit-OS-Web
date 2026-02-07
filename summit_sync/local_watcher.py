import os
import time
import logging
import requests
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
# Hardcoded local path as requested
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "uploads" 
FUNCTION_URL = os.environ.get("AZURE_FUNCTION_URL")
FUNCTION_KEY = os.environ.get("AZURE_FUNCTION_KEY")

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class ImageHandler(FileSystemEventHandler):
    def __init__(self, blob_service_client):
        self.blob_service_client = blob_service_client

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = event.src_path
        if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            return

        # Wait a moment for file write to complete
        time.sleep(1) 
        self.upload_file(filename)

    def upload_file(self, local_path):
        try:
            # Calculate relative path to preserve "Block X/Trip Y" structure
            # Example: ...\2026\Block 1\Trip 1\img.jpg -> Block 1/Trip 1/img.jpg
            relative_path = os.path.relpath(local_path, WATCH_DIR)
            blob_name = relative_path.replace("\\", "/")
            
            logging.info(f"Detected: {relative_path}")
            
            if not self.blob_service_client:
                 logging.warning("No Blob Client. Skipping upload.")
                 return

            container_client = self.blob_service_client.get_container_client(CONTAINER_NAME)
            
            # Create container if not exists
            if not container_client.exists():
                container_client.create_container()

            with open(local_path, "rb") as data:
                container_client.upload_blob(name=blob_name, data=data, overwrite=True)
            
            logging.info(f"Uploaded to Azure: {blob_name}")

            # Trigger Azure Function
            if FUNCTION_URL:
                self.trigger_function(blob_name)
            else:
                logging.warning("AZURE_FUNCTION_URL not set. Skipping function trigger.")

        except Exception as e:
            logging.error(f"Failed to upload {local_path}: {e}")

    def trigger_function(self, blob_name):
        try:
            # Construct the absolute blob URL
            # Note: Standardizing on summitstoreus23436 as per .env
            account_name = CONNECTION_STRING.split("AccountName=")[1].split(";")[0]
            blob_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
            
            payload = {"blob_url": blob_url}
            params = {"code": FUNCTION_KEY} if FUNCTION_KEY else {}
            
            logging.info(f"Triggering function for: {blob_url}")
            response = requests.post(FUNCTION_URL, json=payload, params=params, timeout=30)
            
            if response.status_code == 200:
                logging.info(f"Successfully triggered function: {response.json().get('status')}")
            else:
                logging.error(f"Function trigger failed ({response.status_code}): {response.text}")
        except Exception as e:
            logging.error(f"Error triggering function: {e}")

if __name__ == "__main__":
    if not os.path.exists(WATCH_DIR):
        logging.error(f"Watch directory does not exist: {WATCH_DIR}")
        exit(1)

    logging.info(f"Starting Summit Sync Watcher...")
    logging.info(f"Watching: {WATCH_DIR}")

    blob_service = None
    if CONNECTION_STRING:
        try:
            blob_service = BlobServiceClient.from_connection_string(CONNECTION_STRING)
            logging.info("Connected to Azure Storage.")
        except Exception as e:
            logging.error(f"Invalid Connection String: {e}")
            logging.warning("Running in local-only mode (no upload).")
    else:
        logging.warning("AZUREWEBJOBSSTORAGE not found in .env. Running in local-only mode.")

    event_handler = ImageHandler(blob_service)
    
    # --- Charging Session Monitor (Background Thread) ---
    def poll_charging_sessions():
        logging.info("Starting background charging monitor (30 min interval)...")
        # Late imports to avoid circular issues
        from lib.tessie import TessieClient
        from lib.database import DatabaseClient
        
        tessie = TessieClient()
        db = DatabaseClient()
        vin = os.environ.get("TESSIE_VIN")

        while True:
            try:
                if vin:
                    now = datetime.now()
                    today_start = datetime(now.year, now.month, now.day)
                    ts_start = int(today_start.timestamp())
                    ts_end = int(now.timestamp())
                    
                    charges = tessie.get_charges(vin, ts_start, ts_end)
                    if charges:
                        if len(charges) > 1:
                            logging.warning(f"!!! ALERT: {len(charges)} CHARGING SESSIONS DETECTED TODAY !!!")
                        
                        for charge in charges:
                            session_id = str(charge.get('id', ''))
                            if not session_id: continue
                            
                            charge_data = {
                                "session_id": session_id,
                                "start_time": datetime.fromtimestamp(charge.get('started_at')) if charge.get('started_at') else None,
                                "end_time": datetime.fromtimestamp(charge.get('finished_at')) if charge.get('finished_at') else None,
                                "location": charge.get('location', 'Unknown'),
                                "start_soc": charge.get('starting_battery'),
                                "end_soc": charge.get('ending_battery'),
                                "energy_added": charge.get('charge_energy_added'),
                                "cost": charge.get('cost', 0.0),
                                "duration": charge.get('duration_minutes', 0.0)
                            }
                            db.save_charge(charge_data)
                else:
                    logging.info("Background Check: No new charging sessions.")
            except Exception as e:
                logging.error(f"Error in background charging monitor: {e}")
            
            time.sleep(1800) # Check every 30 minutes

    charging_thread = threading.Thread(target=poll_charging_sessions, daemon=True)
    charging_thread.start()

    # --- Initial Scan (Today's Files Only) ---
    today_str = datetime.now().strftime("%Y%m%d")
    logging.info(f"Scanning for existing screenshots from TODAY ({today_str})...")
    
    scan_count = 0
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            # Filter: Only process files with today's date string in the name
            if today_str in file and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                event_handler.upload_file(full_path)
                scan_count += 1
    
    logging.info(f"Initial scan complete. Processed {scan_count} items from today.")

    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
