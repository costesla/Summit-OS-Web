
import os
import sys
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient
from lib.database import DatabaseClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)

def log_specific_trip():
    target_drive_id = 360556521
    target_fare = 20.00
    target_tip = 0.00
    payment_method = "Cash"
    
    # Search window: Last 24 hours to be safe
    ts_end = int(datetime.now().timestamp())
    ts_start = ts_end - 86400
    
    vin = os.environ.get("TESSIE_VIN")
    client = TessieClient()
    db = DatabaseClient()
    
    print(f"Fetching drive details for ID {target_drive_id} (Window: 24h)...")
    drives = client.get_drives(vin, ts_start, ts_end)
    
    target_drive = None
    for d in drives:
        if d.get('id') == target_drive_id:
            target_drive = d
            break
            
    if not target_drive:
        print("Could not find the specific drive in Tessie API.")
        return

    # Extract Details
    start_ts = target_drive.get('started_at')
    end_ts = target_drive.get('ended_at')
    
    # Resolve addresses if needed
    start_loc = target_drive.get('starting_address') or target_drive.get('starting_saved_location') or 'Unknown'
    end_loc = target_drive.get('ending_address') or target_drive.get('ending_saved_location') or 'Unknown'

    if start_loc == 'Unknown':
         start_loc = client._resolve_address(target_drive.get('starting_latitude'), target_drive.get('starting_longitude')) or 'Unknown'
    if end_loc == 'Unknown':
         end_loc = client._resolve_address(target_drive.get('ending_latitude'), target_drive.get('ending_longitude')) or 'Unknown'

    distance_mi = target_drive.get('odometer_distance', 0)
    duration_min = (end_ts - start_ts) / 60 if end_ts and start_ts else 0
    
    print(f"Found Drive:")
    print(f"   Route: {start_loc} -> {end_loc}")
    print(f"   Time: {datetime.fromtimestamp(start_ts)} (Duration: {duration_min:.1f} min)")
    print(f"   Distance: {distance_mi:.1f} miles")
    
    # Construct Trip Data
    trip_id = f"TESSIE-{target_drive_id}"
    
    trip_data = {
        "trip_id": trip_id,
        "classification": "Private_Trip",
        "fare": target_fare,
        "tip": target_tip,
        "rider_payment": target_fare + target_tip,
        "driver_total": target_fare + target_tip,
        "uber_cut": 0.0,
        "payment_method": payment_method,
        "start_location": start_loc,
        "end_location": end_loc,
        "timestamp_epoch": start_ts,
        "tessie_drive_id": target_drive_id,
        "tessie_distance": distance_mi,
        "tessie_duration": duration_min,
        "distance_miles": distance_mi, # Map to both for consistency
        "duration_minutes": duration_min,
        "raw_text": "Manual Entry: Missed Booking Pricing (Tessie API Match)"
    }
    
    print(f"Logging trip {trip_id} to SQL Database...")
    try:
        db.save_trip(trip_data)
        print(f"Successfully logged cash trip for {payment_method} ${target_fare:.2f}")
    except Exception as e:
        print(f"Failed to save trip: {e}")

if __name__ == "__main__":
    log_specific_trip()
