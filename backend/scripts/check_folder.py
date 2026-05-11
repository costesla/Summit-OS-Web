from services.graph import GraphClient
import json

graph = GraphClient()
folder_path = "Uber Driver/2026/May/Week 1/06"

print(f"Checking folder: {folder_path}")
try:
    files = graph.list_folder_files(folder_path)
    print(f"Total files found: {len(files)}")
    for f in files:
        print(f"  - {f.get('name')} ({f.get('size')} bytes)")
except Exception as e:
    print(f"Error: {e}")
