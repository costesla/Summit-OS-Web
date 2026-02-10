
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.ocr import OCRClient
from dotenv import load_dotenv

load_dotenv()
ocr = OCRClient()

blob_url = "https://stsummitosprod.blob.core.windows.net/uploads/Screenshot_20260129_110004_Uber Driver.jpg"
print(f"Testing OCR on: {blob_url}")

try:
    text = ocr.extract_text(blob_url)
    if text:
        print("OCR Success!")
        print(f"Text Length: {len(text)}")
        print(f"Sample: {text[:100]}")
    else:
        print("OCR Returned None.")
except Exception as e:
    print(f"OCR Exception: {e}")
