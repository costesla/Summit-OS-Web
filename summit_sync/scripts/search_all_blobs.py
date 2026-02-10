import os
import datetime
from azure.storage.blob import BlobServiceClient

def search_all_containers():
    conn_str = 'DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=stsummitosprod;AccountKey=TVjXd4YlIyOrR852pSgwLvcccGV8JzBm8cS5sCqNCm90iRDPBsp+0yB5vZjZ7xshr7GQvNxMfzt7+AStuXbjOQ=='
    service = BlobServiceClient.from_connection_string(conn_str)
    
    containers = service.list_containers()
    for container_info in containers:
        cname = container_info.name
        print(f"--- Searching in container: {cname} ---")
        container_client = service.get_container_client(cname)
        blobs = container_client.list_blobs()
        for b in blobs:
            if '20260130' in b.name or '20260131' in b.name:
                mst = b.last_modified - datetime.timedelta(hours=7)
                print(f"{mst.strftime('%Y-%m-%d %H:%M:%S')} | {b.name}")

if __name__ == "__main__":
    search_all_containers()
