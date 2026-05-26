import requests
import json

url = "https://summitos-api.azurewebsites.net/api/copilot/tessie/drives"
params = {
    "date": "2026-05-24"
}

print(f"Fetching from production: {url} with params {params}...")
try:
    resp = requests.get(url, params=params, timeout=10)
    print("Response Status:", resp.status_code)
    data = resp.json()
    print("Number of drives returned:", len(data.get("drives", [])))
    
    found = False
    for d in data.get("drives", []):
        if "397010117" in str(d.get("leg_ids")) or d.get("tessie_drive_id") == "397010117":
            print("FOUND target drive in production response:")
            print(json.dumps(d, indent=2))
            found = True
            
    if not found:
        print("Target drive NOT found in production response.")
        
except Exception as e:
    print("Error querying production:", e)
