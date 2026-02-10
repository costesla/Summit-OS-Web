import os
import time
import requests
import logging
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "uploads" 
FUNCTION_URL = "http://localhost:7071/api/process-blob" # Default to local if not set?
# Actually, the user has a function app running? 
# In local_watcher it uses: os.environ.get("AZURE_FUNCTION_URL")
# I should use that or default to the deployed one if available.
# But "AZURE_FUNCTION_URL" might be in .env.

FUNCTION_URL = os.environ.get("AZURE_FUNCTION_URL")
FUNCTION_KEY = os.environ.get("AZURE_FUNCTION_KEY")

if not FUNCTION_URL:
    logging.warning("AZURE_FUNCTION_URL not set in .env")

if not CONNECTION_STRING:
    logging.error("AZUREWEBJOBSSTORAGE not set!")
    exit(1)

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

def trigger_function(blob_name):
    try:
        account_name = CONNECTION_STRING.split("AccountName=")[1].split(";")[0]
        blob_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
        
        payload = {"blob_url": blob_url}
        params = {"code": FUNCTION_KEY} if FUNCTION_KEY else {}
        
        logging.info(f"Triggering function for: {blob_url}")
        response = requests.post(FUNCTION_URL, json=payload, params=params, timeout=60)
        
        if response.status_code == 200:
            logging.info(f"Success: {response.json()}")
        else:
            logging.error(f"Failed ({response.status_code}): {response.text}")
    except Exception as e:
        logging.error(f"Error triggering function: {e}")

def process_recent_files(days=3):
    now = time.time()
    cutoff = now - (days * 86400)
    
    logging.info(f"Scanning for files modified in the last {days} days...")
    
    count = 0
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            full_path = os.path.join(root, file)
            mtime = os.path.getmtime(full_path)
            
            if mtime > cutoff and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Filter for Trip-related files
                if any(x in file for x in ["Uber", "Venmo", "Call", "Message", "Map", "Tesla"]):
                    logging.info(f"Processing: {file}")
                    
                    # Upload
                    relative_path = os.path.relpath(full_path, WATCH_DIR)
                    blob_name = relative_path.replace("\\", "/")
                    
                    with open(full_path, "rb") as data:
                        container_client.upload_blob(name=blob_name, data=data, overwrite=True)
                    
                    # Trigger
                    trigger_function(blob_name)
                    count += 1
                    time.sleep(1) # Pace it slightly

    logging.info(f"Processed {count} files.")

if __name__ == "__main__":
    process_recent_files(days=3)
