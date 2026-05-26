import requests
import json

def main():
    url = "https://summitos-api.azurewebsites.net/api/operations/get-day-trips?date=2026-05-22"
    print(f"GET {url}")
    try:
        resp = requests.get(url, timeout=10)
        print(f"Status Code: {resp.status_code}")
        print("Response Content:")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
