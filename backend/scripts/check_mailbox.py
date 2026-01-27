import requests
import json
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'summit_sync'))
from lib.graph import GraphClient

def check_mailbox():
    client = GraphClient()
    token = client._get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Try to reach the mailbox directly
    mailbox = "SummitOS@costesla.com"
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/calendar"
    print(f"Checking Mailbox Access: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print(f"SUCCESS: Mailbox {mailbox} is REACHABLE.")
            data = resp.json()
            print(f"Calendar Name: {data.get('name')}")
        else:
            print(f"FAILED: Mailbox {mailbox} returned {resp.status_code} - {resp.text}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    check_mailbox()
