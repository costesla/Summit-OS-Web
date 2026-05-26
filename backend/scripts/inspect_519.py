import sys
import os

# Add backend directory to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.config_loader import config_loader
config_loader.load()

from services.graph import GraphClient
from services.uber_matcher import UberMatcherService

def inspect():
    graph = GraphClient()
    path = "Uber Driver/2026/May/Week 4/5.19.26"
    print(f"Listing files in {path}...")
    files = graph.list_folder_files(path)
    
    import base64
    from openai import OpenAI
    
    oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    for f in files:
        name = f.get("name")
        if not name.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
            
        print(f"\n==================================================")
        print(f"Analyzing File: '{name}'")
        print(f"==================================================")
        
        content = graph.get_file_content(f.get("id"))
        b64 = base64.b64encode(content).decode("utf-8")
        
        resp = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What type of document or screen is this image? Describe its main content, merchant name, total, date/time, and list the items if readable."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "low"
                        }
                    }
                ]
            }],
            max_tokens=250,
            temperature=0
        )
        print(resp.choices[0].message.content.strip())

if __name__ == "__main__":
    inspect()
