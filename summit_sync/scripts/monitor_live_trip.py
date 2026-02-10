import os
import sys
import time
import csv
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()

def get_private_trip_details():
    """
    Reads bookings_mock.csv to find BKG-001.
    """
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bookings_mock.csv')
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['BookingID'] == 'BKG-001':
                    return row
    except Exception as e:
        print(f"Error reading bookings CSV: {e}")
    return None

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def monitor_trip():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not set")
        return

    trip_info = get_private_trip_details()
    if not trip_info:
        print("Warning: Could not find Booking BKG-001 details.")
        trip_info = {"CustomerName": "Unknown", "ServiceName": "Unknown"}

    client = TessieClient()
    logging.getLogger("urllib3").setLevel(logging.WARNING) # 
    logging.getLogger("root").setLevel(logging.ERROR) # Suppress info logs from lib

    print(f"Initializing monitor for {trip_info['CustomerName']} ({trip_info['ServiceName']})...")

    while True:
        try:
            # Fetch Data
            state = client.get_vehicle_state(vin)
            if not state:
                print("Failed to get state. Retrying...")
                time.sleep(5)
                continue

            drive = state.get('drive_state', {})
            items = state.get('vehicle_state', {})
            charge = state.get('charge_state', {})
            
            # Process Data
            timestamp = datetime.now().strftime('%H:%M:%S')
            shift_state = drive.get('shift_state') # P, D, R, N
            speed = drive.get('speed', 0)
            if speed is None: speed = 0
            
            lat = drive.get('latitude')
            lon = drive.get('longitude')
            
            dest = drive.get('active_route_destination')
            arrival_min = drive.get('active_route_minutes_to_arrival')
            dist_mi = drive.get('active_route_miles_to_arrival')
            
            # Autopilot / FSD State
            ap_state = items.get('autopilot_state_v3')
            
            fsd_status = "Unknown / Not Reported"
            if ap_state:
                if ap_state == "active" or ap_state == "navigating_on_autopilot":
                    fsd_status = "🤖 FSD ACTIVE"
                elif ap_state == "standby":
                    fsd_status = "READY (Standby)"
                else:
                    fsd_status = f"MANUAL ({ap_state})"
            
            # Check if FSD computer is present but sleeping?
            # if not ap_state and items.get('driver_assist') == 'TeslaAP4':
            #     fsd_status += " (HW4)"

            battery = charge.get('battery_level')
            range_mi = charge.get('battery_range')
            
            # Resolve Address (Simple caching could be added here if needed, but for now we hit API)
            # To avoid spamming OSM, maybe only resolve if moved? or just rely on Tessie's address if avail
            # Tessie usually provides 'heading' etc.
            # We'll use the client._resolve_address helper if needed, but let's try to be respectful.
            # We'll print coordinates if address lookup fails or is slow.
            address = "Locating..."
            try:
                # Use internal helper
                resolved = client._resolve_address(lat, lon)
                if resolved:
                    address = resolved
            except:
                address = f"{lat}, {lon}"

            # Clear and Display Dashboard
            clear_screen()
            print("==================================================")
            print(f"      SUMMIT SYNC | LIVE TRIP MONITOR")
            print("==================================================")
            print(f" TRIP ID    : {trip_info.get('BookingID', 'BKG-001')}")
            print(f" CUSTOMER   : {trip_info['CustomerName']}")
            print(f" SERVICE    : {trip_info['ServiceName']}")
            print("--------------------------------------------------")
            print(f" TIME       : {timestamp}")
            print(f" STATUS     : {'🛑 PARKED' if shift_state == 'P' else '🚀 DRIVING'}")
            print(f" DRIVER     : {fsd_status}")
            if shift_state != 'P':
                 print(f" SPEED      : {speed} mph")
            print(f" LOCATION   : {address}")
            print("--------------------------------------------------")
            
            if dest:
                print(f" 🏁 DESTINATION : {dest}")
                print(f" ⏱️  ARRIVAL     : {arrival_min} mins")
                print(f" 📏 DISTANCE    : {dist_mi} mi")
            else:
                print(f" 🏁 DESTINATION : [No Active Navigation]")
                
            print("--------------------------------------------------")
            print(f" 🔋 BATTERY     : {battery}% ({range_mi} mi)")
            print("==================================================")
            print(" Press Ctrl+C to Stop Monitoring")

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"Error in monitor loop: {e}")
        
        # Poll interval
        time.sleep(15)

if __name__ == "__main__":
    monitor_trip()
