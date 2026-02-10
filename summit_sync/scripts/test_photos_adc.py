import google.auth
from google.auth.transport.requests import Request
import requests
import json

def test_photos_adc():
    print("Loading Application Default Credentials...")
    try:
        # Load credentials with the specific scope
        scopes = ['https://www.googleapis.com/auth/photoslibrary.readonly']
        credentials, project = google.auth.default(scopes=scopes)
        
        # Refresh the credentials
        credentials.refresh(Request())
        
        headers = {'Authorization': f'Bearer {credentials.token}'}
        
        print(f"Project: {project}")
        print("Searching Google Photos via ADC...")
        
        url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
        payload = {
            'pageSize': 10
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        
        if resp.status_code == 200:
            print("✅ SUCCESS: ADC has Photos Access")
            items = resp.json().get('mediaItems', [])
            for item in items:
                print(f"{item.get('creationTime')} | {item.get('filename')}")
        else:
            print(f"❌ FAILURE: {resp.status_code}")
            print(resp.json())
            
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_photos_adc()
