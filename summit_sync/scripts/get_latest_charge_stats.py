import os
import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()
logging.basicConfig(level=logging.INFO)

def main():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("ERROR: No VIN found")
        return

    tessie = TessieClient()
    
    # Check today
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    ts_start = int(today_start.timestamp())
    ts_end = int(now.timestamp())
    
    print(f"Checking charges for VIN {vin} from {today_start}")
    
    try:
        charges = tessie.get_charges(vin, ts_start, ts_end)
        
        if not charges:
            print("No charges found for today.")
            # Fallback: Check last 24h
            ts_start_24 = int((now - timedelta(days=1)).timestamp())
            print("Checking last 24h...")
            charges = tessie.get_charges(vin, ts_start_24, ts_end)
            
        if charges:
            print(f"Found {len(charges)} sessions.")
            for c in charges:
                print("--- SESSION ---")
                print(f"ID: {c.get('id')}")
                print(f"Location: {c.get('location')}")
                print(f"Energy Added: {c.get('charge_energy_added')} kWh")
                print(f"Cost: ${c.get('cost', 0.0)}")
                print(f"Start SOC: {c.get('starting_battery')}%")
                print(f"End SOC: {c.get('ending_battery')}%")
                print(f"Duration: {c.get('duration_minutes')} min")
                print("---------------")
        else:
            print("Zero sessions found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
