
import os
import json

root = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Normalized"

# Search for the final receipt screenshot (20:32 MST)
candidates = []
for path, dirs, files in os.walk(root):
    for f in files:
        if "2032" in f and "sidecar" in f:
            candidates.append(os.path.join(path, f))

print(f"Checking {len(candidates)} sidecar candidates for the 8:32 PM MST receipt...")

for cp in candidates:
    with open(cp, "r") as f:
        data = json.load(f)
        print(f"File: {data['filename']}")
        print(f"Extraction: {data.get('extraction')}")
        print(f"Matched Telemetry: {data.get('telemetry_match')}")
        print("-" * 20)
