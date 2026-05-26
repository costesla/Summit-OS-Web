import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))

def main():
    api_key = os.environ.get("TESSIE_API_KEY")
    
    if not api_key:
        print("Error: TESSIE_API_KEY not found in environment.")
        return
        
    url = "https://api.tessie.com/vehicles"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    print("Fetching all vehicles from Tessie API...")
    resp = requests.get(url, headers=headers, timeout=10)
    print("Tessie API Status:", resp.status_code)
    try:
        data = resp.json()
        print("Tessie Vehicles Response:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print("Error:", e)
        print("Raw response:", resp.text)

if __name__ == "__main__":
    main()
