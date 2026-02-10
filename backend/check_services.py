import os
import requests
import json
from services.graph import GraphClient

def list_services():
    graph = GraphClient()
    token = graph._get_token()
    business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
    url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    resp = requests.get(url, headers=headers)
    if resp.ok:
        services = resp.json().get("value", [])
        for s in services:
            print(f"ID: {s.get('id')}, DisplayName: {s.get('displayName')}")
    else:
        print(f"Error: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    list_services()
