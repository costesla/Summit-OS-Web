import requests
import json
import sys

try:
    resp = requests.get("https://summitos-api.azurewebsites.net/api/diag")
    if resp.ok:
        data = resp.json()
        print("Registration Logs:")
        for log in data.get("registration_logs", []):
            print(log)
        
        print("\nFiles in root:")
        print(data.get("files", []))
        
        print("\nFiles in api/:")
        print(data.get("api_files", []))
    else:
        print(f"Error accessing diag: {resp.status_code}")
        print(resp.text)
except Exception as e:
    print(f"Diag check failed: {e}")
