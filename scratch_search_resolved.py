import os
import sys
import json
import requests

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from services.graph import GraphClient

graph = GraphClient()
token = graph._get_token()

print("=== RESOLVED SEARCH FOR TACO IN ONEDRIVE ===")
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Taco')"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    for r in search_results:
        name = r.get("name", "")
        # We fetch the item path
        item_id = r.get("id")
        # Get item details to get the parent path
        item_url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/items/{item_id}"
        i_resp = requests.get(item_url, headers=headers)
        if i_resp.ok:
            details = i_resp.json()
            path = details.get("parentReference", {}).get("path", "")
            # check if it's under 'Uber Driver/2026/May'
            if 'May' in path or 'Week 5' in path:
                print(f"Name: {name} | Path: {path} | Size: {r.get('size')} bytes")
        else:
            print(f"Failed to get details for {name}")
else:
    print(f"Search failed: {resp.text}")
