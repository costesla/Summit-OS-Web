import os
import sys
import json
import requests
import io
import csv

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

folder_path = "Uber Driver/2026/May/Week 5/5.26.26"
files = graph.list_folder_files(folder_path)

csv_file = next((f for f in files if f.get("name").endswith(".csv") and "Tessie" in f.get("name")), None)
content = graph.get_file_content(csv_file.get("id"))
text = content.decode("utf-8-sig")
reader = csv.DictReader(io.StringIO(text))
rows = list(reader)

# Categorize by tag
uber_min = 0
jackie_min = 0
other_min = 0

print(f"{'Tag':<40} {'Start':<17} {'End':<17} {'Min':<6}")
print("-" * 82)

for r in rows:
    tag = r.get("Tag", "") or ""
    dur = int(r.get("Duration (Minutes)", 0) or 0)
    start = r.get("Started At (MDT)", "")
    end = r.get("Ended At (MDT)", "")
    print(f"{tag:<40} {start:<17} {end:<17} {dur:<6}")
    
    tag_lower = tag.lower()
    if "uber" in tag_lower:
        uber_min += dur
    elif "jackie" in tag_lower:
        jackie_min += dur
    else:
        other_min += dur

total_combined = uber_min + jackie_min
print(f"\n=== SUMMARY ===")
print(f"Uber-tagged trips:   {uber_min} min  = {int(uber_min//60)}h {int(uber_min%60)}m")
print(f"Jackie-tagged trips: {jackie_min} min  = {int(jackie_min//60)}h {int(jackie_min%60)}m")
print(f"Other (Private):     {other_min} min  = {int(other_min//60)}h {int(other_min%60)}m")
print(f"COMBINED (Uber+Jackie): {total_combined} min = {total_combined/60:.2f} hrs = {int(total_combined//60)}h {int(total_combined%60)}m")
