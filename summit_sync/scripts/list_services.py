import os
import requests
import json
from lib.bookings import BookingsClient

def list_booking_services():
    client = BookingsClient()
    try:
        token = client._get_access_token()
        business_id = client.business_id
        
        print(f"🔍 Fetching services for business: {business_id}...")
        
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        res = requests.get(url, headers=headers)
        if not res.ok:
            print(f"❌ Error: {res.status_code} - {res.text}")
            return

        services = res.json().get("value", [])
        if not services:
            print("⚠️ No services found for this business.")
            return

        print("\n✅ Found Services:")
        print("-" * 50)
        for s in services:
            print(f"Name: {s.get('displayName')}")
            print(f"ID:   {s.get('id')}")
            print(f"Description: {s.get('description', 'N/A')}")
            print("-" * 50)

    except Exception as e:
        print(f"❌ Critical Failure: {str(e)}")

if __name__ == "__main__":
    list_booking_services()
