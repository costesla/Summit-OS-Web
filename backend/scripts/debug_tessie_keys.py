
import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()
client = TessieClient()
vin = os.environ.get("TESSIE_VIN")

# Today
ts_start = 1769065200 
ts_end = 1769151600 

drives = client.get_drives(vin, ts_start, ts_end)
if drives:
    print("KEYS (Sorted):")
    # Get all unique keys across all drives just in case some are sparse
    all_keys = set()
    for d in drives:
        all_keys.update(d.keys())
    
    for k in sorted(all_keys):
        print(f"- {k}")
        
    print("\nSAMPLE DRIVE (First 5 keys):")
    # Print a sample of relevant location keys
    sample = drives[0]
    loc_keys = [k for k in sample.keys() if 'location' in k or 'address' in k or 'place' in k or 'lat' in k or 'lon' in k]
    for k in loc_keys:
        print(f"{k}: {sample[k]}")
else:
    print("No drives.")
