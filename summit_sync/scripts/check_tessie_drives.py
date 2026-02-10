import os
import json
import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

def check_tessie_drives():
    vin = os.environ.get("TESSIE_VIN")
    api_key = os.environ.get("TESSIE_API_KEY")
    
    if not vin or not api_key:
        print("Missing Tessie credentials")
        return

    # Look for drives on Jan 30th
    # Jan 30th starts at 1706598000 (UTC) approx, but let's just get the last 50 drives
    url = f"https://api.tessie.com/{vin}/drives?limit=50"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return

    drives = response.json().get("results", [])
    print(f"--- Recent Tessie Drives (Last 50) ---")
    
    for d in drives:
        # Convert UTC to MST (UTC-7)
        start_ts = d.get("active_start") or d.get("start_at")
        if not start_ts: continue
        
        utc_dt = datetime.datetime.fromtimestamp(start_ts, datetime.timezone.utc)
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        
        # We only care about Jan 30th
        if mst_dt.date() == datetime.date(2026, 1, 30):
            dist = d.get("distance_miles", 0)
            dur = (d.get("end_at", start_ts) - start_ts) / 60
            print(f"{mst_dt.strftime('%H:%M:%S')} | {dist:5.2f} mi | {dur:4.1f} min | ID: {d.get('id')}")

if __name__ == "__main__":
    check_tessie_drives()
