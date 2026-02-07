import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend')) # Point to backend root
from services.graph import GraphClient
import requests
import json
import logging

def probe_bookings():
    client = GraphClient()
    token = client._get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 1. List Booking Businesses (Re-attempting list after propagation)
    url = "https://graph.microsoft.com/v1.0/solutions/bookingBusinesses"
    print(f"Querying Bookings: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            businesses = resp.json().get("value", [])
            print(f"Found {len(businesses)} Booking businesses.")
            for b in businesses:
                bid = b.get('id')
                print(f"- ID: {bid}, DisplayName: {b.get('displayName')}")
                
                # 2. List Services for each business
                services_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{bid}/services"
                s_resp = requests.get(services_url, headers=headers)
                if s_resp.status_code == 200:
                    services = s_resp.json().get("value", [])
                    print(f"  Services ({len(services)}):")
                    for s in services:
                        print(f"    * {s.get('displayName')} (ID: {s.get('id')})")
                else:
                    print(f"  Failed to get services for {bid}: {s_resp.status_code} - {s_resp.text}")
        else:
            print(f"Failed to query businesses: {resp.status_code} - {resp.text}")
            
        # 3. Direct attempt as fallback
        fallback_id = "SummitOS@costesla.com"
        print(f"\nDirect Fallback Query for: {fallback_id}")
        f_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{fallback_id}"
        f_resp = requests.get(f_url, headers=headers)
        if f_resp.status_code == 200:
            print(f"✅ Direct lookup SUCCESS for {fallback_id}")
            # ... list services here too ...
        else:
            print(f"❌ Direct lookup FAILED for {fallback_id}: {f_resp.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_bookings()
