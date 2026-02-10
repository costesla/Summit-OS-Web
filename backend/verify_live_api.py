
import requests
import json

url = "https://summitos-api.azurewebsites.net/api/quote"
payload = {
    "pickup": "1 Lake Ave, Colorado Springs, CO",
    "dropoff": "1194 Magnolia St, Colorado Springs, CO"
}

print(f"Testing live API at {url}...")
try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    # Test partial address case
    payload_partial = {
        "pickup": "2005 Spirerock Path, Colorado Springs, CO 80919",
        "dropoff": "9181 s"
    }
    print(f"\nTesting partial address (should return success=False with 200)...")
    response_partial = requests.post(url, json=payload_partial, timeout=30)
    print(f"Status Code: {response_partial.status_code}")
    print(f"Response: {response_partial.text}")

except Exception as e:
    print(f"Error during verification: {e}")
