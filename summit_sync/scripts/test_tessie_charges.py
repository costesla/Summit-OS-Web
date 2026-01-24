
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

def test_charges():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        print("Error: TESSIE_VIN not found in .env")
        return

    client = TessieClient()
    
    # Range: 2026-01-22 00:00 to 23:59 (Local Denver Time approx)
    # Using specific epoch for 2026-01-22
    # 2026-01-22 00:00 MST is roughly 1769065200 (UTC-7) 
    
    # Let's target the whole day in UTC context to be safe
    # 2026-01-22 00:00 UTC = 1769040000
    # 2026-01-23 00:00 UTC = 1769126400
    
    # Better: Use the user's specific "morning" which is likely UTC-7. 
    # Just grabbing a wide window around today.
    
    ts_start = 1769065200 # Jan 22 00:00 MST
    ts_end = 1769151600   # Jan 22 23:59 MST
    
    print(f"Checking charges for VIN: {vin}")
    charges = client.get_charges(vin, ts_start, ts_end)
    
    if charges:
        print(f"\nFound {len(charges)} charging sessions:")
        for charge in charges:
            # Prioritize SOC output
            start_soc = charge.get('starting_battery', 'N/A')
            end_soc = charge.get('ending_battery', 'N/A')
            print(f"v--- SOC INFO ---v")
            print(f"START SOC: {start_soc}%")
            print(f"END SOC:   {end_soc}%")
            print(f"^----------------^")
            
            energy = charge.get('charge_energy_added', 0)
            cost = charge.get('cost', 0)
            start_time = charge.get('started_at', 0) 
            dt = datetime.fromtimestamp(start_time)
            print(f"Time: {dt} | Cost: ${cost}")
    else:
        print("No charging sessions found for this window.")

if __name__ == "__main__":
    test_charges()
