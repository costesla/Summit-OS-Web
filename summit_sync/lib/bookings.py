import os
import requests
import datetime
import logging

class BookingsClient:
    """
    Client for interacting with Microsoft Bookings API via Microsoft Graph.
    """
    
    def __init__(self):
        self.tenant_id = os.environ.get("OAUTH_TENANT_ID")
        self.client_id = os.environ.get("OAUTH_CLIENT_ID")
        self.client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
        self.business_id = os.environ.get("BOOKINGS_BUSINESS_ID", "PrivateTrips@costesla.com")
        self.service_id = os.environ.get("BOOKINGS_SERVICE_ID") # e.g. "Airport Transfer"
        
        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logging.error("❌ BookingsClient: Missing Microsoft Graph credentials in environment")

    def _get_access_token(self):
        """Get OAuth2 access token for Microsoft Graph"""
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        res = requests.post(url, data=data)
        res.raise_for_status()
        return res.json().get("access_token")

    def get_availability(self, date_str: str):
        """
        Get available time slots for a specific date (YYYY-MM-DD).
        """
        token = self._get_access_token()
        
        # Parse date
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        weekday = date_obj.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        
        # Determine Hours for the day
        if weekday < 4: # Mon - Thu
            start_t, end_t = "04:30:00", "22:00:00"
        elif weekday == 4: # Fri
            start_t, end_t = "04:30:00", "23:59:59" # Full day until midnight
        elif weekday == 5: # Sat
            start_t, end_t = "08:00:00", "23:00:00"
        else: # Sun
            start_t, end_t = "08:00:00", "18:00:00"

        start_dt = f"{date_str}T{start_t}Z"
        end_dt = f"{date_str}T{end_t}Z"

        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}/getServiceAvailability"
        
        payload = {
            "serviceId": self.service_id,
            "startDateTime": {
                "dateTime": start_dt,
                "timeZone": "UTC"
            },
            "endDateTime": {
                "dateTime": end_dt,
                "timeZone": "UTC"
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        res = requests.post(url, headers=headers, json=payload)
        
        if not res.ok:
            logging.error(f"❌ Graph API Error: {res.text}")
            return []

        data = res.json()
        return data.get("value", [])

    def create_appointment(self, customer_data, start_time_iso):
        """
        Create a new booking in Microsoft Bookings.
        """
        token = self._get_access_token()
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}/appointments"

        # Duration is typically 1 hour for these trips
        start_dt = datetime.datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
        end_dt = start_dt + datetime.timedelta(hours=1)

        payload = {
            "@odata.type": "#microsoft.graph.bookingAppointment",
            "serviceId": self.service_id,
            "startDateTime": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "UTC"
            },
            "endDateTime": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "UTC"
            },
            "customerPhone": customer_data.get("phone"),
            "customerEmailAddress": customer_data.get("email"),
            "customerName": customer_data.get("name"),
            "customerNotes": f"Pickup: {customer_data.get('pickup')}\nDropoff: {customer_data.get('dropoff')}",
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        res = requests.post(url, headers=headers, json=payload)
        res.raise_for_status()
        return res.json()
