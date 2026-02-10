
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Path fix
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.append(app_root)

load_dotenv(os.path.join(app_root, "summit_sync/.env"))
from summit_sync.lib.tessie import TessieClient

tessie = TessieClient()
VIN = os.environ.get("TESSIE_VIN")

# Broad range: Feb 1 to Feb 3
start = int(datetime(2026, 2, 1).timestamp())
end = int(datetime(2026, 2, 3).timestamp())

drives = tessie.get_drives(VIN, start, end)
print(f"Total drives found: {len(drives) if drives else 0}")

if drives:
    print(f"Sample Drive: {json.dumps(drives[0], indent=2)}")
    for d in drives[:10]: # Just first 10
        s_ts = d.get('starting_time') or d.get('start_time')
        e_ts = d.get('ending_time') or d.get('end_time')
        dist = d.get('distance_miles') or d.get('distance') or 0.0
        
        s_time = datetime.fromtimestamp(s_ts).strftime('%Y-%m-%d %H:%M:%S') if s_ts else "N/A"
        e_time = datetime.fromtimestamp(e_ts).strftime('%Y-%m-%d %H:%M:%S') if e_ts else "N/A"
        print(f"Drive {d.get('id', '??')}: {s_time} -> {e_time} ({dist:.2f} mi)")
