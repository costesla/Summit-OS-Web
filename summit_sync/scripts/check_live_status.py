import os
import sys
import json
from datetime import datetime

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient
from dotenv import load_dotenv

load_dotenv()

def check_status():
    vin = os.environ.get("TESSIE_VIN")
    tessie = TessieClient()
    
    print(f"Checking state for VIN: {vin}")
    state = tessie.get_vehicle_state(vin)
    
    if state:
        charge_state = state.get('charge_state', {})
        drive_state = state.get('drive_state', {})
        
        print(f"Charging: {charge_state.get('charging_state')}")
        print(f"Battery: {charge_state.get('battery_level')}%")
        print(f"Range: {charge_state.get('battery_range')} miles")
        print(f"Power: {charge_state.get('charger_power')} kW")
        
        if charge_state.get('charging_state') == 'Charging':
            print(f"Session Energy: {charge_state.get('charge_energy_added')} kWh")
            
    else:
        print("Failed to get state.")

if __name__ == "__main__":
    check_status()
