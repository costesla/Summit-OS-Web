import os
import json
from dotenv import load_dotenv
from lib.tessie import TessieClient
from datetime import datetime, timedelta

# Load environment
load_dotenv()

# Initialize Tessie client
tessie = TessieClient()
vin = os.environ.get("TESSIE_VIN")

if not vin:
    print("ERROR: TESSIE_VIN not found in environment")
    exit(1)

# Get today's drives
today = datetime.now()
start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=0)

print(f"Fetching drives for {today.strftime('%Y-%m-%d')}...")
print(f"From: {start_of_day}")
print(f"To: {end_of_day}")
print()

drives = tessie.get_drives(vin, int(start_of_day.timestamp()), int(end_of_day.timestamp()))

if not drives:
    print("No drives found for today.")
    print("\nTrying yesterday...")
    yesterday = today - timedelta(days=1)
    start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
    drives = tessie.get_drives(vin, int(start_of_day.timestamp()), int(end_of_day.timestamp()))

if not drives:
    print("No drives found.")
    exit(0)

print(f"Found {len(drives)} drives\n")
print("=" * 80)
print("FIRST DRIVE DATA:")
print("=" * 80)
print(json.dumps(drives[0], indent=2))
print("\n" + "=" * 80)
print("BATTERY FIELDS CHECK:")
print("=" * 80)

drive = drives[0]
print(f"starting_battery_level: {drive.get('starting_battery_level', 'NOT FOUND')}")
print(f"ending_battery_level: {drive.get('ending_battery_level', 'NOT FOUND')}")
print(f"energy_used: {drive.get('energy_used', 'NOT FOUND')}")
print(f"battery_level_start: {drive.get('battery_level_start', 'NOT FOUND')}")
print(f"battery_level_end: {drive.get('battery_level_end', 'NOT FOUND')}")
print(f"start_battery_level: {drive.get('start_battery_level', 'NOT FOUND')}")
print(f"end_battery_level: {drive.get('end_battery_level', 'NOT FOUND')}")

print("\n" + "=" * 80)
print("ALL AVAILABLE KEYS:")
print("=" * 80)
print(", ".join(sorted(drive.keys())))
