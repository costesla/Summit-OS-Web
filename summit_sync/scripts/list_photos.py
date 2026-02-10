import requests
import subprocess
import json

def list_photos():
    try:
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], shell=True).decode().strip()
        headers = {'Authorization': f'Bearer {token}'}
        
        # Search for Jan 30/31 items
        url = 'https://photoslibrary.googleapis.com/v1/mediaItems:search'
        payload = {
            'pageSize': 50,
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
            items = resp.json().get('mediaItems', [])
            print(f"Found {len(items)} items in Google Photos.")
            for item in items:
                print(f"{item.get('creationTime')} | {item.get('filename')} | {item.get('baseUrl')}")
        else:
            print(f"Error {resp.status_code}: {resp.json()}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    list_photos()
