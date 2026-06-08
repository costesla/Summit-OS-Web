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

folder_path = "Uber Driver/2026/May/Week 5/5.25.26"
files = graph.list_folder_files(folder_path)

img = next(f for f in files if f.get("name") == "Scan_20260525_135818.jpg")

print(f"\n=== INSPECTING MAY 25TH SCAN: {img.get('name')} ===")
content = graph.get_file_content(img.get("id"))
b64 = base64.b64encode(content).decode("utf-8")

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this scanned image in detail. What is the merchant name, store address, date, time, and total amount?"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}
        ]
    }],
    max_tokens=400
)
print(resp.choices[0].message.content)
