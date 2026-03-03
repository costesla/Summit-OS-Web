import os
import requests
import logging
import json
from datetime import datetime

class SharePointClient:
    """
    Client for interacting with SharePoint Online via Microsoft Graph.
    Implements governed file upload and metadata tagging.
    """
    
    def __init__(self):
        self.tenant_id = os.environ.get("OAUTH_TENANT_ID")
        self.client_id = os.environ.get("OAUTH_CLIENT_ID")
        self.client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
        self.site_name = os.environ.get("SHAREPOINT_SITE_NAME", "Summit Operations") # Configurable
        self.lib_name = os.environ.get("SHAREPOINT_LIB_NAME", "Trip Artifacts") # Configurable
        
        self.site_id = os.environ.get("SHAREPOINT_SITE_ID") # Performance optimization if known
        self.drive_id = os.environ.get("SHAREPOINT_DRIVE_ID")
        
        self.token = None
        self.token_expires = 0

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logging.error("❌ SharePointClient: Missing OAuth credentials in environment")

    def _get_access_token(self):
        """Get or refresh OAuth2 access token for Microsoft Graph"""
        now = datetime.now().timestamp()
        if self.token and now < self.token_expires - 60: # Buffer 60s
            return self.token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        try:
            res = requests.post(url, data=data)
            res.raise_for_status()
            token_data = res.json()
            self.token = token_data.get("access_token")
            self.token_expires = now + token_data.get("expires_in", 3600)
            return self.token
        except Exception as e:
            logging.error(f"Failed to authenticate with Graph: {e}")
            raise

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def resolve_ids(self):
        """Resolve Site ID and Drive (Library) ID if not in env vars."""
        if self.site_id and self.drive_id:
            return

        headers = self._get_headers()
        
        # 1. Resolve Site
        if not self.site_id:
            logging.info(f"Resolving Site ID for '{self.site_name}'...")
            
            # Try Direct Host-Relative Resolution first (More deterministic)
            hostname = "costesla.sharepoint.com"
            path = f"/sites/{self.site_name}"
            direct_url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}"
            
            headers = self._get_headers()
            res = requests.get(direct_url, headers=headers)
            if res.ok:
                self.site_id = res.json().get('id')
                logging.info(f"✅ Found Site ID via Direct Path: {self.site_id}")
            else:
                # Fallback to Search
                logging.warning(f"Direct resolution failed for {path}. Falling back to search...")
                search_url = f"https://graph.microsoft.com/v1.0/sites?search={self.site_name}"
                res = requests.get(search_url, headers=headers)
                if res.ok:
                    sites = res.json().get('value', [])
                    for s in sites:
                        # Match name or displayName
                        if s.get('name') == self.site_name or s.get('displayName') == self.site_name:
                            self.site_id = s.get('id')
                            logging.info(f"✅ Found Site ID via Search: {self.site_id}")
                            break
            
            if not self.site_id:
                logging.error(f"❌ Could not find site '{self.site_name}' (Tried direct and search)")
                return

        # 2. Resolve Drive (Document Library)
        if not self.drive_id:
            logging.info(f"Resolving Drive ID for Library '{self.lib_name}'...")
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives"
            res = requests.get(url, headers=headers)
            if res.ok:
                drives = res.json().get('value', [])
                drive_names = [d.get('name') for d in drives]
                logging.info(f"Available libraries: {drive_names}")
                
                for d in drives:
                    if d.get('name') == self.lib_name:
                        self.drive_id = d.get('id')
                        logging.info(f"✅ Found Drive ID: {self.drive_id}")
                        break
            
            if not self.drive_id:
                 logging.error(f"❌ Could not find document library '{self.lib_name}' in {drive_names if 'drive_names' in locals() else '[]'}")

    def upload_file(self, local_path_or_name, destination_path, file_content=None):
        """
        Uploads a file to SharePoint.
        
        :param local_path_or_name: Local path (if uploading from disk) or filename (if uploading bytes).
        :param destination_path: Relative path in the library (e.g., '2026/02/10/file.png')
        :param file_content: Optional bytes content. If provided, uploads this instead of reading from disk.
        :return: driveItem dictionary
        """
        self.resolve_ids()
        if not self.site_id or not self.drive_id:
            logging.error("Cannot upload: Missing Site/Drive IDs")
            return None

        # Ensure destination path doesn't start with /
        if destination_path.startswith('/'): destination_path = destination_path[1:]

        filename = os.path.basename(local_path_or_name)
        
        if not file_content:
             # Read from disk if content not provided
             with open(local_path_or_name, 'rb') as f:
                 file_data = f.read()
        else:
             file_data = file_content
        
        # Override Content-Type for the upload request
        headers = self._get_headers()
        upload_headers = headers.copy()
        upload_headers["Content-Type"] = "application/octet-stream"
        
        # Proper URL for uploading to a path in a drive
        url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{destination_path}:/content"
        
        try:
            res = requests.put(url, headers=upload_headers, data=file_data)
            res.raise_for_status()
            item = res.json()
            logging.info(f"✅ Upload Complete. Item ID: {item.get('id')}")
            return item
        except Exception as e:
            logging.error(f"❌ Upload Failed: {e}")
            if hasattr(e, 'response') and e.response:
                logging.error(f"Response: {e.response.text}")
            return None

    def update_metadata(self, item_id, metadata):
        """
        Updates the ListItem fields for a given DriveItem.
        
        :param item_id: The id of the DriveItem (file)
        :param metadata: Dictionary of field names and values
        """
        self.resolve_ids()
        
        # 1. Get List Item ID from Drive Item
        # Drive Items are wrappers; the metadata lives on the underlying ListItem
        # Path: /drives/{drive-id}/items/{item-id}?$expand=listItem
        url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{item_id}?$expand=listItem"
        headers = self._get_headers()
        
        try:
            res = requests.get(url, headers=headers)
            res.raise_for_status()
            data = res.json()
            list_item = data.get('listItem')
            if not list_item:
                logging.error(f"No ListItem found for DriveItem {item_id}")
                return
            
            list_item_id = list_item.get('id')
            
            # 2. Patch the fields
            # Path: /sites/{site-id}/lists/{list-id}/items/{item-id}/fields
            # But we can easier go via drive item:
            # PATCH /drives/{drive-id}/items/{item-id}/listItem/fields
            
            patch_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{item_id}/listItem/fields"
            
            payload = metadata # e.g. {"TripID": "123", "Amount": 24.50}
            
            patch_res = requests.patch(patch_url, headers=headers, json=payload)
            patch_res.raise_for_status()
            logging.info(f"✅ Metadata updated for {item_id}")
            
        except Exception as e:
            logging.error(f"❌ Failed to update metadata: {e}")
            if hasattr(e, 'response') and e.response:
                logging.error(f"Response: {e.response.text}")
