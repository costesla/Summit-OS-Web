import os
import requests
import logging
from datetime import datetime
import pytz

class GraphClient:
    def __init__(self):
        self.tenant_id = os.environ.get("OAUTH_TENANT_ID")
        self.client_id = os.environ.get("OAUTH_CLIENT_ID")
        self.client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
        self.user_email = "peter.teehan@costesla.com" # TODO: Configurable?

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise Exception("Missing Microsoft Graph credentials in env")

    def _get_token(self):
        # OPTION 1: Client Credentials (Service Principal) - Preferred to bypass MFA
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        # Default to App Credentials (Client Credentials Flow)
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
            
        resp = requests.post(url, data=data)
        
        if not resp.ok:
            logging.error(f"Graph Token Error: {resp.status_code} {resp.text}")
            raise Exception(f"Graph Token Error: {resp.status_code} {resp.text}")
            
        return resp.json().get("access_token")
            
        return resp.json().get("access_token")

    def _format_iso_z(self, dt: datetime) -> str:
        """Helper to format datetime to ISO 8601 with Z suffix (UTC)."""
        # Convert to UTC first to ensure 'Z' is accurate
        if dt.tzinfo is not None:
            dt = dt.astimezone(pytz.UTC)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    def get_calendar_events(self, date_obj: datetime):
        token = self._get_token()
        from services.datetime_utils import get_timezone, normalize_to_utc
        mt_tz = get_timezone("CO")  # Mountain Time
        
        # Decouple date extraction from timezone shift
        if date_obj.hour == 0 and date_obj.minute == 0 and date_obj.second == 0:
            year = date_obj.year
            month = date_obj.month
            day = date_obj.day
        else:
            # It's a full timestamp, convert to local MT to determine the target day
            if date_obj.tzinfo is None:
                # If naive, treat it as UTC first to make it aware
                date_obj = date_obj.replace(tzinfo=pytz.UTC)
            date_obj_utc = normalize_to_utc(date_obj)
            date_obj_mt = date_obj_utc.astimezone(mt_tz)
            year = date_obj_mt.year
            month = date_obj_mt.month
            day = date_obj_mt.day
            
        # Construct exact Mountain Time start/end for this day
        # Start of Mountain Time day: 00:00:00
        start_mt = mt_tz.localize(datetime(year, month, day, 0, 0, 0, 0))
        # End of Mountain Time day: 23:59:59
        end_mt = mt_tz.localize(datetime(year, month, day, 23, 59, 59, 999999))
        
        # Format both to UTC ISO Z strings
        start_iso = self._format_iso_z(start_mt)
        end_iso = self._format_iso_z(end_mt)

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

    def create_calendar_event(self, subject, body, start_dt, end_dt, location, attendee_email, transaction_id=None):
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/calendar/events"
        
        # Ensure UTC/ISO format
        # Graph expects: "2026-01-26T12:00:00" and specifying TimeZone, or full ISO with Z
        # We will use the specific structure required by Graph
        
        # Prepare DateTimes for Graph
        # Logic: If we send timeZone="America/Denver", the dateTime string MUST be naive (no offset).
        # We ensure start_dt and end_dt are converted to the target timezone's wall clock time, then stripped of tzinfo.
        from services.datetime_utils import get_timezone
        denver_tz = get_timezone("CO")
        
        # Convert to Denver time if it's aware of timezones
        if start_dt.tzinfo:
            start_dt = start_dt.astimezone(denver_tz)
        if end_dt.tzinfo:
            end_dt = end_dt.astimezone(denver_tz)

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
            "categories": ["Private Trip", "SummitOS"],
            "showAs": "busy",
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 30
        }

        # Graph Calendar transactionId: if set, Graph rejects duplicate
        # creates with the same key (409 Conflict) — provider-level
        # idempotency that prevents duplicate events regardless of what
        # the caller's SQL or retry logic does.
        if transaction_id:
            payload["transactionId"] = transaction_id
        
        # Only add attendee if email is provided (prevents duplicate calendar invites to customer)
        if attendee_email:
            payload["attendees"] = [
                {
                    "emailAddress": {
                        "address": attendee_email
                    },
                    "type": "required"
                }
            ]
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logging.info(f"Graph POST to {url} with payload subject={subject}")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
        except requests.exceptions.Timeout:
            logging.error("Graph POST Timed out after 30s")
            raise Exception("Graph API Timeout")
        except Exception as e:
            logging.error(f"Graph POST Request Error: {e}")
            raise e
            
        logging.info(f"Graph Output: {resp.status_code} {resp.text}")
        
        if not resp.ok:
            logging.error(f"Graph Create Error: {resp.text}")
            raise Exception(f"Graph Create Event Error: {resp.status_code} {resp.text}")
            
        return resp.json()
    def send_mail(self, to_email, subject, body_html, from_email="peter.teehan@costesla.com"):
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
                "replyTo": [
                    {
                        "emailAddress": {
                            "address": "peter.teehan@costesla.com"
                        }
                    }
                ],
                "internetMessageHeaders": [
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

    def get_booking_business_hours(self):
        """Fetches Business Hours for the main Booking Business."""
        token = self._get_token()
        # Use configurable ID or default
        business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}"
        params = {
            "$select": "businessHours"
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        resp = requests.get(url, headers=headers, params=params)
        if not resp.ok:
            logging.error(f"Graph Business Hours Error: {resp.text}")
            raise Exception(f"Graph Business Hours Error: {resp.status_code} {resp.text}")
            
        return resp.json().get("businessHours", [])

    def get_calendar_view(self, start_dt, end_dt, top: int = 50):
        """Calendar events in [start_dt, end_dt), ordered by start, with
        times rendered in Mountain Time (Prefer header) so callers don't
        have to convert. This is where SummitOS bookings actually live —
        create_appointment writes standard calendar events, not Bookings
        API appointments."""
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/calendar/calendarView"
        params = {
            "startDateTime": self._format_iso_z(start_dt),
            "endDateTime": self._format_iso_z(end_dt),
            "$orderby": "start/dateTime",
            "$top": top,
            "$select": "subject,start,end,location,bodyPreview",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="America/Denver"',
        }
        resp = requests.get(url, headers=headers, params=params)
        if not resp.ok:
            logging.error(f"Graph Calendar View Error: {resp.text}")
            raise Exception(f"Graph Calendar View Error: {resp.status_code} {resp.text}")
        return resp.json().get("value", [])

    def get_staff_time_off(self, staff_id, start_dt, end_dt):
        """Fetches Time Off for a specific staff member within a range."""
        token = self._get_token()
        business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        
        # Ensure ISO format with Z or similar
        start_iso = self._format_iso_z(start_dt)
        end_iso = self._format_iso_z(end_dt)
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/calendar/calendarView"
        params = {
            "startDateTime": start_iso,
            "endDateTime": end_iso
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # NOTE: This endpoint might return bookings AND time off. 
        # Time Off is typically characterized by serviceId being null or specific type.
        # We will return the raw list and let the caller filter.
        
        resp = requests.get(url, headers=headers, params=params)
        if not resp.ok:
            logging.error(f"Graph Staff Calendar Error: {resp.text}")
            raise Exception(f"Graph Staff Calendar Error: {resp.status_code} {resp.text}")
            
        return resp.json().get("value", [])

    # --- ADMINISTRATION METHDOS FOR BOOKINGS ---

    def publish_booking_page(self, business_id=None):
        """Publishes the Booking Business page so it can be accessed externally."""
        token = self._get_token()
        biz_id = business_id or os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{biz_id}"
        
        # We use PATCH to update the business properties.
        payload = {
            "schedulingPolicy": {
                "allowStaffSelection": True
            },
            "isPublished": True
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logging.info(f"Publishing Booking Page for {biz_id}...")
        resp = requests.patch(url, headers=headers, json=payload)
        
        if not resp.ok:
            logging.error(f"Graph Publish Error: {resp.text}")
            raise Exception(f"Graph Publish Error: {resp.status_code} {resp.text}")
            
        # Optional: Getting the public url if available from the response
        try:
             # Typically it returns the full object on PATCH, or empty. If empty, we can just GET it.
             return self.get_booking_business_details(biz_id)
        except:
             return True

    def get_booking_business_details(self, business_id=None):
        """Helper to get general details like the public URL"""
        token = self._get_token()
        biz_id = business_id or os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{biz_id}"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        resp = requests.get(url, headers=headers)
        if resp.ok:
            return resp.json()
        return None

    def create_booking_service(self, service_payload, business_id=None):
        """Creates a new service for the Booking Business."""
        token = self._get_token()
        biz_id = business_id or os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{biz_id}/services"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logging.info(f"Creating new Booking Service in {biz_id}: {service_payload.get('displayName')}...")
        resp = requests.post(url, headers=headers, json=service_payload)
        
        if not resp.ok:
            logging.error(f"Graph Create Service Error: {resp.text}")
            raise Exception(f"Graph Create Service Error: {resp.status_code} {resp.text}")
            
        return resp.json()


    # --- ONEDRIVE / DRIVE METHODS ---

    def get_drive_root_id(self):
        """Fetches the root ID of the user's primary drive."""
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/root"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers)
        if not resp.ok:
            logging.error(f"Graph Drive Root Error: {resp.text}")
            raise Exception(f"Graph Drive Root Error: {resp.status_code} {resp.text}")
        return resp.json().get("id")

    def get_item_by_path(self, path: str):
        """
        Checks if an item exists at a given relative path.
        Example path: 'Uber Driver/2026/April'
        """
        token = self._get_token()
        # Escape path for URL
        from urllib.parse import quote
        encoded_path = quote(path)
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/root:/{encoded_path}"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers)
        if resp.status_code == 404:
            return None
        if not resp.ok:
            logging.error(f"Graph Item Path Error: {resp.text}")
            return None # Treat as not found or error
        return resp.json()

    def create_folder(self, parent_id: str, folder_name: str):
        """Creates a folder under a parent ID. Uses 'fail' conflict behavior so
        Graph returns a 409 if the folder already exists (we handle that by re-fetching)."""
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/items/{parent_id}/children"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code == 409:
            # Folder already exists — fetch it by path to get the ID
            logging.info(f"Folder '{folder_name}' already exists under parent {parent_id}, re-fetching.")
            return None  # Signal to caller to use get_item_by_path instead
        if not resp.ok:
            logging.error(f"Graph Create Folder Error: {resp.text}")
            raise Exception(f"Graph Create Folder Error: {resp.status_code} {resp.text}")
        return resp.json()

    def ensure_path_exists(self, full_path: str):
        """
        Recursively ensures a path exists in the user's OneDrive.
        Returns the ID of the final folder.
        Logs each segment as FOUND or CREATED for diagnostics.
        """
        parts = full_path.strip('/').split('/')
        current_path = ""
        last_id = self.get_drive_root_id()
        logging.info(f"ensure_path_exists: user={self.user_email}, path='{full_path}'")

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part

            item = self.get_item_by_path(current_path)
            if item:
                last_id = item.get("id")
                logging.info(f"  [FOUND]   {current_path} → {last_id}")
            else:
                new_folder = self.create_folder(last_id, part)
                if new_folder is None:
                    # 409: folder exists but path lookup missed it — re-fetch
                    item = self.get_item_by_path(current_path)
                    if item:
                        last_id = item.get("id")
                        logging.info(f"  [FOUND-409] {current_path} → {last_id}")
                    else:
                        raise Exception(f"Could not create or find folder: {current_path}")
                else:
                    last_id = new_folder.get("id")
                    logging.info(f"  [CREATED] {current_path} → {last_id}")

        return last_id

    def list_folder_files(self, path: str):
        """Lists all files in a given folder path."""
        token = self._get_token()
        from urllib.parse import quote
        encoded_path = quote(path)
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/root:/{encoded_path}:/children"
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(url, headers=headers)
        if not resp.ok:
            if resp.status_code == 404:
                return []
            logging.error(f"Graph List Files Error: {resp.text}")
            return []
        
        return resp.json().get("value", [])

    def move_file(self, item_id: str, destination_parent_id: str, new_name: str = None):
        """Moves a file to a new parent folder. Optionally renames it."""
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/items/{item_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "parentReference": {
                "id": destination_parent_id
            }
        }
        if new_name:
            payload["name"] = new_name

        resp = requests.patch(url, headers=headers, json=payload)
        if not resp.ok:
            logging.error(f"Graph Move File Error: {resp.text}")
            raise Exception(f"Graph Move File Error: {resp.status_code} {resp.text}")
        return resp.json()

    def get_file_content(self, item_id: str):
        """Downloads the bytes of a file by its ID."""
        token = self._get_token()
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/items/{item_id}/content"
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(url, headers=headers)
        if not resp.ok:
            logging.error(f"Graph Download Error: {resp.text}")
            raise Exception(f"Graph Download Error: {resp.status_code} {resp.text}")
        return resp.content
