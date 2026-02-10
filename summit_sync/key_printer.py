
import os
import sys
import json
from dotenv import load_dotenv

app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path: sys.path.append(app_root)

load_dotenv(os.path.join(app_root, "summit_sync/.env"))
from summit_sync.lib.tessie import TessieClient

tessie = TessieClient()
VIN = os.environ.get("TESSIE_VIN")

import time
drives = tessie.get_drives(VIN, int(time.time()) - 86400, int(time.time()))
if drives:
    d = drives[0]
    print(f"All Keys: {sorted(d.keys())}")
    for k, v in d.items():
        print(f"{k}: {v}")
else:
    print("No drives found.")
