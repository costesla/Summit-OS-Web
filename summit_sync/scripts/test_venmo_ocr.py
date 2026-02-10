import logging
import os
import sys
from dotenv import load_dotenv

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.ocr import OCRClient

# Configure logging to be very verbose
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def test_single_venmo():
    load_dotenv()
    print("Initializing OCR Client...")
    client = OCRClient()
    
    image_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260128_070300_Venmo.jpg"
    
    if not os.path.exists(image_path):
        print(f"ERROR: Image not found: {image_path}")
        return

    print(f"File size: {os.path.getsize(image_path)} bytes")
    print("Calling extract_text_from_stream...")
    
    try:
        # We'll use a timeout if possible, but the SDK analyze() doesn't have a direct timeout param 
        # that I recall easily without passing a custom pipeline.
        # Let's just run it and see the DEBUG logs.
        text = client.extract_text_from_stream(image_path)
        
        if text:
            print("\nSUCCESS! Extracted Text:")
            print(text)
        else:
            print("\nFAILED: No text extracted.")
            
    except Exception as e:
        print(f"\nEXCEPTION: {e}")

if __name__ == "__main__":
    test_single_venmo()
