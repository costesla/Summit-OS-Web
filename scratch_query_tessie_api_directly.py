import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))

def main():
    api_key = os.environ.get("TESSIE_API_KEY")
    vin = os.environ.get("TESSIE_VIN")
    
    if not api_key:
        print("Error: TESSIE_API_KEY not found in environment.")
        return
        
    url = f"https://api.tessie.com/{vin}/drives"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # Broaden range: 2026-05-24 00:00:00 MDT to 2026-05-25 00:00:00 MDT
    # MDT is UTC-6, so 06:00 UTC to 06:00 UTC
    mdt = timezone(timedelta(hours=-6))
    dt_start = datetime.strptime("2026-05-24", '%Y-%m-%d').replace(tzinfo=mdt)
    dt_end = dt_start + timedelta(days=1)
    
    params = {
        "from": int(dt_start.timestamp()),
        "to": int(dt_end.timestamp()),
        "limit": 100
    }
    
    print(f"Fetching drives from Tessie API between {dt_start} and {dt_end}...")
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    print("Tessie API Status:", resp.status_code)
    try:
        data = resp.json()
        results = data.get("results", [])
        print(f"Found {len(results)} drives in that range.")
        for d in results:
            print(f"DriveID: {d.get('id')} | Tag: {d.get('tag')} | Start: {datetime.fromtimestamp(d.get('started_at'))}")
    except Exception as e:
        print("Error:", e)
        print("Raw response:", resp.text)

if __name__ == "__main__":
    main()
