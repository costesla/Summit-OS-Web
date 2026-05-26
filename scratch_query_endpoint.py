import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(os.getcwd(), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))

# Mock a func.HttpRequest
class MockRequest:
    def __init__(self, params):
        self.params = params
        self.method = "GET"
        self.headers = {}

from api.copilot import copilot_tessie_drives

def main():
    # Set correct keys in environment just in case
    os.environ["TESSIE_API_KEY"] = os.environ.get("TESSIE_API_KEY", "")
    os.environ["TESSIE_VIN"] = os.environ.get("TESSIE_VIN", "")

    req = MockRequest({
        "date": "2026-05-24",
        "tag": ""
    })

    print("Executing copilot_tessie_drives...")
    resp = copilot_tessie_drives(req)
    
    print("Response Status:", resp.status_code)
    try:
        body = json.loads(resp.get_body().decode('utf-8'))
        print("Drives in response:")
        for d in body.get("drives", []):
            if d.get("tessie_drive_id") == "397010117" or "397010117" in str(d.get("leg_ids")):
                print(json.dumps(d, indent=2))
    except Exception as e:
        print("Error reading response:", e)
        print("Raw response body:", resp.get_body())

if __name__ == "__main__":
    main()
