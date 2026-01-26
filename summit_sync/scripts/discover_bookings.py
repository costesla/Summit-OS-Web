import os
import requests
import json
import sys
from dotenv import load_dotenv

# Ensure we can import from lib
script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '.env'))

sys.path.append(os.path.join(script_dir, '..'))
from lib.graph import GraphClient

def discover_services():
    try:
        graph = GraphClient()
        token = graph._get_token()
        
        # User confirmed business ID
        business_id = os.environ.get("BOOKINGS_BUSINESS_ID", "PrivateTrips@costesla.com")
        
        print(f"DEBUG: Querying Graph for Bookings Services inside: {business_id}...")
        
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        res = requests.get(url, headers=headers)
        if not res.ok:
            print(f"Error: {res.status_code}")
            print(res.text)
            return

        data = res.json()
        services = data.get("value", [])
        
        if not services:
            print("No services found.")
            return

        print("ACTIVE SERVICES:")
        for s in services:
            print(f"- Name: {s.get('displayName')}")
            print(f"  ID:   {s.get('id')}")
            print(f"  Duration: {s.get('defaultDuration')}")
            print("-" * 20)

    except Exception as e:
        print(f"Failure: {str(e)}")

if __name__ == "__main__":
    discover_services()
