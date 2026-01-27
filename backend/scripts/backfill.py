
import os
import logging
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Configuration
load_dotenv()
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "function-releases" 
TARGET_DATE_STR = "20260116" # Filter for files containing this string

def backfill():
    if not CONNECTION_STRING:
        logging.error("AZUREWEBJOBSSTORAGE not found in .env")
        return

    try:
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        if not container_client.exists():
            container_client.create_container()
            
        logging.info(f"Scanning {WATCH_DIR} for files matching '{TARGET_DATE_STR}'...")
        
        count = 0
        for root, dirs, files in os.walk(WATCH_DIR):
            for file in files:
                if TARGET_DATE_STR in file and file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    local_path = os.path.join(root, file)
                    relative_path = os.path.relpath(local_path, WATCH_DIR)
                    blob_name = relative_path.replace("\\", "/") # Ensure forward slashes for URL
                    
                    logging.info(f"Uploading: {blob_name}")
                    
                    with open(local_path, "rb") as data:
                        container_client.upload_blob(name=blob_name, data=data, overwrite=True)
                    count += 1
        
        logging.info(f"Backfill complete. Uploaded {count} files.")

    except Exception as e:
        logging.error(f"Error during backfill: {e}")

if __name__ == "__main__":
    backfill()
