import os
from services.graph import GraphClient
import json

# This script is intended to be run in an environment with credentials.
# Since I don't have them, I'll try to use the ones from the app settings if I can find them,
# or I'll just check if the user can confirm the folder path.

# Wait, I can try to list the parent folder to see what's there.
# I'll modify the script to try and catch the path issue.

graph = GraphClient() # This will fail locally without env

def check(path):
    print(f"Checking: {path}")
    try:
        files = graph.list_folder_files(path)
        print(f"Found {len(files)} items.")
        for f in files:
            print(f"  {f.get('name')} (folder: {f.get('folder') is not None})")
    except Exception as e:
        print(f"Error: {e}")

check("Uber Driver/2026/May")
check("Uber Driver/2026/May/Week 1")
check("Uber Driver/2026/May/Week 2")
