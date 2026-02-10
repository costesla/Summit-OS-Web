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
                # print(f"Set {k}")

def debug_ocr(filename):
    load_settings()
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    fpath = os.path.join(path, filename)
    
    print(f"Endpoint: {os.environ.get('AZURE_VISION_ENDPOINT')}")
    print(f"Key length: {len(os.environ.get('AZURE_VISION_KEY', ''))}")
    
    client = OCRClient()
    print(f"Client initialized: {client.client is not None}")
    
    if client.client:
        print(f"Processing: {fpath}")
        try:
            from azure.ai.vision.imageanalysis.models import VisualFeatures
            with open(fpath, "rb") as f:
                result = client.client.analyze(
                    image_data=f,
                    visual_features=[VisualFeatures.READ]
                )
            print("Analyze called successfully")
            print(f"Result: {result}")
            text = client._parse_analysis_result(result)
            print(f"Parsed Text: {text}")
        except Exception as e:
            print(f"Error during analyze: {str(e)}")

if __name__ == "__main__":
    debug_ocr("Screenshot_20260131_001222_Uber Driver.jpg")
