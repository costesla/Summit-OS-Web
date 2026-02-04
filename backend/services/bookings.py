import os
import requests
import logging
from datetime import datetime
from .graph import GraphClient

class BookingsClient:
    """
    Client for interacting with Microsoft Bookings via Graph API.
    """
    def __init__(self):
        self.graph = GraphClient()
        # This will be the ID of the Bookings Business (e.g. info@costesla.com)
        self.business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID")

    def get_staff_availability(self, start_dt: datetime, end_dt: datetime):
        """
        Retrieves availability for all staff in the bookings business.
        """
        if not self.business_id:
            raise Exception("MS_BOOKINGS_BUSINESS_ID not configured")

        token = self.graph._get_token()
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}/getStaffAvailability"
        
        payload = {
            "staffIds": [], # Empty list gets availability for all staff
            "startDateTime": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "America/Denver"
            },
            "endDateTime": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "America/Denver"
            }
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        if not resp.ok:
            logging.error(f"Bookings Availability Error: {resp.text}")
            resp.raise_for_status()
            
        return resp.json().get("value", [])

    def create_appointment(self, customer_data: dict, start_dt: datetime, end_dt: datetime, service_id: str):
        """
        Creates a new booking appointment.
        """
        if not self.business_id:
            raise Exception("MS_BOOKINGS_BUSINESS_ID not configured")

        token = self.graph._get_token()
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}/appointments"
        
        # FIX: Formally send UTC with Z suffix and specify UTC in the payload
        start_str = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        # Modernized payload structure per Microsoft Graph v1.0 docs
        payload = {
            "customerTimeZone": "Mountain Standard Time",
            "smsNotificationsEnabled": False,
            "endDateTime": {
                "dateTime": end_str,
                "timeZone": "UTC"
            },
            "startDateTime": {
                "dateTime": start_str,
                "timeZone": "UTC"
            },
            "serviceId": service_id,
            "customers": [
                {
                    "@odata.type": "#microsoft.graph.bookingCustomerInformation",
                    "name": customer_data.get('name'),
                    "emailAddress": customer_data.get('email'),
                    "phone": customer_data.get('phone', ''),
                    "notes": f"Pickup: {customer_data.get('pickup')}\nDropoff: {customer_data.get('dropoff')}"
                }
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logging.info(f"Creating Bookings appointment for {customer_data.get('email')} at {start_str}")
        
        resp = requests.post(url, headers=headers, json=payload)
        if not resp.ok:
            # CAPTURE BODY: This is crucial for seeing the 'message' from Microsoft (e.g. 'Invalid Service ID')
            error_detail = resp.text
            logging.error(f"Bookings Appt Error: {resp.status_code} - {error_detail}")
            raise Exception(f"Microsoft Graph Error: {resp.status_code} - {error_detail}")
            
        return resp.json()
