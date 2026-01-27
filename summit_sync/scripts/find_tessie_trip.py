
import os
import sys
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)

def find_trip():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not found in .env")
        return

    client = TessieClient()
    
    # Look back 2 days to be safe
    now = datetime.now()
    start_dt = now - timedelta(days=2)
    
    ts_start = int(start_dt.timestamp())
    ts_end = int(now.timestamp())
    
    print(f"Searching drives from {start_dt} to {now}...")
    drives = client.get_drives(vin, ts_start, ts_end)
    
    if not drives:
        print("No drives found.")
        return

    # Sort typically
    drives.sort(key=lambda x: x.get('started_at', 0))

    target_pickup = "Wuthering Heights"
    target_dropoff = "Grand vista" # lowercase v based on user input

    found = False
    for drive in drives:
        start_loc = drive.get('starting_address') or drive.get('starting_saved_location') or 'Unknown'
        end_loc = drive.get('ending_address') or drive.get('ending_saved_location') or 'Unknown'
        
        # Resolve if unknown (optional, but good for matching)
        if start_loc == 'Unknown':
             start_loc = client._resolve_address(drive.get('starting_latitude'), drive.get('starting_longitude')) or 'Unknown'
        if end_loc == 'Unknown':
             end_loc = client._resolve_address(drive.get('ending_latitude'), drive.get('ending_longitude')) or 'Unknown'

        # Check for match
        if target_pickup.lower() in start_loc.lower() and target_dropoff.lower() in end_loc.lower():
            print("\n✅ FOUND MATCHING DRIVE:")
            print(f"ID: {drive.get('id')}")
            print(f"Date: {datetime.fromtimestamp(drive.get('started_at'))}")
            print(f"Start: {start_loc}")
            print(f"End: {end_loc}")
            print(f"Distance: {drive.get('odometer_distance')} miles")
            
            # Print full details for logging
            print(f"TS Start: {drive.get('started_at')}")
            print(f"TS End: {drive.get('ended_at')}")
            found = True
            break
            
    if not found:
        print("\nNo exact match found for Wuthering Heights -> Grand vista.")
        print("Listing all recent drives for manual review (Last 20):")
        # Reverse to show newest last
        for drive in drives[-20:]: 
             start_loc = drive.get('starting_address') or drive.get('starting_saved_location') or 'Unknown'
             end_loc = drive.get('ending_address') or drive.get('ending_saved_location') or 'Unknown'
             
             # Resolve if unknown
             if start_loc == 'Unknown':
                  start_loc = client._resolve_address(drive.get('starting_latitude'), drive.get('starting_longitude')) or 'Unknown'
             if end_loc == 'Unknown':
                  end_loc = client._resolve_address(drive.get('ending_latitude'), drive.get('ending_longitude')) or 'Unknown'

             print(f"ID: {drive.get('id')} | {datetime.fromtimestamp(drive.get('started_at'))} | {start_loc} -> {end_loc}")

if __name__ == "__main__":
    find_trip()
