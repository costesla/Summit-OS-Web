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

print("=== SEARCHING ONEDRIVE FOR TACO ===")
token = graph._get_token()
# We do a search specifically for 'Taco'
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Taco')"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    print(f"Found {len(search_results)} search results for 'Taco':")
    for r in search_results:
        # Check if parent is in May 2026 or has 'Week 5'
        path = r.get('parentReference', {}).get('path', '')
        print(f"  Name: {r.get('name')} | Path: {path} | Size: {r.get('size')} bytes")
else:
    print(f"Search failed: {resp.text}")

print("\n=== SEARCHING FOR FILES CONTAINING 'Scan' IN MAY 2026 ===")
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Scan')"
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    filtered = [r for r in search_results if 'May' in r.get('parentReference', {}).get('path', '')]
    print(f"Found {len(filtered)} search results for 'Scan' in May 2026 folder:")
    for r in filtered:
        print(f"  Name: {r.get('name')} | Path: {r.get('parentReference', {}).get('path')} | Size: {r.get('size')} bytes")
else:
    print(f"Search failed: {resp.text}")
