import os
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

TENANT_ID = os.environ.get("OAUTH_TENANT_ID")
CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")
BUSINESS_ID = 'SummitOS@costesla.com'
STAFF_ID = 'b9c4204d-bd20-43cc-aa50-2add4602d316'

def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, data=data)
    return resp.json().get("access_token")

def test_raw_calendar(token):
    # Try with very simple dates
    start = "2026-02-09T00:00:00Z"
    end = "2026-02-15T00:00:00Z"
    
    url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{BUSINESS_ID}/staffMembers/{STAFF_ID}/calendarView"
    params = {
        "startDateTime": start,
        "endDateTime": end
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params)
    print(f"STATUS: {resp.status_code}")
    print(f"RESPONSE: {resp.text}")

if __name__ == "__main__":
    token = get_token()
    if token:
        test_raw_calendar(token)
