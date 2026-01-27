
import os
import sys
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)

def get_morning_charges():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not found in .env")
        return

    client = TessieClient()
    
    # Today: Jan 23, 2026
    # UTC-7 (MST)
    # Jan 23 00:00 MST = 1737615600
    # Current time (roughly) = 1737664000
    
    ts_start = 1737615600
    ts_end = int(datetime.now().timestamp())
    
    print(f"Checking charges for today (since 00:00 MST) for VIN: {vin}")
    charges = client.get_charges(vin, ts_start, ts_end)
    
    if charges:
        print(f"\nFound {len(charges)} charging sessions today:")
        for charge in charges:
            print(f"--- Session Detail ---")
            print(f"ID: {charge.get('id')}")
            print(f"Location: {charge.get('location')}")
            print(f"Start SOC: {charge.get('starting_battery')}%")
            print(f"End SOC: {charge.get('ending_battery')}%")
            print(f"Energy Added: {charge.get('charge_energy_added')} kWh")
            print(f"Cost: ${charge.get('cost')}")
            start_time = charge.get('started_at')
            if start_time:
                print(f"Started At: {datetime.fromtimestamp(start_time)}")
    else:
        print("No charging sessions found for today.")

if __name__ == "__main__":
    get_morning_charges()
