import os
import datetime
from azure.storage.blob import BlobServiceClient

def search_blobs_feb1():
    conn_str = 'DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stsummitosprod;AccountKey=TVjXd4YlIyOrR852pSgwLvcccGV8JzBm8cS5sCqNCm90iRDPBsp+0yB5vZjZ7xshr7GQvNxMfzt7+AStuXbjOQ=='
    service = BlobServiceClient.from_connection_string(conn_str)
    container_client = service.get_container_client("uploads")
    
    print(f"--- All Blobs in 'uploads' modified on Feb 1st, 2026 (MST) ---")
    
    blobs = container_client.list_blobs()
    found = []
    
    target_date = datetime.date(2026, 2, 1)
    
    for blob in blobs:
        utc_dt = blob.last_modified
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        
        if mst_dt.date() == target_date:
            found.append((blob.name, mst_dt))
            
    found.sort(key=lambda x: x[1])
    
    if not found:
        print("No blobs found for today in 'uploads'.")
    else:
        for name, ts in found:
            print(f"{ts.strftime('%H:%M:%S')} | {name}")

if __name__ == "__main__":
    search_blobs_feb1()
