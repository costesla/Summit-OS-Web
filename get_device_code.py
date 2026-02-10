import requests
import time
import sys

# Configuration matches your Azure App Registration
TENANT_ID = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
CLIENT_ID = "a7d212ac-dd2b-4910-a62a-b623a8ac250c" 
SCOPE = "offline_access Bookings.ReadWrite.All User.Read"

def get_device_code():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode"
    data = {
        "client_id": CLIENT_ID,
        "scope": SCOPE
    }
    resp = requests.post(url, data=data)
    if not resp.ok:
        print(f"Error getting device code: {resp.text}")
        sys.exit(1)
    
    return resp.json()

def poll_for_token(device_code):
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    interval = device_code["interval"]
    expires_in = device_code["expires_in"]
    device_code_str = device_code["device_code"]
    
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": CLIENT_ID,
        "device_code": device_code_str
    }
    
    print(f"\nWaiting for you to sign in... (Expires in {expires_in} seconds)")
    
    start_time = time.time()
    
    while True:
        resp = requests.post(url, data=data)
        if resp.ok:
            return resp.json()
        
        err = resp.json().get("error")
        if err == "authorization_pending":
            pass # Just keep waiting
        elif err == "slow_down":
            interval += 5 # Back off
        elif err == "expired_token":
            print("Time expired!")
            sys.exit(1)
        else:
            print(f"Error: {resp.text}")
        
        if time.time() - start_time > expires_in:
            print("Timed out.")
            sys.exit(1)
            
        time.sleep(interval)

if __name__ == "__main__":
    code_data = get_device_code()
    
    print("\n" + "="*60)
    print("ACTION REQUIRED: AUTHORIZE MFA")
    print("="*60)
    print(f"1. Go to: {code_data['verification_uri']}")
    print(f"2. Enter code: {code_data['user_code']}")
    print("="*60 + "\n")
    
    # We write the code to a file so the agent can read it quickly
    with open("auth_code.txt", "w") as f:
        f.write(f"URL: {code_data['verification_uri']}\nCode: {code_data['user_code']}")
        
    token_data = poll_for_token(code_data)
    
    print("\nSUCCESS! Refresh Token Acquired.")
    with open("refresh_token.txt", "w") as f:
        f.write(token_data.get("refresh_token", "NO_TOKEN_FOUND"))
