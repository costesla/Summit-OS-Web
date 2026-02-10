import logging
import os
import json
import sys
from dotenv import load_dotenv

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.ocr import OCRClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def process_venmo_screenshots():
    load_dotenv()
    client = OCRClient()
    
    screenshots = [
        r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260128_070300_Venmo.jpg",
        r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260128_070548_Venmo.jpg"
    ]

    results = []
    for path in screenshots:
        if not os.path.exists(path):
            print(f"ERROR: Image not found at {path}")
            continue

        print(f"\n--- Processing: {os.path.basename(path)} ---")
        text = client.extract_text_from_stream(path)
        
        if text:
            print("Extracted Text:")
            print(text)
            results.append({"path": path, "text": text})
        else:
            print("FAILED: OCR extraction returned no text.")

    # Save results to a temporary file for analysis
    with open("summit_sync/venmo_ocr_results.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"\nResults saved to summit_sync/venmo_ocr_results.json")

if __name__ == "__main__":
    process_venmo_screenshots()
