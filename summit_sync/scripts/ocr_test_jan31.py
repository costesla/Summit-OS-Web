import sys
import os
import json
import logging

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.ocr import OCRClient

def load_settings():
    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local.settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            settings = json.load(f)
            for k, v in settings.get("Values", {}).items():
                os.environ[k] = v
                print(f"Setting: {k}")

def ocr_specific_file(filename):
    load_settings()
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    fpath = os.path.join(path, filename)
    
    if not os.path.exists(fpath):
        print(f"File not found: {fpath}")
        return

    client = OCRClient()
    if not client.client:
        print("Failed to initialize OCR Client. Check endpoint and key.")
        return
        
    print(f"Processing: {filename}")
    text = client.extract_text_from_stream(fpath)
    print("--- OCR RESULT ---")
    print(text)
    
    if text:
        # Try to parse it
        data = client.parse_ubertrip(text)
        print("--- PARSED DATA ---")
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    ocr_specific_file("Screenshot_20260131_001222_Uber Driver.jpg")
