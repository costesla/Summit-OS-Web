import requests
import json
import sys
import os

# Set up path to import lib.graph
sys.path.append(os.path.join(os.getcwd(), 'summit_sync'))
from lib.graph import GraphClient

def check_health():
    client = GraphClient()
    token = client._get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 1. Check a simple endpoint (users)
    url = "https://graph.microsoft.com/v1.0/users?$top=1"
    print(f"Querying Graph Health (Users): {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("✅ Graph Token is HEALTHY and has basic access.")
        else:
            print(f"❌ Graph Health Check FAILED: {resp.status_code} - {resp.text}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    check_health()
