import os
import sys
import logging
from lib.ocr import OCRClient
from lib.tessie import TessieClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_pipeline(target_path):
    logging.info(f"--- Starting Local OCR Test for: {target_path} ---")
    
    # 1. OCR
    ocr = OCRClient()
    if not ocr.client:
        logging.error("❌ OCR Client not initialized. Check AZURE_VISION_ENDPOINT and AZURE_VISION_KEY in .env")
        return

    # Determine if local file or URL
    try:
        if os.path.exists(target_path):
            logging.info(f"Processing local file: {target_path}")
            raw_text = ocr.extract_text_from_stream(target_path)
        elif target_path.startswith(("http://", "https://")):
            logging.info(f"Processing URL: {target_path}")
            raw_text = ocr.extract_text(target_path)
        else:
            logging.error(f"❌ Target path not found or invalid URL: {target_path}")
            return
    except Exception as e:
        logging.error(f"❌ OCR Extraction Failed: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return

    if not raw_text:
        logging.error("❌ No text extracted from the image.")
        return

    logging.info("--- Raw OCR Text Output ---")
    print(raw_text)
    logging.info("---------------------------")

    # 2. Classification
    classification = ocr.classify_image(raw_text)
    logging.info(f"📋 Classification: {classification}")

    # 3. Parse
    if classification == "Uber_Core":
        trip_data = ocr.parse_ubertrip(raw_text)
        logging.info("✅ Parsed Uber Data:")
        for k, v in trip_data.items():
            logging.info(f"   {k}: {v}")
    elif classification == "Expense":
        logging.info("💰 Detected as an Expense receipt.")
    else:
        logging.info("ℹ️ General classification. No specific parsing applied.")

    # 4. Tessie (Optional Match)
    tessie = TessieClient()
    if tessie.api_key and os.environ.get("TESSIE_VIN"):
        import time
        fake_timestamp = time.time() 
        vin = os.environ.get("TESSIE_VIN")
        drive = tessie.match_drive_to_trip(vin, fake_timestamp)
        if drive:
            logging.info(f"🚗 Tessie Match Found: Drive ID {drive.get('id')}")
        else:
            logging.info("result: No matching Tessie drive found for current timestamp.")

if __name__ == "__main__":
    # Load env vars
    try:
        from dotenv import load_dotenv
        # Look for .env in the same directory as the script
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        load_dotenv(dotenv_path=env_path)
    except Exception as e:
        logging.warning(f"Dotenv load failed: {e}")

    if len(sys.argv) < 2:
        print("Usage: python test_local.py <path_to_image_or_url>")
        sys.exit(1)
    
    target = sys.argv[1]
    test_pipeline(target)
