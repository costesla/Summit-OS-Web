import os
import sys
import logging
import json
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()

def check_drive():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not set")
        return

    client = TessieClient()
    print(f"Connecting to Tessie for VIN: {vin}...")
    
    state = client.get_vehicle_state(vin)
    
    if not state:
        print("Failed to get vehicle state.")
        return

    # Extract Drive State
    drive = state.get('drive_state', {})
    vehicle = state.get('vehicle_state', {})
    charge = state.get('charge_state', {})
    
    print("\n--- Live Telemetry ---")
    print(f"Timestamp: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Shift State: {drive.get('shift_state', 'Parked')}")
    print(f"Speed: {drive.get('speed', 0)} mph")
    print(f"Power: {drive.get('power', 0)} kW")
    print(f"Location: {drive.get('latitude')}, {drive.get('longitude')}")
    print(f"Heading: {drive.get('heading')}°")
    
    # Navigation Details
    dest = drive.get('active_route_destination')
    if dest:
        print(f"Destination: {dest}")
        print(f"Arrival: {drive.get('active_route_minutes_to_arrival')} mins ({drive.get('active_route_miles_to_arrival')} mi)")
    else:
        print("Destination: Not actively navigating")

    print(f"Battery: {charge.get('battery_level')}% ({charge.get('battery_range')} mi)")
    print(f"Odometer: {vehicle.get('odometer')} mi")
    
    # Try sending a reverse geocode explicitly if we have stats
    if drive.get('latitude'):
        try:
            addr = client._resolve_address(drive.get('latitude'), drive.get('longitude'))
            print(f"Address: {addr}")
        except:
            pass
            
    print("----------------------")

if __name__ == "__main__":
    check_drive()
