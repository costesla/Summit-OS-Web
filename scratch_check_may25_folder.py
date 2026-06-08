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
folder_path = "Uber Driver/2026/May/Week 5/5.25.26"
try:
    files = graph.list_folder_files(folder_path)
    print(f"=== ONEDRIVE FILES IN 5.25.26 ===")
    for f in files:
        print(f"  Name: {f.get('name')} | ID: {f.get('id')} | Size: {f.get('size')} bytes")
except Exception as e:
    print(f"Error: {e}")
