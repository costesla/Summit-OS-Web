from lib.ocr import OCRClient
from dotenv import load_dotenv
import os

load_dotenv()
ocr = OCRClient()

filepath = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\20260207_125419.jpg"

if os.path.exists(filepath):
    print(f"Scanning: {os.path.basename(filepath)}")
    print("="*80)
    
    result = ocr.extract_text_from_stream(filepath)
    
    if result:
        # Save to file for review
        with open("red_star_vapor_text.txt", 'w', encoding='utf-8') as f:
            f.write(result)
        print("Saved OCR text to: red_star_vapor_text.txt")
        print(f"\nText preview (first 500 chars):")
        print(result[:500])
    else:
        print("No text extracted")
else:
    print(f"File not found: {filepath}")
