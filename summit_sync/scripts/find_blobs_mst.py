import os
import datetime
from azure.storage.blob import BlobServiceClient

def find_blobs_mst():
    conn_str = 'DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stsummitosprod;AccountKey=TVjXd4YlIyOrR852pSgwLvcccGV8JzBm8cS5sCqNCm90iRDPBsp+0yB5vZjZ7xshr7GQvNxMfzt7+AStuXbjOQ=='
    service = BlobServiceClient.from_connection_string(conn_str)
    container_client = service.get_container_client("uploads")
    
    # MST is UTC-7
    
    print(f"--- Blobs in 'uploads' filtered for Jan 30/31 (MST) ---")
    
    blobs = container_client.list_blobs()
    found = []
    
    target_dates = [datetime.date(2026, 1, 30), datetime.date(2026, 1, 31)]
    
    for blob in blobs:
        # blob.last_modified is UTC datetime with tzinfo
        utc_dt = blob.last_modified
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        
        if mst_dt.date() in target_dates:
            found.append((blob.name, mst_dt))
            
    # Sort by MST time
    found.sort(key=lambda x: x[1])
    
    for name, ts in found:
        print(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} | {name}")

if __name__ == "__main__":
    find_blobs_mst()
