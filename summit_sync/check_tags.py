import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from lib.tessie import TessieClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)
tessie = TessieClient()
vin = os.environ.get("TESSIE_VIN")
TARGET_DATE = "2026-02-06"

def check_tags():
    print(f"--- Checking Tags for {TARGET_DATE} ---")
    start_dt = datetime.strptime(f"{TARGET_DATE} 00:00:00", "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(f"{TARGET_DATE} 23:59:59", "%Y-%m-%d %H:%M:%S")

    try:
        drives = tessie.get_drives(vin, int(start_dt.timestamp()), int(end_dt.timestamp()))
    except Exception as e:
        print(f"Error: {e}")
        return

    if not drives:
        print("No drives found.")
        return

    drives.sort(key=lambda x: x.get('started_at', 0))
    
    print(f"{'Time':<10} | {'Tag':<20} | {'Distance':<10}")
    print("-" * 50)
    
    for d in drives:
        start = datetime.fromtimestamp(d['started_at']).strftime("%H:%M")
        tag = d.get('tag') or "Users_Label_None" # Tessie returns None if empty?
        dist = d.get('distance', 0)
        
        print(f"{start:<10} | {str(tag):<20} | {dist:<10}")

if __name__ == "__main__":
    check_tags()
