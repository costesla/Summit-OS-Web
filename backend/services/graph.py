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
        if not resp.ok:
            raise Exception(f"Graph Token Error: {resp.status_code} {resp.text}")
        return resp.json().get("access_token")

    def _format_iso_z(self, dt: datetime) -> str:
        """Helper to safely format datetime to ISO 8601 with Z suffix if UTC/naive."""
        if dt.tzinfo is None:
            # Assume UTC if naive, per typical Graph API usage or just standard ISO
            return dt.isoformat() + "Z"
        
        # If it has a timezone, isoformat() includes offset. 
        # CAUTION: Graph API might behave differently depending on endpoint.
        # But '2026-01-27T12:00:00-07:00Z' is INVALID.
        return dt.isoformat()

    def get_calendar_events(self, date_obj: datetime):
        token = self._get_token()
        
        # Start of day
        start_dt = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        # End of day
        end_dt = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        start_iso = self._format_iso_z(start_dt)
        end_iso = self._format_iso_z(end_dt)

        # Graph API expects ISO strings
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
            raise Exception(f"Graph Search Error: {resp.status_code} {resp.text}")
            
        data = resp.json()
        return data.get("value", [])

    def create_calendar_event(self, subject, body, start_dt, end_dt, location, attendee_email):
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/calendar/events"
        
        # Ensure UTC/ISO format
        # Graph expects: "2026-01-26T12:00:00" and specifying TimeZone, or full ISO with Z
        # We will use the specific structure required by Graph
        
        # Prepare DateTimes for Graph
        # Logic: If we send timeZone="America/Denver", the dateTime string MUST be naive (no offset).
        # We ensure start_dt and end_dt are converted to the target timezone's wall clock time, then stripped of tzinfo.
        
        # NOTE: This assumes start_dt/end_dt are correctly zoned or intended for that zone.
        # For robustness, we just format them as simple strings if they have tzinfo.
        
        start_str = start_dt.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%S')
        
        payload = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body
            },
            "start": {
                "dateTime": start_str,
                "timeZone": "America/Denver" # Enforce local time for clarity in Outlook
            },
            "end": {
                "dateTime": end_str,
                "timeZone": "America/Denver"
            },
            "location": {
                "displayName": location
            },
            "attendees": [
                {
                    "emailAddress": {
                        "address": attendee_email
                    },
                    "type": "required"
                }
            ],
            "categories": ["Private Trip", "SummitOS"],
            "showAs": "busy",
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 30
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        if not resp.ok:
            logging.error(f"Graph Create Error: {resp.text}")
            raise Exception(f"Graph Create Event Error: {resp.status_code} {resp.text}")
            
        return resp.json()
    def send_mail(self, to_email, subject, body_html, from_email="PrivateTrips@costesla.com"):
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
        
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ],
                "internetMessageHeaders": [
                    { "name": "Reply-To", "value": "peter.teehan@costesla.com" },
                    { "name": "X-Mailer", "value": "SummitOS Receipt Engine" }
                ]
            },
            "saveToSentItems": "true"
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        if not resp.ok:
            logging.error(f"Graph SendMail Error: {resp.text}")
            raise Exception(f"Graph SendMail Error: {resp.status_code} {resp.text}")
            
        return True
