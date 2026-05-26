import sys
import os
from zoneinfo import ZoneInfo

# Add backend directory to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.config_loader import config_loader
config_loader.load()

from services.graph import GraphClient
graph = GraphClient()

def list_folders(path):
    print(f"Listing OneDrive path: '{path}'")
    try:
        items = graph.list_folder_files(path)
        for item in items:
            is_folder = "folder" in item
            print(f"  - {item.get('name')} (Folder: {is_folder})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_folders("Uber Driver")
    list_folders("Uber Driver/2026")
    list_folders("Uber Driver/2026/May")
