import requests
import json

def main():
    url = "https://summitos-api.azurewebsites.net/api/copilot/tessie/day-summary?date=2026-05-17"
    print("Hitting live URL:", url)
    try:
        resp = requests.get(url, timeout=15)
        print("Status Code:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            print("Response:")
            print(json.dumps(data, indent=2))
        else:
            print("Response Text:", resp.text)
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
