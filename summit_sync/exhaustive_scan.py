
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

# 18:00 MST = 01:00 UTC (1770080400)
# 20:00 MST = 03:00 UTC (1770087600)
drives = tessie.get_drives(VIN, 1770080400, 1770087600)

print(f"Drives found: {len(drives)}")
total_dist = 0
for d in drives:
    start_ts = d.get('started_at')
    end_ts = d.get('ended_at') or (start_ts + d.get('duration', 0) if start_ts else None)
    
    start_dt = datetime.fromtimestamp(start_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST'))
    end_dt = datetime.fromtimestamp(end_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST')) if end_ts else "N/A"
    
    dist = d.get('odometer_distance', 0)
    print(f"ID {d['id']}: {start_dt.strftime('%H:%M:%S')} -> {end_dt.strftime('%H:%M:%S') if end_ts else 'N/A'} MST")
    print(f"  {d.get('starting_location')} -> {d.get('ending_location')}")
    print(f"  Miles: {dist}")
    print("-" * 20)
    total_dist += dist

print(f"Combined Odometer Miles in Window: {total_dist:.2f}")
