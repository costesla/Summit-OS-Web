import os
import requests
import json
import sys
from dotenv import load_dotenv

script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '.env'))
sys.path.append(os.path.join(script_dir, '..'))
from lib.graph import GraphClient

def list_all_businesses():
    try:
        graph = GraphClient()
        token = graph._get_token()
        
        # Trial 1: List all businesses
        print("Trial 1: GET /solutions/bookingBusinesses")
        url = "https://graph.microsoft.com/v1.0/solutions/bookingBusinesses"
        headers = {"Authorization": f"Bearer {token}"}
        
        res = requests.get(url, headers=headers)
        if res.ok:
            data = res.json()
            businesses = data.get("value", [])
            print(f"SUCCESS: Found {len(businesses)} businesses.")
            for b in businesses:
                print(f"- {b.get('displayName')} | ID: {b.get('id')}")
        else:
            print(f"FAIL Trial 1: {res.status_code} - {res.text}")

        # Trial 2: Specifically check PrivateTrips email
        email = "PrivateTrips@costesla.com"
        print(f"\nTrial 2: GET /solutions/bookingBusinesses/{email}")
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{email}"
        res = requests.get(url, headers=headers)
        if res.ok:
            print(f"SUCCESS Trial 2: Found business. ID: {res.json().get('id')}")
        else:
            print(f"FAIL Trial 2: {res.status_code} - {res.text}")

    except Exception as e:
        print(f"CRITICAL: {str(e)}")

if __name__ == "__main__":
    list_all_businesses()
