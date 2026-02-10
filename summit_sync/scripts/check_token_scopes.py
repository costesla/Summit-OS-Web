import requests
import subprocess
import json

def check_token_info():
    try:
        # Try to get the access token from gcloud
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], shell=True).decode().strip()
        
        # Check token info via Google's endpoint
        url = f"https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={token}"
        resp = requests.get(url)
        
        if resp.status_code == 200:
            print("--- Token Info ---")
            info = resp.json()
            print(f"Scope: {info.get('scope')}")
            print(f"Expires in: {info.get('expires_in')}")
            
            # Check if Photos Library scope is present
            scopes = info.get('scope', '').split(' ')
            if 'https://www.googleapis.com/auth/photoslibrary.readonly' in scopes:
                print("✅ Photos scope is PRESENT")
            else:
                print("❌ Photos scope is MISSING")
        else:
            print(f"Error checking token: {resp.status_code}")
            print(resp.json())
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    check_token_info()
