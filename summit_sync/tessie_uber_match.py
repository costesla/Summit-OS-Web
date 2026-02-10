
import os
import sys
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Path fix
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.append(app_root)
    sys.path.append(os.path.join(app_root, "backend"))

# Load environment
load_dotenv(os.path.join(app_root, "summit_sync/.env"))

from summit_sync.lib.tessie import TessieClient
from backend.services.ocr import OCRClient

# --- Configuration ---
SHIFT_AUDIT_PATH = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data\2026\02\02\0445-2042\shift_audit.json"
SOURCE_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TESSIE_VIN = "7SAYGDEEXRF075302"

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def match_logic():
    # 1. Load Shift Audit
    if not os.path.exists(SHIFT_AUDIT_PATH):
        print(f"Error: Shift audit not found at {SHIFT_AUDIT_PATH}")
        return

    with open(SHIFT_AUDIT_PATH, "r") as f:
        shift_data = json.load(f)

    # 2. Initialize Clients
    tessie = TessieClient()
    ocr = OCRClient()

    # 3. Fetch Tessie Drives for Feb 2
    # Feb 2, 2026 UTC/Local approximation
    # 04:45 AM = 1769970300 (est)
    # 08:42 PM = 1770027720 (est)
    dt_start = datetime(2026, 2, 2, 4, 0, 0)
    dt_end = datetime(2026, 2, 2, 22, 0, 0)
    
    print(f"Fetching Tessie drives from {dt_start} to {dt_end}...")
    tessie_drives = tessie.get_drives(TESSIE_VIN, int(dt_start.timestamp()), int(dt_end.timestamp()))
    print(f"Found {len(tessie_drives)} Tessie drives.")

    # 4. Process Uber Screenshots and Match
    matches = []
    unmatched_uber = []
    
    # Filter for Uber Core screenshots in the shift
    uber_files = [f for f in shift_data["files"] if "Uber Driver" in f["filename"]]
    
    print(f"Processing {len(uber_files)} Uber screenshots for matching...")

    for uber_item in uber_files:
        filename = uber_item["filename"]
        img_path = os.path.join(SOURCE_DIR, filename)
        img_ts = uber_item["timestamp"] # HH:MM:SS
        img_dt_str = f"20260202 {img_ts}"
        img_dt = datetime.strptime(img_dt_str, "%Y%m%d %H:%M:%S")
        img_epoch = img_dt.timestamp()

        # Run OCR
        print(f"Running OCR on {filename}...")
        text = ocr.extract_text_from_stream(img_path)
        uber_data = ocr.parse_ubertrip(text)
        
        uber_miles = uber_data.get("distance_miles", 0.0)
        uber_earnings = uber_data.get("driver_total", 0.0)

        # Matching Logic
        best_match = None
        min_diff = 999999

        for drive in tessie_drives:
            drive_end_ts = drive.get('finished_at') or drive.get('ending_time') or drive.get('end_time')
            if not drive_end_ts: continue
            
            diff_min = (img_epoch - drive_end_ts) / 60
            abs_diff = abs(diff_min)
            
            if filename == "Screenshot_20260202_203214_Uber Driver.jpg":
                print(f"DEBUG: Screenshot {img_ts} (Epoch: {img_epoch}) vs Drive {drive['id']} (End: {drive_end_ts}, Diff: {diff_min:.2f} min)")

            if abs_diff < 60 and abs_diff < min_diff:
                min_diff = abs_diff
                best_match = drive

        if best_match:
            tessie_miles = best_match.get("distance") or best_match.get("distance_miles") or 0.0
            tessie_start_ts = best_match.get("started_at") or best_match.get("starting_time") or 0.0
            tessie_end_ts = best_match.get("finished_at") or best_match.get("ending_time") or 0.0
            
            matches.append({
                "uber_filename": filename,
                "uber_time": img_ts,
                "uber_miles": uber_miles,
                "uber_earnings": uber_earnings,
                "tessie_id": best_match.get("id"),
                "tessie_miles": round(tessie_miles, 2),
                "tessie_start": datetime.fromtimestamp(tessie_start_ts).strftime("%H:%M:%S") if tessie_start_ts else "N/A",
                "tessie_end": datetime.fromtimestamp(tessie_end_ts).strftime("%H:%M:%S") if tessie_end_ts else "N/A",
                "diff_miles": round(abs(uber_miles - tessie_miles), 2),
                "time_diff_min": round(min_diff, 2)
            })
        else:
            unmatched_uber.append({
                "uber_filename": filename,
                "uber_time": img_ts,
                "uber_miles": uber_miles
            })

    # 5. Generate Report
    report = {
        "summary": {
            "total_uber_screenshots": len(uber_files),
            "matched_trips": len(matches),
            "unmatched_trips": len(unmatched_uber),
            "total_uber_miles": sum(m["uber_miles"] for m in matches),
            "total_tessie_miles": sum(m["tessie_miles"] for m in matches),
        },
        "matches": matches,
        "unmatched": unmatched_uber
    }

    output_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data\2026\02\02\0445-2042\tessie_uber_truth.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=4)

    return report

if __name__ == "__main__":
    result = match_logic()
    if result:
        print("\n--- MATCHING SUMMARY ---")
        print(f"Matched: {result['summary']['matched_trips']}")
        print(f"Unmatched: {result['summary']['unmatched_trips']}")
        print(f"Uber Miles (Matched): {result['summary']['total_uber_miles']:.2f}")
        print(f"Tessie Miles (Matched): {result['summary']['total_tessie_miles']:.2f}")
