import logging
import os
from azure.identity import DefaultAzureCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
image_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260116_075250_Uber Driver.jpg"

print(f"Testing OCR with AAD (DefaultAzureCredential)...")
print(f"Endpoint: {endpoint}")

try:
    client = ImageAnalysisClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential()
    )
    
    with open(image_path, "rb") as f:
        result = client.analyze(
            image_data=f,
            visual_features=[VisualFeatures.READ]
        )
    
    if result.read:
        print("Success! Extracted text:")
        for block in result.read.blocks:
            for line in block.lines:
                print(line.text)
    else:
        print("No text found.")

except Exception as e:
    print(f"Failed: {str(e)}")
    import traceback
    print(traceback.format_exc())
