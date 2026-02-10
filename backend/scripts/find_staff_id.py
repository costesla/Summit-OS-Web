import os
import requests
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

TENANT_ID = os.environ.get("OAUTH_TENANT_ID")
CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")
BUSINESS_ID = 'SummitOS@costesla.com' # Force this as env might be flaky

def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
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

def list_staff(token):
    url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{BUSINESS_ID}/staffMembers"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if not resp.ok:
        print(f"Staff List Error: {resp.text}")
        return None
    return resp.json().get("value", [])

if __name__ == "__main__":
    token = get_token()
    if token:
        staff = list_staff(token)
        if staff:
            print(json.dumps(staff, indent=2))
            for s in staff:
                if "Peter" in s.get("displayName", ""):
                    print(f"FOUND PETER: {s['id']}")
