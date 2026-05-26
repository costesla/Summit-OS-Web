import os
import sys
import json
import requests
from datetime import datetime, timezone
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
    
    # Range: May 23 00:00:00 UTC to May 26 00:00:00 UTC
    params = {
        "from": 1779494400,
        "to": 1779753600,
        "limit": 250
    }
    
    print("Fetching drives from Tessie API (broad window)...")
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    print("Tessie API Status:", resp.status_code)
    try:
        data = resp.json()
        results = data.get("results", [])
        print(f"Found {len(results)} drives in that range.")
        found = False
        for d in results:
            if str(d.get("id")) == "397010117" or d.get("id") == 397010117:
                print("FOUND target drive:")
                print(json.dumps(d, indent=2))
                found = True
        if not found:
            print("Target drive 397010117 NOT found in broad range.")
    except Exception as e:
        print("Error:", e)
        print("Raw response:", resp.text)

if __name__ == "__main__":
    main()
