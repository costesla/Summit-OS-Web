import requests
import os

tenant_id = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
client_id = "a7d212ac-dd2b-4910-a62a-b623a8ac250c"
client_secret = "Plm8Q~3LDUO4WYabCjPsiBLud-vNQB3EszJGQad1"

username = "PrivateTrips@costesla.com"
password = "AmeliaCOS-112430!"

url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

data = {
    "client_id": client_id,
    "scope": "Bookings.ReadWrite.All",
    "username": username,
    "password": password,
    "grant_type": "password",
    "client_secret": client_secret
}

print(f"Attempting login for {username}...")
resp = requests.post(url, data=data)

if resp.ok:
    print("SUCCESS: Token Access Granted!")
    print(f"Token Type: {resp.json().get('token_type')}")
else:
    print(f"FAILED: {resp.status_code}")
    print(resp.text)
