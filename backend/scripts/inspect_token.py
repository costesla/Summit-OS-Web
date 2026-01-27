import os
import requests
import json
import jwt # Make sure pyjwt is installed, or we can use a simpler method
from dotenv import load_dotenv

script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '.env'))

def inspect_token():
    tenant_id = os.environ.get("OAUTH_TENANT_ID")
    client_id = os.environ.get("OAUTH_CLIENT_ID")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    
    res = requests.post(url, data=data)
    token = res.json().get("access_token")
    
    if not token:
        print("FAIL: Could not acquire token.")
        return

    # Basic JWT decoding without needing a library (split by dot)
    try:
        header, payload, signature = token.split('.')
        # Pad payload if necessary
        missing_padding = len(payload) % 4
        if missing_padding:
            payload += '=' * (4 - missing_padding)
        
        import base64
        decoded_payload = base64.b64decode(payload).decode('utf-8')
        payload_json = json.loads(decoded_payload)
        
        print("TOKEN ROLES/SCOPES:")
        roles = payload_json.get("roles", [])
        if roles:
            for r in roles:
                print(f"- [ROLE] {r}")
        else:
            print("- No Roles found (Check if App Permissions were granted and Consented)")
            
        scp = payload_json.get("scp", "")
        if scp:
            print(f"- [SCOPES] {scp}")
            
    except Exception as e:
        print(f"Error decoding token: {str(e)}")

if __name__ == "__main__":
    inspect_token()
