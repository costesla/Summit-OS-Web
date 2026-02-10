import os
import datetime
from azure.storage.blob import BlobServiceClient

def find_specific_window():
    conn_str = 'DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stsummitosprod;AccountKey=TVjXd4YlIyOrR852pSgwLvcccGV8JzBm8cS5sCqNCm90iRDPBsp+0yB5vZjZ7xshr7GQvNxMfzt7+AStuXbjOQ=='
    service = BlobServiceClient.from_connection_string(conn_str)
    container_client = service.get_container_client("uploads")
    
    # 11:58 AM MST (UTC-7) is 18:58 UTC
    # User said 11:58 AM trip on Jan 30
    
    print(f"--- Blobs modified around 11:58 AM MST (18:58 UTC) on Jan 30 ---")
    
    blobs = container_client.list_blobs()
    found = []
    
    for blob in blobs:
        utc_dt = blob.last_modified
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        
        # Check Jan 30th between 11:45 AM and 12:15 PM MST
        if mst_dt.date() == datetime.date(2026, 1, 30):
            if 11 <= mst_dt.hour <= 12:
                found.append((blob.name, mst_dt))
            
    # Sort by MST time
    found.sort(key=lambda x: x[1])
    
    for name, ts in found:
        print(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} | {name}")

if __name__ == "__main__":
    find_specific_window()
