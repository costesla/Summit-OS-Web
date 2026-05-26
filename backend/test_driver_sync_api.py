import requests
import json

def main():
    url = "https://summitos-api.azurewebsites.net/api/driver/sync?date=2026-05-18"
    try:
        resp = requests.get(url)
        print("Status code:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            print("Success:", data.get("success"))
            print("Trips count:", len(data.get("trips", [])))
            print("Expenses fastfood count:", len(data.get("expenses", {}).get("fastfood", [])))
            print("Expenses charging count:", len(data.get("expenses", {}).get("charging", [])))
            print("\nFirst 3 trips:")
            for t in data.get("trips", [])[:3]:
                print(t)
        else:
            print("Response:", resp.text)
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
