
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

# Window: 17:30 MST to 20:30 MST (00:30 to 03:30 UTC Feb 3)
# 1770078600 to 1770089400
drives = tessie.get_drives(VIN, 1770078600, 1770089400)

print(f"Total drives in window: {len(drives)}")
for d in drives:
    start_ts = d.get('started_at')
    duration = d.get('duration', 0)
    end_ts = d.get('ended_at') or (start_ts + duration if start_ts else None)
    
    start_dt = datetime.fromtimestamp(start_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST'))
    end_dt = datetime.fromtimestamp(end_ts, tz=pytz.UTC).astimezone(pytz.timezone('MST')) if end_ts else "N/A"
    
    print(f"Drive {d['id']}: {start_dt.strftime('%H:%M:%S')} -> {end_dt.strftime('%H:%M:%S') if end_ts else 'N/A'} MST")
    print(f"  Start Loc: {d.get('starting_location')}")
    print(f"  End Loc:   {d.get('ending_location')}")
    print(f"  Distance:  {d.get('odometer_distance')} mi")
    print("-" * 30)

# Check mission report for screenshots in this window
report_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Normalized\mission_report.json"
if os.path.exists(report_path):
    with open(report_path, "r") as f:
        report = json.load(f)
    print("\nScreenshots in 18:00-19:30 MST window:")
    for item in report:
        if "18:" in item["filename"] or "19:" in item["filename"]:
            print(f"  {item['filename']} -> {item['path']}")
