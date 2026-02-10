
import os
import re
from datetime import datetime

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
DATE_TARGET = "20260202"

def get_timestamp(filename):
    # Try parsing Screenshot_YYYYMMDD_HHMMSS.jpg
    match = re.search(r"Screenshot_(\d{8})_(\d{6})", filename)
    if match:
        dt_str = f"{match.group(1)} {match.group(2)}"
        return datetime.strptime(dt_str, "%Y%m%d %H%M%S")
    
    # Try parsing YYYYMMDD_HHMMSS.jpg
    match = re.search(r"(\d{8})_(\d{6})", filename)
    if match:
        dt_str = f"{match.group(1)} {match.group(2)}"
        return datetime.strptime(dt_str, "%Y%m%d %H%M%S")
    
    return None

files_found = []
for file in os.listdir(WATCH_DIR):
    if DATE_TARGET in file:
        ts = get_timestamp(file)
        if ts:
            files_found.append((file, ts))

files_found.sort(key=lambda x: x[1])

print(f"Total files on {DATE_TARGET}: {len(files_found)}")
for f, ts in files_found:
    print(f"{ts.strftime('%H:%M:%S')} - {f}")
