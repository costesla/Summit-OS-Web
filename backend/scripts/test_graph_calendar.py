import os
import requests
import json
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

TENANT_ID = os.environ.get("OAUTH_TENANT_ID")
CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")
BUSINESS_ID = 'SummitOS@costesla.com'
STAFF_ID = 'b9c4204d-bd20-43cc-aa50-2add4602d316'
BUSINESS_TIMEZONE = "America/Denver"

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

def test_calendar_view(token):
    tz = pytz.timezone(BUSINESS_TIMEZONE)
    now = datetime.now(tz)
    start_dt = now - timedelta(days=1)
    end_dt = now + timedelta(days=5)

    # Convert to UTC and format with Z
    start_utc = start_dt.astimezone(pytz.UTC)
    end_utc = end_dt.astimezone(pytz.UTC)
    
    start_iso = start_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_iso = end_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f"Testing with: {start_iso} to {end_iso}")

    url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{BUSINESS_ID}/staffMembers/{STAFF_ID}/calendarView"
    params = {
        "startDateTime": start_iso,
        "endDateTime": end_iso
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params)
    print(f"CALENDAR STATUS: {resp.status_code}")
    if not resp.ok:
        print(f"Calendar Error: {resp.text}")
    else:
        print("Success! Found events:", len(resp.json().get('value', [])))

if __name__ == "__main__":
    token = get_token()
    if token:
        test_calendar_view(token)
