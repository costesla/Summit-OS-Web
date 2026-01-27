import requests
import json

URL = "https://www.costesla.com/api/quote"

payload = {
    "tripType": "one-way",
    "pickup": "1 Lake Ave, Colorado Springs, CO",
    "dropoff": "Denver International Airport",
    "stops": [],
    "simpleWaitTime": False
}

print(f"Testing Pricing Endpoint: {URL}")
try:
    response = requests.post(URL, json=payload, timeout=20)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2))
        if data.get("success"):
            print("SUCCESS: PRICING ENGINE VERIFIED")
        else:
            print("FAILED: ENGINE RETURNED SUCCESS: FALSE")
    else:
        print(f"FAILED: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"ERROR: {e}")
