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
        Creates a new booking appointment using standard Graph Calendar API 
        (Bypassing Bookings API due to persistent 401 Service Principal issues).
        """
        # Construct Event Details
        name = customer_data.get('name', 'Customer')
        email = customer_data.get('email')
        phone = customer_data.get('phone', 'N/A')
        pickup = customer_data.get('pickup', 'N/A')
        dropoff = customer_data.get('dropoff', 'N/A')
        notes = customer_data.get('notes', '')
        
        subject = f"Booking: {name}"
        body = f"""
        <h3>New Booking from SummitOS</h3>
        <p><strong>Customer:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Phone:</strong> {phone}</p>
        <hr>
        <p><strong>Pickup:</strong> {pickup}</p>
        <p><strong>Dropoff:</strong> {dropoff}</p>
        <p><strong>Service ID:</strong> {service_id}</p>
        <p><strong>Notes:</strong> {notes}</p>
        """
        
        location = pickup if pickup else "SummitOS Service"
        
        # Use existing GraphClient logic which we know works (Calendar API)
        logging.info(f"Creating Calendar Event (Fallback) for {email} at {start_dt}")
        
        try:
            # create_calendar_event(self, subject, body, start_dt, end_dt, location, attendee_email)
            resp = self.graph.create_calendar_event(
                subject=subject,
                body=body,
                start_dt=start_dt,
                end_dt=end_dt,
                location=location,
                attendee_email=email
            )
            return resp
        except Exception as e:
            logging.error(f"Calendar Fallback Error: {e}")
            raise e
