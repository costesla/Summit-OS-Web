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

t1 = next(f for f in files if f.get("name") == "Scan_20260526_204311.jpg")
t2 = next(f for f in files if f.get("name") == "Scan_20260527_054933.jpg")

for img, name in [(t1, "Scan_20260526_204311.jpg"), (t2, "Scan_20260527_054933.jpg")]:
    print(f"\n=== EXACT NUMBERS FOR: {name} ===")
    content = graph.get_file_content(img.get("id"))
    b64 = base64.b64encode(content).decode("utf-8")
    
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Locate the subtotal, tax, and TOTAL amount paid on this receipt. Transcribe them exactly as they appear in the image. What is the merchant name and store address exactly?"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}
            ]
        }],
        max_tokens=300
    )
    print(resp.choices[0].message.content)
