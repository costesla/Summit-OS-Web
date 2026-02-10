import os
import json
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

def dump_tessie():
    vin = os.environ.get("TESSIE_VIN")
    api_key = os.environ.get("TESSIE_API_KEY")
    
    # Get last 100 drives to be safe
    url = f"https://api.tessie.com/{vin}/drives?limit=100"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return

    drives = response.json().get("results", [])
    print(f"Total drives found: {len(drives)}")
    
    for d in drives:
        start_ts = d.get("active_start") or d.get("start_at")
        utc_dt = datetime.datetime.fromtimestamp(start_ts, datetime.timezone.utc)
        mst_dt = utc_dt - datetime.timedelta(hours=7)
        dist = d.get("distance_miles", 0)
        
        # Log everything from Jan 29 to Feb 1 to see the spread
        print(f"{mst_dt.strftime('%Y-%m-%d %H:%M:%S')} | {dist:6.2f} mi | ID: {d.get('id')}")

if __name__ == "__main__":
    dump_tessie()
