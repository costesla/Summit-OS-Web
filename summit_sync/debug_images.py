import os
import re
from datetime import datetime, timedelta

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TARGET_DATE = "2026-02-07"

def get_file_dt(filepath):
    """Extracts timestamp from filename or falls back to creation time."""
    filename = os.path.basename(filepath)
    match = re.search(r"(\d{8})_(\d{6})", filename)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getctime(filepath))

print(f"Scanning {WATCH_DIR} for {TARGET_DATE}...")
images = []
if not os.path.exists(WATCH_DIR):
    print("Directory does not exist!")
else:
    for f in os.listdir(WATCH_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            full_path = os.path.join(WATCH_DIR, f)
            dt = get_file_dt(full_path)
            img_date = dt.strftime("%Y-%m-%d")
            
            # Simplified logic for debug
            if img_date == TARGET_DATE:
                print(f"MATCH: {f} -> {dt}")
                images.append(f)
            else:
                # Print first few failures
                if len(images) == 0: 
                     print(f"SKIP: {f} -> {dt} (Expect {TARGET_DATE})")

print(f"Found {len(images)} images.")
