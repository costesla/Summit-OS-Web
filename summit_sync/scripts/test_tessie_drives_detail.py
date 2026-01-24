
import os
import sys
import logging
from dotenv import load_dotenv
from datetime import datetime

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.ERROR) # Clean output

def test_drives_detail():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not found in .env")
        return

    client = TessieClient()
    
    # Range: 2026-01-22 00:00 to 23:59 MST
    # 2026-01-22 00:00 MST is roughly 1769065200 (UTC-7)
    # Using a 24-hour window
    
    ts_start = 1769065200 # Jan 22 00:00 MST
    ts_end = 1769151600   # Jan 22 23:59 MST
    
    print(f"Fetching drive history for Jan 22, 2026...")
    drives = client.get_drives(vin, ts_start, ts_end)
    
    if not drives:
        print("No drives found for this period.")
        return

    # Sort safely
    drives.sort(key=lambda x: x.get('started_at', 0))

    total_miles = 0
    stops = []
    
    print("\n--- Summit Sync Daily Drive Analysis (Jan 22, 2026) ---")
    
    for idx, drive in enumerate(drives, 1):
        dist = drive.get('odometer_distance', 0)
        total_miles += dist
        
        start_loc = drive.get('starting_address') or drive.get('starting_saved_location') or 'Unknown'
        end_loc = drive.get('ending_address') or drive.get('ending_saved_location') or 'Unknown'
        
        if start_loc == 'Unknown':
            start_loc = client._resolve_address(drive.get('starting_latitude'), drive.get('starting_longitude')) or 'Unknown'
            
        if end_loc == 'Unknown':
            end_loc = client._resolve_address(drive.get('ending_latitude'), drive.get('ending_longitude')) or 'Unknown'
            
        # Clean up addresses
        if start_loc: start_loc = start_loc.split(',')[0]
        if end_loc: end_loc = end_loc.split(',')[0]
        
        start_ts = drive.get('started_at', 0)
        end_ts = drive.get('ended_at', 0)
        
        start_dt = datetime.fromtimestamp(start_ts).strftime('%H:%M')
        end_dt = datetime.fromtimestamp(end_ts).strftime('%H:%M')
        
        stops.append({
            'id': idx,
            'start': start_loc,
            'end': end_loc,
            'time': f"{start_dt}-{end_dt}",
            'miles': dist
        })

    # Summary Stats
    first_start = stops[0]['start'] if stops else "N/A"
    last_end = stops[-1]['end'] if stops else "N/A"
    
    print(f"\n1) Total Miles Driven:  {total_miles:.1f} miles")
    print(f"2) Total Stops Made:    {len(stops)}")
    print(f"3) Starting Point:      {first_start}")
    print(f"   Final End Point:     {last_end}")
    
    print(f"\n4) Detailed Stop Log:")
    print(f"{'Stop':<4} | {'Time':<11} | {'Miles':<6} | {'From -> To'}")
    print("-" * 60)
    
    for stop in stops:
        route = f"{stop['start']} -> {stop['end']}"
        # Truncate route if too long
        if len(route) > 35:
            route = route[:32] + "..."
            
        print(f"#{stop['id']:<3} | {stop['time']:<11} | {stop['miles']:<6.1f} | {route}")

if __name__ == "__main__":
    test_drives_detail()
