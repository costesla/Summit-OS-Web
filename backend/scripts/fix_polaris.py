import os
import sys
import requests
import json
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def fix_polaris_service():
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
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Get Service ID
    services_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
    services_resp = requests.get(services_url, headers=headers)
    services = services_resp.json().get("value", [])
    polaris_service = next((s for s in services if "Polaris" in s.get("displayName", "")), None)
    
    if not polaris_service:
        print("Could not find Hotel Polaris service.")
        return
        
    service_id = polaris_service["id"]
    
    # 1. Update the Scheduling Policy to fix the "No Availability" issue
    # We must provide timeSlotInterval and minimumLeadTime
    # PT30M = 30 minutes. PT0S = 0 seconds (Immediate/On-Demand)
    
    # 2. Add "Powered by Summit OS" to the description
    base_description = polaris_service.get("description", "")
    if "Powered by Summit OS" not in base_description:
        base_description += "\n\n🚀 *Powered by Summit OS*"

    update_payload = {
        "description": base_description,
        "schedulingPolicy": {
            "timeSlotInterval": "PT30M",
            "minimumLeadTime": "PT0S",
            "maximumAdvance": "P90D",
            "allowStaffSelection": False
        }
    }
    
    update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services/{service_id}"
    print("Sending PATCH request to fix availability and add branding...")
    patch_resp = requests.patch(update_url, headers=headers, json=update_payload)
    
    if patch_resp.ok:
        print("SUCCESS! Availability intervals and branding applied.")
    else:
        print(f"FAILED: {patch_resp.text}")

if __name__ == "__main__":
    fix_polaris_service()
