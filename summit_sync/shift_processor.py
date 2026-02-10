
import os
import re
import json
import hashlib
import shutil
from datetime import datetime

# --- Configuration ---
SOURCE_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
OUTPUT_ROOT = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data"
DATE_TARGET = "20260202"
SHIFT_START_STR = "04:45:00"
SHIFT_END_STR = "20:42:00"

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

def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def process_shift():
    shift_start = datetime.strptime(f"{DATE_TARGET} {SHIFT_START_STR}", "%Y%m%d %H:%M:%S")
    shift_end = datetime.strptime(f"{DATE_TARGET} {SHIFT_END_STR}", "%Y%m%d %H:%M:%S")
    
    # Year/Month/Day/ShiftStart-ShiftEnd/
    shift_label = f"{shift_start.strftime('%H%M')}-{shift_end.strftime('%H%M')}"
    target_rel_path = os.path.join(
        shift_start.strftime("%Y"),
        shift_start.strftime("%m"),
        shift_start.strftime("%d"),
        shift_label
    )
    target_dir = os.path.join(OUTPUT_ROOT, target_rel_path)
    os.makedirs(target_dir, exist_ok=True)

    images_to_process = []
    
    for file in os.listdir(SOURCE_DIR):
        if DATE_TARGET in file:
            ts = get_timestamp(file)
            if ts and shift_start <= ts <= shift_end:
                images_to_process.append((file, ts))

    images_to_process.sort(key=lambda x: x[1])

    summary = {
        "shift_start": shift_start.isoformat(),
        "shift_end": shift_end.isoformat(),
        "image_count": len(images_to_process),
        "target_directory": target_dir,
        "files": []
    }

    for filename, ts in images_to_process:
        src_path = os.path.join(SOURCE_DIR, filename)
        file_hash = calculate_hash(src_path)
        
        # Sidecar Schema
        sidecar = {
            "filename": filename,
            "timestamp": ts.isoformat(),
            "timestamp_epoch": ts.timestamp(),
            "shift_id": shift_label,
            "artifact_hash": file_hash,
            "ingestion_time": datetime.now().isoformat(),
            "summitos_compliant": True,
            "lineage": "SummitSync_ManualRouting"
        }
        
        # Save sidecar
        sidecar_filename = f"{os.path.splitext(filename)[0]}_sidecar.json"
        sidecar_path = os.path.join(target_dir, sidecar_filename)
        
        with open(sidecar_path, "w") as f:
            json.dump(sidecar, f, indent=4)
            
        # Optional: In a real scenario we might move/copy the images too
        # shutil.copy2(src_path, os.path.join(target_dir, filename))
        
        summary["files"].append({
            "filename": filename,
            "timestamp": ts.strftime("%H:%M:%S"),
            "hash": file_hash
        })

    # Save final shift summary
    with open(os.path.join(target_dir, "shift_audit.json"), "w") as f:
        json.dump(summary, f, indent=4)
        
    # Also save to current directory for easy access
    with open("summit_sync/shift_result.json", "w") as f:
        json.dump(summary, f, indent=4)
        
    return summary

if __name__ == "__main__":
    result = process_shift()
    print(f"Processed {result['image_count']} images.")
