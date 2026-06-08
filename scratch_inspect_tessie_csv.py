import os
import sys
import json
import requests
import io

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
import csv

graph = GraphClient()

folder_path = "Uber Driver/2026/May/Week 5/5.26.26"
files = graph.list_folder_files(folder_path)

csv_file = next((f for f in files if f.get("name").endswith(".csv") and "Tessie" in f.get("name")), None)
if not csv_file:
    print("No Tessie CSV found in 5.26.26!")
else:
    print(f"Found CSV: {csv_file.get('name')}")
    content = graph.get_file_content(csv_file.get("id"))
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    
    # Print header
    if rows:
        print(f"\nHeaders: {list(rows[0].keys())}")
        print(f"\nTotal rows: {len(rows)}")
        print(f"\nFirst 3 rows:")
        for r in rows[:3]:
            print(r)
