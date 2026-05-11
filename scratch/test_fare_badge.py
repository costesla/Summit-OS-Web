import urllib.request, json

# Find the actual Azure Function URL
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "summit_sync"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "summit_sync", ".env"))

# Try to find the function URL from settings
settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "summitos-api-settings.json")
with open(settings_path) as f:
    settings = json.load(f)

base_url = None
for item in settings.get("properties", {}).items() if isinstance(settings.get("properties"), dict) else []:
    pass

# Use the known URL from the frontend config
urls_to_try = [
    "https://func-summitos-prod.azurewebsites.net/api/copilot/tessie/drives?tag=uber&days=2",
    "https://summitos-api.azurewebsites.net/api/copilot/tessie/drives?tag=uber&days=2",
]

for url in urls_to_try:
    try:
        print(f"Trying: {url}")
        r = urllib.request.urlopen(url, timeout=15)
        data = json.loads(r.read())
        drives = data.get("drives", [])
        print(f"  Total drives: {len(drives)}")
        for d in drives[:5]:
            print(f"  date={d.get('date')} time={d.get('time_mst')} tag={d.get('tag')} fare_matched={d.get('fare_matched')} earnings={d.get('driver_earnings')}")
        break
    except Exception as e:
        print(f"  Failed: {e}")
