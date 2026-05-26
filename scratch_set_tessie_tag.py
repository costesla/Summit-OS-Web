import os
import sys
import json
from dotenv import load_dotenv

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(os.getcwd(), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load environment variables from root .env first
root_env_path = os.path.join(os.getcwd(), '.env')
if os.path.exists(root_env_path):
    print(f"Loading environment from root .env: {root_env_path}")
    load_dotenv(dotenv_path=root_env_path)

# Load environment variables from backend/local.settings.json
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    print(f"Loading environment from local.settings.json: {settings_path}")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

from services.tessie import TessieClient

def main():
    tessie = TessieClient()
    
    # Check loaded keys in environment
    api_key = os.environ.get("TESSIE_API_KEY")
    vin = os.environ.get("TESSIE_VIN")
    
    if not api_key:
        print("Error: TESSIE_API_KEY not found in environment.")
        return
    if not vin:
        print("Error: TESSIE_VIN not found in environment.")
        return

    # Use them directly in TessieClient to bypass any SecretManager issues
    tessie.api_key = api_key

    drive_id = "397010117"
    new_tag = "Private:Charging Session 2"

    print(f"Setting tag to '{new_tag}' on Tessie API for drive {drive_id} (VIN: {vin})...")
    resp = tessie.set_drive_tag(vin, drive_id, new_tag)
    print("API Response:", resp)

if __name__ == "__main__":
    main()
