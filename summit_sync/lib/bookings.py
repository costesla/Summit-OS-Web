import os
import requests
import logging
from datetime import datetime
from lib.graph import GraphClient

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
        
        payload = {
            "@odata.type": "#microsoft.graph.bookingAppointment",
            "customerTimeZone": "America/Denver",
            "smsNotificationsEnabled": True,
            "endDateTime": {
                "@odata.type": "#microsoft.graph.dateTimeTimeZone",
                "dateTime": end_dt.isoformat(),
                "timeZone": "America/Denver"
            },
            "isLocationOnline": False,
            "optOutOfCustomerEmail": False,
            "anonymousJoinWebUrl": None,
            "postBuffer": "PT30M", # 30 min post-buffer
            "preBuffer": "PT30M",  # 30 min pre-buffer
            "price": 0, # Pricing handled by our engine
            "priceType": "undefined",
            "reminders": [
                {
                    "@odata.type": "#microsoft.graph.bookingReminder",
                    "message": "Your SummitOS driver is arriving soon!",
                    "offset": "PT30M",
                    "recipients": "customer"
                }
            ],
            "serviceId": service_id,
            "startDateTime": {
                "@odata.type": "#microsoft.graph.dateTimeTimeZone",
                "dateTime": start_dt.isoformat(),
                "timeZone": "America/Denver"
            },
            "customers": [
                {
                    "@odata.type": "#microsoft.graph.bookingCustomerInformation",
                    "customerId": None,
                    "displayName": customer_data.get('name'),
                    "emailAddress": customer_data.get('email'),
                    "phone": customer_data.get('phone'),
                    "location": {
                        "@odata.type": "#microsoft.graph.location",
                        "displayName": customer_data.get('pickup')
                    }
                }
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        if not resp.ok:
            logging.error(f"Bookings Appt Error: {resp.text}")
            resp.raise_for_status()
            
        return resp.json()
