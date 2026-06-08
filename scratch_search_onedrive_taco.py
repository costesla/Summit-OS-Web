import os
import sys
import json

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

print("=== SEARCHING ONEDRIVE FOR RECENT IMAGES / TACO BELLS ===")
# Search Graph API for files containing 'Taco' or 'Scan' in name
token = graph._get_token()
import requests
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Taco')"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    print(f"Found {len(search_results)} search results for 'Taco':")
    for r in search_results:
        print(f"  Name: {r.get('name')} | Path: {r.get('parentReference', {}).get('path')} | Size: {r.get('size')} bytes")
else:
    print(f"Search failed: {resp.text}")

print("\n=== SEARCHING FOR FILES CONTAINING 'Scan' ===")
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Scan')"
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    print(f"Found {len(search_results)} search results for 'Scan' in May 2026:")
    for r in search_results:
        # Check if parent is in May 2026 or folder name matches
        path = r.get('parentReference', {}).get('path', '')
        if 'May' in path or '5.26.26' in path or '5.25.26' in path:
            print(f"  Name: {r.get('name')} | Path: {path} | Size: {r.get('size')} bytes")
else:
    print(f"Search failed: {resp.text}")
