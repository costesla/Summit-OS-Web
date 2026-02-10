import os
import datetime
from azure.storage.blob import BlobServiceClient

def find_today_blobs():
    conn_str = 'DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stsummitosprod;AccountKey=TVjXd4YlIyOrR852pSgwLvcccGV8JzBm8cS5sCqNCm90iRDPBsp+0yB5vZjZ7xshr7GQvNxMfzt7+AStuXbjOQ=='
    service = BlobServiceClient.from_connection_string(conn_str)
    container_client = service.get_container_client("uploads")
    
    # Target: Feb 1st, 2026 MST
    # Current time is ~4 PM MST
    
    print(f"--- Blobs in 'uploads' for Feb 1st, 2026 (MST) ---")
    
    blobs = container_client.list_blobs()
    found = []
    
    target_date = datetime.date(2026, 2, 1)
    
    for blob in blobs:
        utc_dt = blob.last_modified
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        
        if mst_dt.date() == target_date:
            found.append((blob.name, mst_dt))
            
    found.sort(key=lambda x: x[1])
    
    for name, ts in found:
        print(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} | {name}")

if __name__ == "__main__":
    find_today_blobs()
