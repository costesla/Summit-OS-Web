import logging
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, AzureCliCredential
from lib.ocr import OCRClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_ocr():
    load_dotenv()
    
    print("--- Modern OCR Client Diagnostic ---")
    client = OCRClient()
    
    # Force Azure CLI Credential for local testing to avoid IMDS timeouts
    if not client.key:
        print("Forcing AzureCliCredential for local test...")
        from azure.ai.vision.imageanalysis import ImageAnalysisClient
        client.client = ImageAnalysisClient(
            endpoint=client.endpoint,
            credential=AzureCliCredential()
        )

    print(f"Endpoint: {client.endpoint}")
    print(f"Auth Method: {'API Key' if client.key else 'Azure Identity (AAD)'}")

    # Test file path from previous logs
    image_path = os.path.join(
        os.environ.get("USERPROFILE"), 
        r"OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260116_075250_Uber Driver.jpg"
    )

    if not os.path.exists(image_path):
        print(f"WARNING: Sample image not found at {image_path}")
        return

    print(f"Extracting text from: {os.path.basename(image_path)}...")
    text = client.extract_text_from_stream(image_path)

    if text:
        print("\n--- Extracted Text ---")
        print(text)
        print("----------------------")
        
        # Test classification
        category = client.classify_image(text)
        print(f"Classification: {category}")
        
        # Test Uber parsing if applicable
        if category == "Uber_Core":
            details = client.parse_ubertrip(text)
            print(f"Uber Trip Details: {details}")
    else:
        print("FAILED: OCR extraction returned no text.")

if __name__ == "__main__":
    test_ocr()
