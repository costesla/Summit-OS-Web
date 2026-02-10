
import os
import json

root = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Normalized"
report_path = os.path.join(root, "mission_report.json")

with open(report_path, "r") as f:
    report = json.load(f)

print(f"Total artifacts: {len(report)}")

# Look for 18:3x screenshots
for item in report:
    filename = item["filename"]
    # Screenshots are usually Screenshot_YYYYMMDD_HHMMSS
    if "20260202_183" in filename or "18:3" in item["filename"]:
        print(f"Found candidate: {filename}")
        sidecar_rel = f"{filename}_sidecar.json"
        # The path in report is the directory
        sidecar_path = os.path.join(root, item["path"], sidecar_rel)
        if os.path.exists(sidecar_path):
            with open(sidecar_path, "r") as sf:
                sidecar = json.load(sf)
                print(f"  Timestamp MST: {sidecar.get('timestamp_mst')}")
                print(f"  OCR Text: {sidecar.get('ocr_raw_text')[:100]}...")
                print(f"  Extraction: {sidecar.get('extraction')}")
                print(f"  Telemetry Match: {sidecar.get('telemetry_match')}")
                print("-" * 20)
