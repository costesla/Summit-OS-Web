import os
import sys
import requests
import json
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def diag():
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
    token = requests.post(token_url, data=token_data).json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Get Services
    s_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
    services = requests.get(s_url, headers=headers).json().get("value", [])
    polaris = next((s for s in services if "Polaris" in s.get("displayName", "")), None)
    
    if not polaris:
        print("COULD NOT FIND POLARIS SERVICE")
        return
        
    print("--- POLARIS SERVICE CONFIG ---")
    print(f"Staff Assigned: {polaris.get('staffMemberIds')}")
    print(f"Scheduling Policy: {json.dumps(polaris.get('schedulingPolicy'), indent=2)}")
    
    # Check Business Hours
    b_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}"
    biz = requests.get(b_url, headers=headers).json()
    print("\n--- BUSINESS HOURS ---")
    print(json.dumps(biz.get("businessHours"), indent=2))
    
    # Check Staff
    st_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
    staffs = requests.get(st_url, headers=headers).json().get("value", [])
    print("\n--- ALL STAFF ---")
    for st in staffs:
        print(f"Name: {st.get('displayName')} | ID: {st.get('id')} | Email: {st.get('emailAddress')}")
        if polaris.get('staffMemberIds') and st.get('id') in polaris.get('staffMemberIds'):
            print("  -> ASSIGNED TO POLARIS")
            print("  -> WORKING HOURS:", json.dumps(st.get("workingHours")))

if __name__ == "__main__":
    diag()
