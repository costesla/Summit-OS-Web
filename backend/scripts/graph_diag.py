import os
import requests
import json
import sys
from dotenv import load_dotenv

script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '.env'))
sys.path.append(os.path.join(script_dir, '..'))
from lib.graph import GraphClient

def diagnostic():
    try:
        graph = GraphClient()
        token = graph._get_token()
        print("PASS: Successfully acquired access token.")
        
        # Try a simple "GET /me" or similar
        # Since we use client_credentials, we can't use /me. 
        # We must use /users
        
        url = "https://graph.microsoft.com/v1.0/users/peter.teehan@costesla.com"
        headers = {"Authorization": f"Bearer {token}"}
        
        res = requests.get(url, headers=headers)
        if res.ok:
            print(f"PASS: Can query user. DisplayName: {res.json().get('displayName')}")
        else:
            print(f"FAIL: User query failed. {res.status_code} - {res.text}")

        # Try to list bookingBusinesses
        url = "https://graph.microsoft.com/v1.0/solutions/bookingBusinesses"
        res = requests.get(url, headers=headers)
        if res.ok:
            print("PASS: Can list booking businesses.")
            businesses = res.json().get("value", [])
            for b in businesses:
                print(f"- {b.get('displayName')} ({b.get('id')})")
        else:
            print(f"FAIL: Cannot list booking businesses. {res.status_code} - {res.text}")

    except Exception as e:
        print(f"CRITICAL: {str(e)}")

if __name__ == "__main__":
    diagnostic()
