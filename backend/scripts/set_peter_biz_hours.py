import os
import requests
import json
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def set_peter_biz_hours():
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

    # 1. Update Business Hours to a safe 00:00 to 23:59 block
    hop_safe = []
    days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    for day in days:
        hop_safe.append({
            "day": day,
            "timeSlots": [
                {
                    "startTime": "00:00:00.0000000",
                    "endTime": "23:59:00.0000000" 
                }
            ]
        })

    biz_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}"
    biz_resp = requests.patch(biz_update_url, headers=headers, json={"businessHours": hop_safe})
    if biz_resp.ok:
        print("Set Business Hours to 24/7 successfully.")
    else:
        print(f"Failed to set Business Hours: {biz_resp.text}")

    # Set Peter to use those Business Hours
    st_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
    staffs = requests.get(st_url, headers=headers).json().get("value", [])
    peter = next((s for s in staffs if "peter" in s.get("emailAddress", "").lower()), None)
    
    if peter:
        staff_id = peter["id"]
        staff_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers/{staff_id}"
        
        # We omit workingHours and just set useBusinessHours to True
        staff_payload = {
            "useBusinessHours": True
        }
        
        print(f"Patching Peter to inherit Business Hours...")
        staff_resp = requests.patch(staff_update_url, headers=headers, json=staff_payload)
        if staff_resp.ok:
            print("SUCCESS! Peter now uses inherit Business Hours.")
        else:
            print(f"FAILED Staff patch: {staff_resp.text}")
    else:
        print("Peter not found.")

if __name__ == "__main__":
    set_peter_biz_hours()
