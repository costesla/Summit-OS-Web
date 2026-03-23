import os, sys, requests
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(env_path)

tenant_id = os.environ.get("OAUTH_TENANT_ID")
client_id = os.environ.get("OAUTH_CLIENT_ID")
client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
business_id = os.environ.get('MS_BOOKINGS_BUSINESS_ID', 'SummitOS@costesla.com')

token = requests.post(f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token', data={
    'client_id': client_id,
    'scope': 'https://graph.microsoft.com/.default',
    'client_secret': client_secret,
    'grant_type': 'client_credentials'
}).json().get('access_token')

services = requests.get(f'https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services', headers={'Authorization': 'Bearer ' + token}).json().get('value', [])

for s in services:
    if 'Polaris' in s.get('displayName', ''):
        print(f"\nNAME: {s['displayName']}\nLINK: https://outlook.office365.com/owa/calendar/{business_id}/bookings/s/{s['id']}\n")
