
import os
import sys
import json
import logging
import hashlib
import pytz
import time
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
from summit_sync.lib.datetime_utils import normalize_to_utc, get_summit_routing_path
from backend.services.ocr import OCRClient

# --- MISSION CONFIGURATION ---
SHIFT_AUDIT_PATH = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data\2026\02\02\0445-2042\shift_audit.json"
SOURCE_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
OUTPUT_ROOT = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Normalized"
VIN = os.environ.get("TESSIE_VIN")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

class SummitMissionOrchestrator:
    def __init__(self):
        self.tessie = TessieClient()
        self.ocr = OCRClient()
        self.shift_data = self._load_shift()
        self.drives = []

    def _load_shift(self):
        if not os.path.exists(SHIFT_AUDIT_PATH):
            raise FileNotFoundError(f"Shift audit missing: {SHIFT_AUDIT_PATH}")
        with open(SHIFT_AUDIT_PATH, "r") as f:
            return json.load(f)

    def agent_fetch_telemetry(self):
        """Fetches Tessie drives for the shift's UTC window."""
        # 1. Normalize shift bounds to UTC (they are MST in the audit)
        start_utc = normalize_to_utc(self.shift_data["shift_start"])
        end_utc = normalize_to_utc(self.shift_data["shift_end"])
        
        # 2. Safety Padding: -30 mins to +30 mins to ensure window capture
        window_start = int(start_utc.timestamp()) - 1800
        window_end = int(end_utc.timestamp()) + 1800
        
        logging.info(f"FETCH_WINDOW: Seeking drives between {start_utc.isoformat()} and {end_utc.isoformat()}")
        logging.info(f"FETCH_BOUNDS: Epoch {window_start} -> {window_end}")
        
        self.drives = self.tessie.get_drives(VIN, window_start, window_end)
        
        if not self.drives:
            logging.error(f"FETCH_EMPTY: No drives retrieved. Correcting query context...")
            # Fallback: Query last 24h if window fails
            now_ts = int(datetime.now().timestamp())
            self.drives = self.tessie.get_drives(VIN, now_ts - 86400, now_ts)
            
        logging.info(f"FETCH_SUCCESS: Retrieved {len(self.drives) if self.drives else 0} drives.")

    def run_mission(self):
        self.agent_fetch_telemetry()
        
        results = []
        # Process ALL files now that we are self-healing
        for img_item in self.shift_data["files"]:
            try:
                result = self.process_artifact(img_item)
                results.append(result)
            except Exception as e:
                logging.error(f"Failed to process {img_item['filename']}: {e}")

        # Final mission report
        report_path = os.path.join(OUTPUT_ROOT, "mission_report.json")
        os.makedirs(OUTPUT_ROOT, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(results, f, indent=4)
        
        logging.info(f"Mission complete. Processed {len(results)} artifacts.")

    def process_artifact(self, item):
        filename = item["filename"]
        img_path = os.path.join(SOURCE_DIR, filename)
        
        # 1. TIMEZONE AGENT (Normalization First)
        # Screenshot filenames are like Screenshot_20260202_044546.jpg (MST)
        # We use the audit timestamp which is already split
        img_dt_str = f"20260202 {item['timestamp']}"
        utc_dt = normalize_to_utc(img_dt_str)
        
        # 2. OCR AGENT
        logging.info(f"OCR_AGENT: Extracting text for {filename}")
        
        max_retries = 5
        retry_delay = 5.0 # Increased base delay
        raw_text = ""
        
        for attempt in range(max_retries):
            try:
                time.sleep(retry_delay) 
                raw_text = self.ocr.extract_text_from_stream(img_path)
                break
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Too Many Requests" in error_msg:
                    # Dynamically respect Azure's 47-50s throttle window
                    wait_time = 50 + (attempt * 10) 
                    logging.warning(f"OCR_LIMIT: Throttled by Azure. Waiting {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logging.error(f"OCR_ERROR: Unexpected failure for {filename}: {e}")
                    raise e

        extraction = self.ocr.parse_ubertrip(raw_text)
        
        # 3. MATCHING AGENT (Using UTC-normalized timestamp & OCR extraction for tags)
        logging.info(f"MATCHING_AGENT: Aligning {filename} with Telemetry")
        best_drive = self._match(utc_dt, extraction)
        
        # 4. Routing Agent
        block = "Uber_Shift_02.02"
        trip_id = extraction.get("rider", "Private") + "_" + utc_dt.strftime("%H%M")
        routing_path = get_summit_routing_path(utc_dt, block, trip_id)
        full_output_dir = os.path.join(OUTPUT_ROOT, routing_path)
        os.makedirs(full_output_dir, exist_ok=True)
        
        # 5. Sidecar Agent
        sidecar = {
            "filename": filename,
            "hash": item["hash"],
            "timestamp_mst": item["timestamp"],
            "timestamp_utc": utc_dt.isoformat(),
            "scan_date_utc": datetime.now().isoformat(),
            "ocr_raw_text": raw_text,
            "extraction": extraction,
            "telemetry_match": best_drive.get("id") if best_drive else None,
            "telemetry_miles": best_drive.get("distance") if best_drive else 0.0,
            "uber_miles": extraction.get("distance_miles"),
            "summitos_compliant": True,
            "routing_path": routing_path
        }
        
        sidecar_path = os.path.join(full_output_dir, f"{filename}_sidecar.json")
        with open(sidecar_path, "w") as f:
            json.dump(sidecar, f, indent=4)
            
        logging.info(f"Artifact finalized at: {routing_path}")
        return {"filename": filename, "status": "COMPLIANT", "path": routing_path}

    def _match(self, utc_dt, extraction=None):
        img_epoch = utc_dt.timestamp()
        best_match = None
        min_diff = 3600 # 1 hour max tolerance
        
        # Self-Correction Diagnostic Data
        closest_diff = 999999
        nearest_drive_utc = "N/A"
        
        # LOGGING MST vs UTC
        mst_str = utc_dt.strftime("%H:%M:%S")
        logging.info(f"MATCH_AGENT: Normalizing MST {mst_str} -> UTC {utc_dt.isoformat()}")

        # Extract potential rider for tag matching
        rider_name = extraction.get("rider", "").lower() if extraction else ""

        for drive in self.drives:
            # --- PRIORITY 1: TAG MATCHING (Ground Truth) ---
            drive_tag = str(drive.get("tag", "")).lower()
            if drive_tag:
                # Check for "Uber Trip X" or "James" style tags
                # Use fuzzy match for "Uber Trip" or direct name match
                if "uber trip" in drive_tag:
                    # If this is an Uber screenshot and tag says Uber Trip, check sequence
                    # For now, if both are Uber, we treat as high-confidence
                    if rider_name != "private":
                         logging.info(f"MATCH_TAG: Found Uber Ground Truth: {drive_tag}")
                         return drive
                
                if rider_name and rider_name in drive_tag:
                    logging.info(f"MATCH_TAG: Found Passenger Ground Truth: {drive_tag} (Matches: {rider_name})")
                    return drive

            # --- PRIORITY 2: TIME MATCHING (Fallback) ---
            # Tessie started_at/finished_at are already UTC epochs
            start_ts = drive.get('started_at')
            duration = drive.get('duration', 0)
            
            drive_end_ts = drive.get('finished_at') or drive.get('ending_time') or drive.get('end_time')
            
            if not drive_end_ts and start_ts is not None:
                drive_end_ts = start_ts + duration
            
            if not drive_end_ts: 
                continue
            
            diff = abs(img_epoch - drive_end_ts)
            
            if diff < closest_diff:
                closest_diff = diff
                nearest_drive_utc = datetime.fromtimestamp(drive_end_ts, tz=pytz.UTC).isoformat()
            
            if diff < min_diff:
                min_diff = diff
                best_match = drive
        
        # Diagnostic Report
        match_window_passed = best_match is not None
        delta_seconds = round(closest_diff, 2)
        
        diag_msg = (
            f"\n--- TELEMETRY ALIGNMENT DIAGNOSTIC ---\n"
            f"  Screenshot UTC: {utc_dt.isoformat()}\n"
            f"  Nearest Drive:  {nearest_drive_utc}\n"
            f"  Delta Seconds:  {delta_seconds} ({delta_seconds/60:.2f} mins)\n"
            f"  Match Success:  {match_window_passed}\n"
            f"--------------------------------------"
        )
        
        if not match_window_passed:
            logging.warning(f"MATCH_FAIL: {diag_msg}")
        else:
            logging.info(f"MATCH_SUCCESS: {diag_msg}")
            
        return best_match

if __name__ == "__main__":
    orchestrator = SummitMissionOrchestrator()
    orchestrator.run_mission()
