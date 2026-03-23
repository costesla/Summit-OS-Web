import os, logging, requests, sys
logging.basicConfig(level=logging.INFO)
from services.config_loader import config_loader; config_loader.load()
from services.sharepoint import SharePointClient

def main():
    sp = SharePointClient()
    sp.resolve_ids()
    if not sp.site_id or not sp.drive_id:
        logging.error("Missing site or drive ID")
        sys.exit(1)
        
    headers = sp._get_headers()
    
    # 1. Get the list ID from the drive ID
    list_url = f"https://graph.microsoft.com/v1.0/drives/{sp.drive_id}/list"
    res = requests.get(list_url, headers=headers)
    res.raise_for_status()
    list_data = res.json()
    list_id = list_data['id']
    logging.info(f"Target List ID: {list_id}")
    
    # 2. Add columns
    columns = [
        {
            "description": "Deterministic Artifact Identifier",
            "enforceUniqueValues": False,
            "hidden": False,
            "indexed": True,
            "name": "ArtifactID",
            "text": {
                "allowMultipleLines": False,
                "appendChangesToExistingText": False,
                "linesForEditing": 0,
                "maxLength": 255
            }
        },
        {
            "description": "Artifact Classification",
            "enforceUniqueValues": False,
            "hidden": False,
            "name": "Classification",
            "text": {
                "allowMultipleLines": False,
                "appendChangesToExistingText": False,
                "linesForEditing": 0,
                "maxLength": 255
            }
        },
        {
            "description": "Date of Ingestion",
            "enforceUniqueValues": False,
            "hidden": False,
            "name": "IngestionDate",
            "dateTime": {
                "displayAs": "default",
                "format": "dateOnly"
            }
        }
    ]
    
    columns_url = f"https://graph.microsoft.com/v1.0/sites/{sp.site_id}/lists/{list_id}/columns"
    
    for col in columns:
        try:
            r = requests.post(columns_url, headers=headers, json=col)
            if r.status_code == 201:
                logging.info(f"✅ Created column {col['name']}")
            elif r.status_code == 400 and 'already exists' in r.text.lower():
                logging.info(f"⚠️ Column {col['name']} already exists.")
            elif r.status_code == 409:
                logging.info(f"⚠️ Column {col['name']} conflict/already exists.")
            else:
                logging.error(f"❌ Failed to create {col['name']}. Status: {r.status_code}, Response: {r.text}")
        except Exception as e:
            logging.error(f"❌ Exception creating {col['name']}: {e}")

if __name__ == '__main__':
    main()
