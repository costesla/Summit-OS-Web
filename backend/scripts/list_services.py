import os
import requests
import json
import sys
from dotenv import load_dotenv

# Ensure we can import from lib
script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '.env'))

sys.path.append(os.path.join(script_dir, '..'))
from lib.bookings import BookingsClient

def list_booking_services():
    client = BookingsClient()
    try:
        # Load from .env if not already in environment
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
        
        # Use business_id from env if set, else fallback to class default
        business_id = os.environ.get("BOOKINGS_BUSINESS_ID", client.business_id)
        
        token = client._get_access_token()
        
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
            print("⚠️ No services found for this business. Check if the ID is correct.")
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
