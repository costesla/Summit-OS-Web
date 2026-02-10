import os
import sys
import json
import logging
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()

def dump_state():
    vin = os.environ.get("TESSIE_VIN")
    client = TessieClient()
    print(f"Fetching state for {vin}...")
    state = client.get_vehicle_state(vin)
    
    with open("summit_sync/debug_fsd_dump.json", "w") as f:
        json.dump(state, f, indent=4)
    print("Dumped to summit_sync/debug_fsd_dump.json")

if __name__ == "__main__":
    dump_state()
