
import os
import sys
import json
from datetime import datetime
import pytz
from dotenv import load_dotenv

app_root = os.getcwd()
sys.path.append(app_root)
load_dotenv(os.path.join(app_root, "summit_sync/.env"))

from summit_sync.lib.tessie import TessieClient

tessie = TessieClient()
VIN = os.environ.get("TESSIE_VIN")

# Shift window: 18:00 MST to 19:30 MST
# 18:00 MST = Feb 3 01:00 UTC (1770080400)
# 19:30 MST = Feb 3 02:30 UTC (1770085800)
drives = tessie.get_drives(VIN, 1770080400, 1770085800)

print(f"Total drives in evening window: {len(drives)}")
for d in drives:
    start_ts = d.get('started_at')
    end_ts = d.get('ended_at') or (start_ts + d.get('duration', 0) if start_ts else None)
    
    if start_ts:
        start_dt = datetime.fromtimestamp(start_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST'))
        end_dt = datetime.fromtimestamp(end_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST')) if end_ts else "N/A"
        
        print(f"Drive {d['id']}: {start_dt.strftime('%H:%M:%S')} -> {end_dt.strftime('%H:%M:%S') if end_ts else 'N/A'} MST")
        print(f"  Distance: {d.get('odometer_distance')} mi, Energy: {d.get('energy_used')} kWh")
        print(f"  Route: {d.get('starting_location')} -> {d.get('ending_location')}")
        print("-" * 20)
