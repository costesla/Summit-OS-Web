import os
import sys
import json
import base64

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from services.graph import GraphClient
from openai import OpenAI

graph = GraphClient()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

folder_path = "Uber Driver/2026/May/Week 5/5.26.26"
files = graph.list_folder_files(folder_path)

# Let's inspect the non-Uber screenshots that aren't Starbucks or Samsung Wallet
candidates = [
    "Screenshot_20260527_044038.jpg",
    "Screenshot_20260527_044200.jpg",
    "Screenshot_20260527_044257.jpg",
    "Screenshot_20260527_045906.jpg"
]

for name in candidates:
    img = next((f for f in files if f.get("name") == name), None)
    if not img:
        print(f"File not found: {name}")
        continue
        
    print(f"\n=== INSPECTING SCREENSHOT: {name} ===")
    content = graph.get_file_content(img.get("id"))
    b64 = base64.b64encode(content).decode("utf-8")
    
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Identify the merchant name, location/address (if any), transaction date, transaction time, subtotal, tax, and TOTAL amount paid/received from this image. Transcribe them exactly as they appear in the image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}
            ]
        }],
        max_tokens=400
    )
    print(resp.choices[0].message.content)
