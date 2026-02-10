import requests
import json
import os

def test_ocr_rest():
    # Load from local.settings.json manually
    settings_path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\summit_sync\local.settings.json"
    with open(settings_path, "r") as f:
        settings = json.load(f)["Values"]
        
    endpoint = settings["AZURE_VISION_ENDPOINT"]
    key = settings["AZURE_VISION_KEY"]
    
    # URL for Read API (REST)
    # The endpoint in settings usually looks like: https://REGION.api.cognitive.microsoft.com/
    # But here it's: https://ai-summitos-prod.cognitiveservices.azure.com/
    
    url = f"{endpoint.rstrip('/')}/computervision/imageanalysis:analyze?api-version=2023-02-01-preview&features=read"
    
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/octet-stream"
    }
    
    image_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026\Screenshot_20260131_001222_Uber Driver.jpg"
    
    with open(image_path, "rb") as f:
        data = f.read()
        
    print(f"Calling: {url}")
    resp = requests.post(url, headers=headers, data=data)
    
    print(f"Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    test_ocr_rest()
