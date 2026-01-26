import os
import requests
import logging
from datetime import datetime

class GraphClient:
    def __init__(self):
        self.tenant_id = os.environ.get("OAUTH_TENANT_ID")
        self.client_id = os.environ.get("OAUTH_CLIENT_ID")
        self.client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
        self.user_email = "peter.teehan@costesla.com" # TODO: Configurable?

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise Exception("Missing Microsoft Graph credentials in env")

    def _get_token(self):
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        resp = requests.post(url, data=data)
        resp.raise_for_status()
        return resp.json().get("access_token")

    def get_calendar_events(self, date_obj: datetime):
        token = self._get_token()
        
        # Start of day
        start_dt = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        # End of day
        end_dt = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        start_iso = start_dt.isoformat() + "Z" # Append Z if naive, but assume caller handles tz or we just send iso
        end_iso = end_dt.isoformat() + "Z"

        # Graph API expects ISO strings
        # URL encode? Requests params handle it usually, but Graph is picky with specific format inside URL path sometimes
        # Using calendarView
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/calendar/calendarView"
        params = {
            "startDateTime": start_iso,
            "endDateTime": end_iso
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.get(url, headers=headers, params=params)
        if not resp.ok:
            logging.error(f"Graph API Error: {resp.text}")
            resp.raise_for_status()
            
        data = resp.json()
        return data.get("value", [])
