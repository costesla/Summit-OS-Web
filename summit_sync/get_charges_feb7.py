from lib.tessie import TessieClient
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()
t = TessieClient()
vin = os.environ.get('TESSIE_VIN')

# Feb 7, 2026
start = datetime.strptime('2026-02-07 00:00:00', '%Y-%m-%d %H:%M:%S')
end = datetime.strptime('2026-02-07 23:59:59', '%Y-%m-%d %H:%M:%S')

print(f"Fetching charging sessions for Feb 7, 2026...\n")

try:
    charges = t.get_charges(vin, int(start.timestamp()), int(end.timestamp()))
    
    print(f"Found {len(charges)} charging sessions\n")
    
    for i, charge in enumerate(charges, 1):
        print(f"Charging Session #{i}:")
        print(f"  ID: {charge.get('id')}")
        
        started = datetime.fromtimestamp(charge.get('started_at', 0))
        ended = datetime.fromtimestamp(charge.get('ended_at', 0))
        
        print(f"  Started: {started}")
        print(f"  Ended: {ended}")
        print(f"  Duration: {(ended - started).total_seconds() / 60:.1f} minutes")
        print(f"  Location: {charge.get('location', 'Unknown')}")
        print(f"  Start SOC: {charge.get('starting_battery', 0)}%")
        print(f"  End SOC: {charge.get('ending_battery', 0)}%")
        print(f"  Energy Added: {charge.get('energy_added', 0)} kWh")
        print(f"  Cost: ${charge.get('cost', 0)}")
        print()
        
except Exception as e:
    print(f"Error: {e}")
