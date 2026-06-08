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

print("=== RAW SEARCH FOR TACO (FIRST 10) ===")
url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root/search(q='Taco')"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers)
if resp.ok:
    search_results = resp.json().get("value", [])
    print(f"Total results: {len(search_results)}")
    for r in search_results[:10]:
        print(f"Name: {r.get('name')} | ParentRef: {r.get('parentReference')}")
else:
    print(f"Search failed: {resp.text}")
