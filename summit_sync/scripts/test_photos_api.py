import requests
import subprocess
import json

def test_photos_api():
    print("Attempting to get gcloud access token...")
    try:
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], shell=True).decode().strip()
        headers = {'Authorization': f'Bearer {token}'}
        
        print("Searching Google Photos...")
        # Search for items from Jan 30th/31st
        url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
        payload = {
            'pageSize': 20,
            'filters': {
                'dateFilter': {
                    'dates': [
                        {'year': 2026, 'month': 1, 'day': 30},
                        {'year': 2026, 'month': 1, 'day': 31}
                    ]
                }
            }
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        
        if resp.status_code == 200:
            print("✅ SUCCESS: Photos API Accessible")
            items = resp.json().get('mediaItems', [])
            print(f"Found {len(items)} items.")
            for item in items:
                print(f"{item.get('creationTime')} | {item.get('filename')} | {item.get('id')}")
        else:
            print(f"❌ FAILURE: {resp.status_code}")
            print(resp.json())
            
            if resp.status_code == 403:
                print("\nTIP: Make sure you ran:")
                print("gcloud auth login --update-adc --scopes=https://www.googleapis.com/auth/photoslibrary.readonly,https://www.googleapis.com/auth/cloud-platform")
                
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_photos_api()
