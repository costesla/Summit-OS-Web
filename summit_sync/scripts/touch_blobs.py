
import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()
conn_str = os.environ.get("AZUREWEBJOBSSTORAGE")

def touch_blobs():
    if not conn_str:
        print("AZUREWEBJOBSSTORAGE not found.")
        return

    service = BlobServiceClient.from_connection_string(conn_str)
    container_client = service.get_container_client("function-releases")
    
    print("Touching blobs in 'function-releases' to trigger Logic App...")
    blobs = container_client.list_blobs()
    count = 0
    for blob in blobs:
        if blob.name.endswith(".jpg") or blob.name.endswith(".png"):
            # Update metadata to trigger the 'modified' event
            blob_client = container_client.get_blob_client(blob.name)
            metadata = blob.metadata or {}
            metadata['last_touched'] = str(os.urandom(4).hex()) 
            blob_client.set_blob_metadata(metadata)
            print(f"Touched: {blob.name}")
            count += 1
    
    print(f"Total blobs touched: {count}")

if __name__ == "__main__":
    touch_blobs()
