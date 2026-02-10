import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()

def check_drives():
    vin = os.environ.get("TESSIE_VIN")
    client = TessieClient()
    
    # Get drives for today (starting from midnight)
    now = datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ts_start = int(midnight.timestamp())
    ts_end = int(now.timestamp())
    
    print(f"Fetching drives for {vin} from {midnight} to Now...")
    
    drives = client.get_drives(vin, ts_start, ts_end)
    
    print(f"\nFound {len(drives)} drives:")
    print("--------------------------------------------------")
    for i, d in enumerate(drives): # Tessie returns newest first usually
        # Convert timestamps
        start = datetime.fromtimestamp(d['started_at']).strftime('%H:%M')
        end = datetime.fromtimestamp(d['ended_at']).strftime('%H:%M') if d.get('ended_at') else "Active"
        dist = d.get('distance', 0)
        start_addr = d.get('starting_sublocality') or d.get('starting_city') or "Unknown"
        end_addr = d.get('ending_sublocality') or d.get('ending_city') or "Unknown"
        
        print(f"#{i+1}: {start} -> {end} | {dist} mi | {start_addr} -> {end_addr}")
        # print(json.dumps(d, indent=2)) # Debug
    print("--------------------------------------------------")

if __name__ == "__main__":
    check_drives()
