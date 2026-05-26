import os
import sys
import json
import requests
from datetime import datetime
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
    
    # EXACT TIMESTAMPS FROM COPILOT.PY FOR 2026-05-24
    from_ts = 1779650400
    to_ts = 1779736800
    
    params = {
        "from": from_ts,
        "to": to_ts,
        "limit": 200
    }
    
    print(f"Fetching drives from Tessie API (from={from_ts}, to={to_ts})...")
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    print("Tessie API Status:", resp.status_code)
    try:
        data = resp.json()
        results = data.get("results", [])
        print(f"Found {len(results)} drives in that range.")
        for d in results:
            if d.get("id") == 397010117 or d.get("id") == "397010117":
                print("RAW DRIVE OBJECT:")
                print(json.dumps(d, indent=2))
    except Exception as e:
        print("Error:", e)
        print("Raw response:", resp.text)

if __name__ == "__main__":
    main()
