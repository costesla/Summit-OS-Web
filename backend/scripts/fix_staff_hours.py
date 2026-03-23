import os
import requests
import json
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def set_peter_hours_smart():
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

    # Set Peter
    st_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
    staffs = requests.get(st_url, headers=headers).json().get("value", [])
    peter = next((s for s in staffs if "peter" in s.get("emailAddress", "").lower()), None)
    
    if peter:
        staff_id = peter["id"]
        working_hours = peter.get("workingHours", [])
        
        # Find Friday and fix it!
        for wh in working_hours:
            if wh.get("day") == "friday":
                # Look at timeslots
                for ts in wh.get("timeSlots", []):
                     if ts.get("endTime") == "00:00:00.0000000":
                          print("Found the corrupted Friday ending time! Setting back to 23:30...")
                          ts["endTime"] = "23:30:00.0000000"
                          
        # Verify the array to be safe: any endTime of 00:00:00.0000000 needs to be fixed.
        for wh in working_hours:
             for ts in wh.get("timeSlots", []):
                  if ts.get("endTime") == "00:00:00.0000000":
                       ts["endTime"] = "23:30:00.0000000"

        staff_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers/{staff_id}"
        staff_payload = {
            "workingHours": working_hours,
            "useBusinessHours": False
        }
        
        print(f"Submitting PATCH Payload for Peter:\n{json.dumps(staff_payload, indent=2)}")
        
        staff_resp = requests.patch(staff_update_url, headers=headers, json=staff_payload)
        if staff_resp.ok:
            print("SUCCESS! Staff hours restored to working state.")
        else:
            print(f"FAILED Staff patch: {staff_resp.text}")
    else:
        print("Peter not found.")

if __name__ == "__main__":
    set_peter_hours_smart()
