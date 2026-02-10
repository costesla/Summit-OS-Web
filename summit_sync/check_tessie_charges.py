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

print(f"Checking Tessie API for charging sessions on Feb 7, 2026...")
print(f"Start: {int(start.timestamp())}, End: {int(end.timestamp())}")

# Check if there's a get_charges or similar method
print(f"\nAvailable Tessie methods:")
for method in dir(t):
    if not method.startswith('_'):
        print(f"  - {method}")
