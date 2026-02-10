
import os
import json
import shutil

SHIFT_AUDIT = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data\2026\02\02\0445-2042\shift_audit.json"
SOURCE_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TARGET_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\2.2.26 Uber Trip Logging"
MISSION_REPORT = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Normalized\mission_report.json"

if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR)

with open(SHIFT_AUDIT, "r") as f:
    audit = json.load(f)

print(f"Archiving {len(audit['files'])} files...")

count = 0
for item in audit["files"]:
    filename = item["filename"]
    src = os.path.join(SOURCE_DIR, filename)
    dst = os.path.join(TARGET_DIR, filename)
    
    if os.path.exists(src):
        shutil.copy2(src, dst)
        count += 1
    else:
        print(f"Warning: Source file missing: {filename}")

# Also copy the mission report for context
if os.path.exists(MISSION_REPORT):
    shutil.copy2(MISSION_REPORT, os.path.join(TARGET_DIR, "mission_summary.json"))

print(f"Successfully archived {count} screenshots to {TARGET_DIR}")
