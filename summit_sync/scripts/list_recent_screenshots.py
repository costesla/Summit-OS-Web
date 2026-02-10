import os
import time
from datetime import datetime

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"

def list_recent_screenshots():
    print(f"Scanning {WATCH_DIR} for recent screenshots...")
    files = []
    for root, dirs, fnames in os.walk(WATCH_DIR):
        for name in fnames:
            if name.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, name)
                mtime = os.path.getmtime(full_path)
                dt = datetime.fromtimestamp(mtime)
                # Looking for Jan 28
                if dt.year == 2026 and dt.month == 1 and dt.day == 28:
                    files.append((dt, full_path))
    
    files.sort(key=lambda x: x[0])
    for dt, path in files:
        print(f"{dt}: {path}")

if __name__ == "__main__":
    list_recent_screenshots()
