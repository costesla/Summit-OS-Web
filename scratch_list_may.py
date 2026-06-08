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

def list_all_recursive(folder_path):
    print(f"\n--- Listing: {folder_path} ---")
    try:
        token = graph._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{graph.user_email}/drive/root:/{folder_path}:/children"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers)
        if resp.ok:
            items = resp.json().get("value", [])
            for item in items:
                name = item.get("name")
                is_folder = "folder" in item
                item_path = f"{folder_path}/{name}"
                print(f"Name: {name} | IsFolder: {is_folder} | Size: {item.get('size')} bytes")
                if is_folder:
                    list_all_recursive(item_path)
        else:
            print(f"Failed to list {folder_path}: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

list_all_recursive("Uber Driver/2026/May")
