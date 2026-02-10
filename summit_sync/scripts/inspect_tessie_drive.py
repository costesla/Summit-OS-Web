
import os
import sys
import json
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.tessie import TessieClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

tessie = TessieClient()
vin = os.environ.get("TESSIE_VIN")

# Get drives from the last 24 hours
import time
now = int(time.time())
yesterday = now - (24 * 3600)

drives = tessie.get_drives(vin, yesterday, now)
print(f"Found {len(drives)} drives.")

if drives:
    print("Sample Drive Object:")
    print(json.dumps(drives[0], indent=2))
