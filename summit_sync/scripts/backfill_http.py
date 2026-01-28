"""
Backfill script - uploads files from local onedrive folder to Azure Blob Storage
and calls HTTP Function to process them
"""
import os
import sys
import logging
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
import requests
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()
logging.basicConfig(level=logging.INFO)

def backfill():
    # Configuration
    storage_conn_str = os.environ.get("AzureWebJobsStorage")
    local_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla Camera Roll\2026-01-16"
    container_name = "function-releases"
    function_url = os.environ.get("AZURE_FUNCTION_URL", "https://summitsyncfuncus23436.azurewebsites.net/api/process-blob")
    function_key = os.environ.get("AZURE_FUNCTION_KEY")
    
    if not storage_conn_str:
        print("Error: AzureWebJobsStorage connection string not found")
        return
    
    # Upload files
    blob_service_client = BlobServiceClient.from_connection_string(storage_conn_str)
    container_client = blob_service_client.get_container_client(container_name)
    
    uploaded_urls = []
    for root, dirs, files in os.walk(local_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                local_file = os.path.join(root, file)
                
                # Preserve folder structure
                relative_path = os.path.relpath(local_file, local_path)
                blob_name = f"2026-01-16/{relative_path}".replace("\\", "/")
                
                try:
                    blob_client = container_client.get_blob_client(blob_name)
                    with open(local_file, "rb") as data:
                        blob_client.upload_blob(data, overwrite=True)
                    
                    blob_url = blob_client.url
                    uploaded_urls.append(blob_url)
                    logging.info(f"Uploaded: {blob_name}")
                    
                except Exception as e:
                    logging.error(f"Error uploading {file}: {str(e)}")
    
    # Call HTTP function for each uploaded blob
    logging.info(f"\nProcessing {len(uploaded_urls)} blobs via HTTP function...")
    success_count = 0
    error_count = 0
    
    for blob_url in uploaded_urls:
        try:
            response = requests.post(
                f"{function_url}?code={function_key}",
                json={"blob_url": blob_url},
                timeout=120
            )
            if response.status_code == 200:
                result = response.json()
                logging.info(f"✓ Processed: {result.get('trip_id', 'unknown')}")
                success_count += 1
            else:
                logging.error(f"✗ HTTP {response.status_code}: {blob_url}")
                error_count += 1
        except Exception as e:
            logging.error(f"✗ Error calling function: {str(e)}")
            error_count += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"BACKFILL COMPLETE")
    print(f"{'='*50}")
    print(f"Uploaded: {len(uploaded_urls)} blobs")
    print(f"Processed: {success_count} successful")
    print(f"Errors: {error_count}")
    print(f"{'='*50}")

if __name__ == "__main__":
    backfill()
