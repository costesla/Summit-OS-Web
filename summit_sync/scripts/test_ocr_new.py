import os
import sys
import logging
from dotenv import load_dotenv

# Add parent directory to path so we can import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.ocr import OCRClient

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_ocr():
    # Load environment variables
    load_dotenv()
    
    # Initialize OCR Client
    print("--- Initializing OCR Client ---")
    ocr = OCRClient()
    
    if not ocr.client:
        print("Error: OCR Client could not be initialized. Check AZURE_VISION_ENDPOINT.")
        return

    test_image = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "public", "pikes-peak-bg.png")
    if os.path.exists(test_image):
        print(f"\n--- Testing extract_text_from_stream with {test_image} ---")
        text = ocr.extract_text_from_stream(test_image)
        if text:
            print("OCR Result:")
            print(text)
            
            print("\n--- Parsing Result ---")
            parsed = ocr.parse_ubertrip(text)
            print(parsed)
            
            print("\n--- Classifying Result ---")
            category = ocr.classify_image(text)
            print(f"Category: {category}")
        else:
            print("OCR failed to extract text.")
    else:
        print(f"\nNo test image found at {test_image}. Skipping stream test.")

    print("\nNext steps:")
    print("1. Update AZURE_VISION_ENDPOINT in .env if needed.")
    print("2. Ensure you are logged in via 'az login'.")
    print("3. Run this script with a path to a real image to verify.")

if __name__ == "__main__":
    test_ocr()
