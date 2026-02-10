import os
import time
import logging
import json
import requests
import pickle
import traceback
from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
CREDENTIALS_FILE = os.environ.get("GOOGLE_PHOTOS_CREDENTIALS_PATH", "./credentials/client_secret.json")
TOKEN_FILE = os.environ.get("GOOGLE_PHOTOS_TOKEN_PATH", "./credentials/token.pickle")
POLL_INTERVAL = int(os.environ.get("GOOGLE_PHOTOS_POLL_INTERVAL", 300))

# Azure Configuration
CONNECTION_STRING = os.environ.get("AZUREWEBJOBSSTORAGE")
CONTAINER_NAME = "uploads"
FUNCTION_URL = os.environ.get("AZURE_FUNCTION_URL")
FUNCTION_KEY = os.environ.get("AZURE_FUNCTION_KEY")

SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
STATE_FILE = "processed_photos.json"

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def get_gmail_service():
    """Authenticates and returns the Google Photos API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Error refreshing token: {e}")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                logging.error(f"Credentials file not found at {CREDENTIALS_FILE}")
                logging.error("Please download client_secret.json from Google Cloud Console.")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # Revert to local server with random port
            creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
                
    return build('photoslibrary', 'v1', credentials=creds, static_discovery=False)

def list_media_with_retries(service, retries=3):
    for i in range(retries):
        try:
            return service.mediaItems().list(pageSize=50).execute()
        except HttpError as e:
            if e.resp.status == 500:
                print(f"Server Error (500). Retrying in {2**i} seconds...")
                logging.warning(f"Server Error (500). Retrying in {2**i} seconds...")
                time.sleep(2**i) # Wait longer each time
            else:
                raise e
    return {} # Return empty if all retries fail

def load_processed_photos():
    """Loads the set of processed photo IDs."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get("processed_ids", []))
        except Exception:
            return set()
    return set()

def save_processed_id(photo_id):
    """Saves a processed photo ID to the state file."""
    processed = load_processed_photos()
    processed.add(photo_id)
    with open(STATE_FILE, 'w') as f:
        json.dump({"processed_ids": list(processed), "last_update": datetime.now().isoformat()}, f)

class AzureUploader:
    def __init__(self):
        if not CONNECTION_STRING:
             logging.error("AZUREWEBJOBSSTORAGE is missing/None!")
             self.blob_service_client = None
             return

        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
            self.container_client = self.blob_service_client.get_container_client(CONTAINER_NAME)
            if not self.container_client.exists():
                self.container_client.create_container()
        except Exception as e:
            logging.error(f"Failed to initialize Azure Blob Client: {e}")
            self.blob_service_client = None

    def upload_photo(self, photo_content, filename):
        if not self.blob_service_client:
            logging.error("Azure Blob Client not available.")
            return False

        try:
            # Use 'GooglePhotos' as the "Block" folder to distinguish source
            blob_name = f"GooglePhotos/{filename}"
            self.container_client.upload_blob(name=blob_name, data=photo_content, overwrite=True)
            logging.info(f"Uploaded to Azure: {blob_name}")
            
            self.trigger_function(blob_name)
            return True
        except Exception as e:
            logging.error(f"Failed to upload {filename}: {e}")
            logging.error(traceback.format_exc())
            return False

    def trigger_function(self, blob_name):
        try:
            if not CONNECTION_STRING:
                logging.error("Cannot parse account name because CONNECTION_STRING is None")
                return

            account_name = CONNECTION_STRING.split("AccountName=")[1].split(";")[0]
            blob_url = f"https://{account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
            
            payload = {"blob_url": blob_url}
            params = {"code": FUNCTION_KEY} if FUNCTION_KEY else {}
            
            logging.info(f"Triggering function for: {blob_url}")
            response = requests.post(FUNCTION_URL, json=payload, params=params, timeout=30)
            
            if response.status_code == 200:
                logging.info(f"Function triggered successfully.")
            else:
                logging.error(f"Function trigger failed: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Error triggering function: {e}")
            logging.error(traceback.format_exc())

def main():
    logging.info("Starting Google Photos Watcher...")
    
    # Debug: Check environment
    if not CONNECTION_STRING:
        logging.warning("!!! AZUREWEBJOBSSTORAGE is NOT found in environment. Check .env file. !!!")
    else:
        logging.info("AZUREWEBJOBSSTORAGE loaded successfully.")

    uploader = AzureUploader()
    processed_ids = load_processed_photos()
    
    while True:
        try:
            service = get_gmail_service()
            if not service:
                logging.error("Failed to authenticate with Google Photos.")
                time.sleep(60)
                continue
            
            # Fetch recent items
            results = list_media_with_retries(service)
            items = results.get('mediaItems', [])

            logging.info(f"API returned {len(items)} items. Checking..." )
            
            new_count = 0
            for item in items:
                photo_id = item.get('id')
                filename = item.get('filename', '')
                mime_type = item.get('mimeType', '')
                
                logging.info(f"Checking item: {filename} ({mime_type})")

                if photo_id in processed_ids:
                    logging.info(f"  -> Skipped (Already Processed)")
                    continue
                
                # Filter for images
                if not mime_type.startswith('image/'):
                    logging.info(f"  -> Skipped (Not an image)")
                    continue

                # Temporary: Upload EVERYTHING that is an image
                is_screenshot_candidate = True 

                if is_screenshot_candidate:
                    logging.info(f"  -> MATCH! Downloading {filename}...")
                    
                    base_url = item.get('baseUrl')
                    download_url = f"{base_url}=d"
                    
                    try:
                        img_data = requests.get(download_url).content
                        if uploader.upload_photo(img_data, filename):
                            save_processed_id(photo_id)
                            processed_ids.add(photo_id)
                            new_count += 1
                    except Exception as e:
                        logging.error(f"Error downloading/uploading {filename}: {e}")
                        logging.error(traceback.format_exc())
                else:
                    logging.info(f"  -> Skipped (Did not match filter)")

            if new_count == 0:
                logging.info("No new screenshots found.")
            else:
                logging.info(f"Processed {new_count} new screenshots.")

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            logging.error(traceback.format_exc())
            time.sleep(60)
        
        logging.info(f"Sleeping for {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
