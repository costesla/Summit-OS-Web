import requests
import os
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
key = os.environ.get("AZURE_VISION_KEY")

# Sanity check endpoint
if not endpoint.endswith("/"):
    endpoint += "/"

# Legacy v3.2 Analyze endpoint
url = f"{endpoint}vision/v3.2/analyze?visualFeatures=Read"

image_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260116_075250_Uber Driver.jpg"

print(f"Testing OCR...")
print(f"URL: {url}")
print(f"Key: {key[:5]}...{key[-5:]}")

with open(image_path, "rb") as f:
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/octet-stream"
    }
    response = requests.post(url, headers=headers, data=f)

print(f"Status Code: {response.status_code}")
if response.status_code == 200:
    print("Success!")
    print(response.json())
else:
    print("Failed")
    print(response.text)
