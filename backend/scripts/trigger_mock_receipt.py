import requests
import json

URL = "https://www.costesla.com/api/book"

payload = {
    "customerName": "Peter Teehan (Test)",
    "customerEmail": "peter.teehan@costesla.com",
    "pickup": "Test Pickup: The Broadmoor",
    "dropoff": "Test Dropoff: DEN Airport",
    "price": "$125.00",
    "duration": 60
}

print(f"Triggering Mock Receipt: {URL}")
print(f"Payload: {json.dumps(payload, indent=2)}")

try:
    response = requests.post(URL, json=payload, timeout=20)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        print("SUCCESS: Receipt Triggered.")
        print(response.json())
    else:
        print(f"FAILED: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"ERROR: {e}")
