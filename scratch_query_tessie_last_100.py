import os
import sys
import json
import requests
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
    params = {
        "limit": 100
    }
    
    print("Fetching last 100 drives from Tessie API...")
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    print("Tessie API Status:", resp.status_code)
    try:
        data = resp.json()
        results = data.get("results", [])
        print(f"Retrieved {len(results)} drives.")
        found = False
        for d in results:
            if str(d.get("id")) == "397010117" or d.get("id") == 397010117:
                print("FOUND target drive in last 100 drives:")
                print(json.dumps(d, indent=2))
                found = True
        if not found:
            print("Target drive NOT found in the last 100 drives on Tessie account.")
    except Exception as e:
        print("Error:", e)
        print("Raw response:", resp.text)

if __name__ == "__main__":
    main()
