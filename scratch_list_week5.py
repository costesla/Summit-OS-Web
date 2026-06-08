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
base_path = "Uber Driver/2026/May/Week 5"

try:
    # Let's list the children of Week 5
    token = graph._get_token()
    import requests
    url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root:/Uber Driver/2026/May/Week 5:/children"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.ok:
        items = resp.json().get("value", [])
        for item in items:
            name = item.get("name")
            is_folder = "folder" in item
            print(f"Name: {name} | Folder: {is_folder} | ID: {item.get('id')}")
            if is_folder:
                # list children of this folder
                folder_url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/items/{item.get('id')}/children"
                f_resp = requests.get(folder_url, headers=headers)
                if f_resp.ok:
                    f_items = f_resp.json().get("value", [])
                    for fi in f_items:
                        print(f"  -> File: {fi.get('name')} | Size: {fi.get('size')} bytes")
    else:
        print(f"Failed to list Week 5: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
