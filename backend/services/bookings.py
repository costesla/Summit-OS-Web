import os
import requests
import logging
from datetime import datetime
from .graph import GraphClient

# Stripe metadata is the paid path's ONLY store between checkout and finalize,
# and it caps each VALUE at 500 characters — well under five autocompleted
# street addresses packed into one key. So the route travels as numbered keys
# instead, where the index carries the order explicitly and nothing can be
# silently truncated. Matches MAX_STOPS in the booking UI; raising one means
# checking Stripe's 50-key budget, not just this constant.
MAX_METADATA_STOPS = 5
_STOP_VALUE_LIMIT = 480  # under Stripe's 500, leaving room for nothing clever


def encode_route_metadata(stops) -> dict:
    """Ordered stops -> {'stop0': ..., 'stop1': ...} for Stripe metadata."""
    clean = [str(s).strip() for s in (stops or []) if s and str(s).strip()]
    return {
        f"stop{i}": leg[:_STOP_VALUE_LIMIT]
        for i, leg in enumerate(clean[:MAX_METADATA_STOPS])
    }


def decode_route_metadata(meta) -> list:
    """Stripe metadata -> ordered stops.

    Reads by index rather than by iterating the dict, because metadata comes
    back as an unordered mapping and dict order is not a guarantee we should
    be trusting a customer's itinerary to. Stops at the first gap: a missing
    index means the route ended there, not that a leg should be skipped.
    """
    stops = []
    for i in range(MAX_METADATA_STOPS):
        value = (meta or {}).get(f"stop{i}")
        value = str(value).strip() if value else ""
        if not value:
            break
        stops.append(value)
    return stops


def render_route_rows(pickup: str, stops, dropoff: str) -> str:
    """Receipt table rows for a route, in travel order.

    Lives here, and is used by BOTH receipt builders (the invoice/cash path in
    api/bookings.py and the Stripe path in finalize_service.py), because those
    are separate implementations that have drifted before. A customer whose
    receipt lists stops in a different order from the driver's calendar has no
    way to tell which one is the real trip.

    Falls back to the original two-row Pickup/Dropoff layout when there are no
    stops, so a plain A-to-B booking's receipt is unchanged.
    """
    label = ('padding: 15px 0 6px; font-size: 14px; color: #666666;')
    value = ('padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;')
    clean = [str(s).strip() for s in (stops or []) if s and str(s).strip()]

    def row(text, style):
        return f'<tr><td colspan="2" style="{style}">{text}</td></tr>'

    if not clean:
        return (row("Pickup Location", label) + row(pickup, value)
                + row("Dropoff Location", label) + row(dropoff, value))

    rows = row("Pickup", label) + row(pickup, value)
    for i, stop in enumerate(clean, start=1):
        rows += row(f"Stop {i}", label) + row(stop, value)
    rows += row("Final Drop-off", label) + row(dropoff, value)
    return rows


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

    def create_appointment(self, customer_data: dict, start_dt: datetime, end_dt: datetime, service_id: str, transaction_id: str = None):
        """
        Creates a new booking appointment using standard Graph Calendar API 
        (Bypassing Bookings API due to persistent 401 Service Principal issues).
        When transaction_id is provided, Graph prevents duplicate events natively.
        """
        # Construct Event Details
        name = customer_data.get('name', 'Customer')
        email = customer_data.get('email')
        phone = customer_data.get('phone', 'N/A')
        pickup = customer_data.get('pickup', 'N/A')
        dropoff = customer_data.get('dropoff', 'N/A')
        notes = customer_data.get('notes', '')
        # Intermediate stops IN TRAVEL ORDER. Blanks are dropped but the
        # surviving sequence is never sorted or de-duplicated — the order IS
        # the trip, and two visits to the same address is a real itinerary.
        stops = [s.strip() for s in (customer_data.get('stops') or []) if s and s.strip()]

        subject = f"Booking: {name}"

        # The route renders as an ordered list so the sequence is legible in
        # Outlook at a glance — this is the view the owner actually drives from.
        if stops:
            legs = "".join(
                f"<li>{leg}</li>" for leg in [pickup, *stops, dropoff]
            )
            route_html = (
                f"<p><strong>Route ({len(stops)} "
                f"{'stop' if len(stops) == 1 else 'stops'}):</strong></p>"
                f"<ol>{legs}</ol>"
            )
        else:
            route_html = (f"<p><strong>Pickup:</strong> {pickup}</p>"
                          f"<p><strong>Dropoff:</strong> {dropoff}</p>")

        body = f"""
        <h3>New Booking from SummitOS</h3>
        <p><strong>Customer:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Phone:</strong> {phone}</p>
        <hr>
        {route_html}
        <p><strong>Service ID:</strong> {service_id}</p>
        <p><strong>Notes:</strong> {notes}</p>
        """

        location = pickup if pickup else "SummitOS Service"
        # Graph's Event resource carries an ORDERED `locations` array alongside
        # the singular `location`. Sending it means the sequence survives as
        # structured data, not just as prose inside the body.
        locations = [pickup, *stops, dropoff] if stops else None
        
        # Use existing GraphClient logic which we know works (Calendar API)
        logging.info(f"Creating Calendar Event (Fallback) for {email} at {start_dt}")
        
        try:
            # create_calendar_event(self, subject, body, start_dt, end_dt, location, attendee_email, transaction_id)
            resp = self.graph.create_calendar_event(
                subject=subject,
                body=body,
                start_dt=start_dt,
                end_dt=end_dt,
                location=location,
                attendee_email=None, # Prevent Graph from sending a duplicate basic calendar invite
                transaction_id=transaction_id,
                locations=locations,
            )
            return resp
        except Exception as e:
            logging.error(f"Calendar Fallback Error: {e}")
            raise e
