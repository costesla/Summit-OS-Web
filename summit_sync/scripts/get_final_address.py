import os
import sys
import requests
import json
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tessie import TessieClient

load_dotenv()

def get_exact_address():
    vin = os.environ.get("TESSIE_VIN")
    client = TessieClient()
    print(f"Fetching location for {vin}...")
    state = client.get_vehicle_state(vin)
    
    drive = state.get('drive_state', {})
    lat = drive.get('latitude')
    lon = drive.get('longitude')
    
    print(f"Coordinates: {lat}, {lon}")
    
    # Reverse Geocode with full details
    headers = {'User-Agent': 'SummitOS/1.0'}
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.json()
        
        print("\n--- Full Address Data ---")
        print(json.dumps(data.get('address', {}), indent=2))
        
        addr = data.get('address', {})
        full_string = f"{addr.get('house_number', '')} {addr.get('road', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('postcode', '')}"
        print(f"\nConstructed Address: {full_string.strip()}")
        
    except Exception as e:
        print(f"Error reverse geocoding: {e}")

if __name__ == "__main__":
    get_exact_address()
