import os
import sys
import requests
import json
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def diag_availability():
    tenant_id = os.environ.get("OAUTH_TENANT_ID")
    client_id = os.environ.get("OAUTH_CLIENT_ID")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")

    # Get Token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    resp = requests.post(token_url, data=token_data)
    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("=== MS GRAPH AVAILABILITY DIAGNOSTICS ===")

    # 1. Fetch Polaris Service
    s_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
    services = requests.get(s_url, headers=headers).json().get("value", [])
    polaris = next((s for s in services if "Polaris" in s.get("displayName", "")), None)
    
    if not polaris:
        print("Service not found.")
        return
        
    print("\n[SERVICE CONFIG]")
    print(f"Service ID: {polaris['id']}")
    print(json.dumps(polaris.get("schedulingPolicy"), indent=2))
    
    # 2. Fetch Staff
    st_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
    staffs = requests.get(st_url, headers=headers).json().get("value", [])
    peter = next((s for s in staffs if "peter" in s.get("emailAddress", "").lower()), None)
    
    if peter:
        print("\n[STAFF CONFIG: Peter]")
        print(f"Use Business Hours: {peter.get('useBusinessHours')}")
        print("Working Hours:", json.dumps(peter.get("workingHours")))
    else:
        print("Peter not found.")

    # 3. Check Peter's Calendar Events for Feb 20th
    if peter:
        # Use simple calendar/calendarView endpoint for the specific user
        user_email = peter.get("emailAddress")
        print(f"\n[CALENDAR EVENTS ON FEB 20: {user_email}]")
        
        # We look at Feb 20th mountain time (UTC -7)
        # 2026-02-20T00:00:00-07:00 to 2026-02-20T23:59:59-07:00
        # which is 2026-02-20T07:00:00Z to 2026-02-21T06:59:59Z
        
        start_iso = "2026-02-20T00:00:00Z"
        end_iso   = "2026-02-21T00:00:00Z" # Broaden the search
        
        cal_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/calendarView?startDateTime={start_iso}&endDateTime={end_iso}"
        cal_resp = requests.get(cal_url, headers=headers)
        if cal_resp.ok:
            events = cal_resp.json().get("value", [])
            print(f"Total events found: {len(events)}")
            for e in events:
                print(f" - {e.get('subject')} | {e.get('showAs')} | AllDay: {e.get('isAllDay')} | Start: {e.get('start', {}).get('dateTime')} -> End: {e.get('end', {}).get('dateTime')}")
        else:
            print(f"Failed to fetch calendar: {cal_resp.text}")

        # 4. Use Bookings Availability API to get EXACT available slots
        # POST /solutions/bookingBusinesses/{id}/getStaffAvailability
        print("\n[BOOKINGS ENGINE AVAILABILITY TEST]")
        av_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/getStaffAvailability"
        av_payload = {
            "staffIds": [peter['id']],
            "startDateTime": {
                "dateTime": "2026-02-20T00:00:00.0000000",
                "timeZone": "America/Denver"
            },
            "endDateTime": {
                "dateTime": "2026-02-20T23:59:00.0000000",
                "timeZone": "America/Denver"
            }
        }
        av_resp = requests.post(av_url, headers=headers, json=av_payload)
        if av_resp.ok:
            av_data = av_resp.json().get("value", [])
            for staff_av in av_data:
                 print(f"Availability Items for Staff:")
                 for slot in staff_av.get("availabilityItems", []):
                     print(f"  Status: {slot.get('status')} | {slot.get('startDateTime', {}).get('dateTime')} -> {slot.get('endDateTime', {}).get('dateTime')}")
        else:
            print(f"Failed to get availability: {av_resp.text}")

if __name__ == "__main__":
    diag_availability()
