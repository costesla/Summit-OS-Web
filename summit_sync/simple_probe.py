
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

import time
end = int(time.time())
start = end - (86400 * 2)

drives = tessie.get_drives(VIN, start, end)
print(f"Total drives: {len(drives) if drives else 0}")
if drives:
    for d in drives:
        s_ts = d.get('started_at') or d.get('starting_time')
        e_ts = d.get('finished_at') or d.get('ending_time')
        dist = d.get('distance') or d.get('distance_miles') or 0.0
        
        s_str = datetime.fromtimestamp(s_ts).strftime('%H:%M:%S') if s_ts else "N/A"
        e_str = datetime.fromtimestamp(e_ts).strftime('%H:%M:%S') if e_ts else "N/A"
        date_str = datetime.fromtimestamp(s_ts).strftime('%Y-%m-%d') if s_ts else "N/A"
        
        print(f"Drive {d.get('id')}: {date_str} {s_str} -> {e_str} ({dist:.2f} mi)")
