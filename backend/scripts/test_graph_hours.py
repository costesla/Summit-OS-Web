import os
import requests
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

TENANT_ID = os.environ.get("OAUTH_TENANT_ID")
CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")
BUSINESS_ID = 'SummitOS@costesla.com'

def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    # Note: Use scope=https://graph.microsoft.com/.default for client_credentials
    data = {
        "client_id": CLIENT_ID,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, data=data)
    if not resp.ok:
        print(f"Token Error: {resp.text}")
        return None
    return resp.json().get("access_token")

def get_business_hours(token):
    # Testing both Lösungen solutions and users/me/calendar
    url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{BUSINESS_ID}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    print(f"BUSINESS STATUS: {resp.status_code}")
    if not resp.ok:
        print(f"Business Error: {resp.text}")
        return None
    return resp.json().get("businessHours", [])

if __name__ == "__main__":
    token = get_token()
    if token:
        hours = get_business_hours(token)
        print(json.dumps(hours, indent=2))
