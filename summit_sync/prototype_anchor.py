import os
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from lib.tessie import TessieClient
import re

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(message)s')

WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TARGET_DATE = "2026-02-06"

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

def main():
    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")
    
    print(f"--- Prototyping Anchor Logic for {TARGET_DATE} ---")
    
    # 1. Fetch Drives
    start_dt = datetime.strptime(f"{TARGET_DATE} 00:00:00", "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(f"{TARGET_DATE} 23:59:59", "%Y-%m-%d %H:%M:%S")
    
    print(f"Fetching Tessie drives for VIN {vin}...")
    drives = tessie.get_drives(vin, int(start_dt.timestamp()), int(end_dt.timestamp()))
    print(f"Found {len(drives)} drives.")
    
    # Sort drives by time (Tessie usually returns newest first)
    # Use 'started_at' which seems to be the key
    drives.sort(key=lambda x: x.get('started_at', 0))

    # 2. Index Images
    print("Indexing local images...")
    images = []
    for f in os.listdir(WATCH_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            full_path = os.path.join(WATCH_DIR, f)
            dt = get_file_dt(full_path)
            # Filter loosely for the target date (since we might have overnight trips)
            if dt.strftime("%Y-%m-%d") == TARGET_DATE:
                images.append({"filename": f, "dt": dt, "path": full_path})
    print(f"Found {len(images)} images for {TARGET_DATE}.")

    # 3. The Anchor Logic
    print("\n--- Matching Images to Drives ---")
    
    for i, drive in enumerate(drives):
        # Handle missing keys safely
        start_ts = drive.get('started_at')
        end_ts = drive.get('ended_at')
        
        if not start_ts or not end_ts:
            print(f"[TRIP #{i+1}] SKIP - Missing timestamps")
            continue

        drive_start = datetime.fromtimestamp(start_ts)
        drive_end = datetime.fromtimestamp(end_ts)
        
        # Define the Magnet Window
        # Start: 15 mins before (for Offer cards)
        # End: 15 mins after (for Receipts)
        window_start = drive_start - timedelta(minutes=15)
        window_end = drive_end + timedelta(minutes=15)
        
        matched_images = []
        for img in images:
            if window_start <= img['dt'] <= window_end:
                matched_images.append(img)
                
        # Basic Classification
        has_receipt = any("Trip Details" in img['filename'] or img['dt'] > drive_end for img in matched_images)
        # Also check for "details" in filename if OCR was done, but here we only have filenames.
        # Screenshot filenames don't contain content info unless renamed.
        # But earlier process might have renamed them?
        # The prompt says: "Screenshot_20260206_..."
        
        status = "COMPLETED" if matched_images else "NO MATCHES"

        duration_min = (end_ts - start_ts) / 60
        # distance might be 'distance' or 'odometer_distance' (trip specific?)
        # Let's try 'distance' first, then fallback
        distance_mi = drive.get('distance', drive.get('odometer_distance', 0))
        
        print(f"\n[TRIP #{i+1}] {drive_start.strftime('%H:%M')} - {drive_end.strftime('%H:%M')} ({duration_min:.1f} min, {distance_mi:.1f} mi)")
        print(f"   Status: {status}")
        print(f"   Matches: {len(matched_images)} images")
        for img in matched_images:
            offset = (img['dt'] - drive_start).total_seconds() / 60
            timing_label = " DURING"
            if offset < 0: timing_label = " BEFORE"
            elif img['dt'] > drive_end: timing_label = " AFTER "
            
            print(f"      - {img['filename']} ({timing_label} {abs(offset):.1f} min)")

if __name__ == "__main__":
    main()
