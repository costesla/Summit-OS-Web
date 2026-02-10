import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

def list_blobs():
    connection_string = os.environ.get("AZUREWEBJOBSSTORAGE")
    if not connection_string:
        print("AZUREWEBJOBSSTORAGE not found.")
        return

    container_name = "uploads"
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        
        print(f"Blobs in container '{container_name}':")
        blobs = container_client.list_blobs()
        found = False
        for blob in blobs:
            if "Venmo" in blob.name:
                print(f"- {blob.name}")
                found = True
        
        if not found:
            print("No Venmo screenshots found in Azure.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_blobs()
