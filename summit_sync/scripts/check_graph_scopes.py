import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'summit_sync'))
from lib.graph import GraphClient
import json
import base64

def check_scopes():
    client = GraphClient()
    token = client._get_token()
    
    # Simple JWT decode (middle part)
    parts = token.split('.')
    if len(parts) != 3:
        print("Invalid token format")
        return
        
    payload = json.loads(base64.b64decode(parts[1] + "===").decode('utf-8'))
    roles = payload.get('roles', [])
    print(f"Current App Roles (Scopes):")
    for r in roles:
        print(f"- {r}")
        
    if any("Bookings" in r for r in roles):
        print("✅ Bookings permissions detected.")
    else:
        print("❌ Missing Bookings permissions (Bookings.Read.All / Bookings.ReadWrite.All required)")

if __name__ == "__main__":
    check_scopes()
