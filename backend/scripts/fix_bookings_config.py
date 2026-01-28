import os
import sys
import logging
import requests

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Adjust path to include backend root so we can import 'services'
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

# Import BookingsClient from services
# This will trigger the relative import 'from .graph import GraphClient' in bookings.py
# which resolves to backend.services.graph.GraphClient
try:
    from services.bookings import BookingsClient
except ImportError as e:
    logging.error(f"Failed to import BookingsClient: {e}")
    sys.exit(1)

class BookingsConfigurator(BookingsClient):

    def __init__(self):
        self.business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
        
        # Credentials provided by user
        self.tenant_id = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
        self.client_id = "3908fbac-03a0-4670-acf9-3bb24188747b"
        self.client_secret = "kSt8Q~6bJKckBi9UwtBE85XY_4R94Emf3ek.3cMr"
        
        self.token = self._get_token_from_creds()
        
        if not self.token:
            raise Exception("Failed to acquire token")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.base_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}"

    def _get_token_from_creds(self):
        """Get token via Client Credentials Flow"""
        logging.info("🔑 Acquiring token via Client Credentials...")
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        try:
            res = requests.post(url, data=data)
            if res.ok:
                logging.info("✅ Token acquired successfully")
                return res.json().get("access_token")
            logging.error(f"❌ Token fetch failed: {res.text}")
        except Exception as e:
            logging.error(f"❌ Token fetch exception: {e}")
        return None

    def get_staff_param(self, name_query="Peter Teehan"):
        """Find the exact staff member ID for Peter Teehan"""
        logging.info(f"🔍 Searching for staff: {name_query}...")
        res = requests.get(f"{self.base_url}/staffMembers", headers=self.headers)
        if not res.ok:
            logging.error(f"❌ Failed to fetch staff: {res.text}")
            return None
        
        staff_list = res.json().get("value", [])
        for staff in staff_list:
            if name_query.lower() in staff.get("displayName", "").lower():
                logging.info(f"✅ Found Staff: {staff['displayName']} (ID: {staff['id']})")
                return staff['id']
        
        logging.error(f"❌ Staff member '{name_query}' not found!")
        return None

    def get_services(self):
        """Fetch all booking services"""
        logging.info("🔍 Fetching services...")
        res = requests.get(f"{self.base_url}/services", headers=self.headers)
        if not res.ok:
            logging.error(f"❌ Failed to fetch services: {res.text}")
            return []
        
        services = res.json().get("value", [])
        for s in services:
             logging.info(f"   📋 Found Service: {s.get('displayName')} (ID: {s.get('id')})")
        return services

    def update_service_staff(self, service_id, service_name, staff_id):
        """Assign ONLY specific staff to a service"""
        logging.info(f"⚙️ Updating Service: {service_name} ({service_id})")
        
        url = f"{self.base_url}/services/{service_id}"
        
        # 1. Update Staff Assignment ONLY (Simple Payload)
        payload = {
            "staffMemberIds": [staff_id]
        }
        
        res = requests.patch(url, headers=self.headers, json=payload)
        
        if res.ok:
            logging.info(f"   ✅ Successfully assigned staff.")
        else:
            logging.error(f"   ❌ Failed to update staff: {res.text}")
            return

        # 2. Update Scheduling Policy (Separate Payload)
        logging.info(f"   ⚙️ Updating policy for: {service_name}")
        policy_payload = {
            "schedulingPolicy": {
                "timeSlotInterval": "PT30M",
                "minimumLeadTime": "PT4H",
                "maximumAdvance": "P365D",
                "sendConfirmationsToOwner": True,
                "notifyCustomers": True,
                "allowStaffSelection": False 
            }
        }
        res2 = requests.patch(url, headers=self.headers, json=policy_payload)
        if res2.ok:
             logging.info(f"   ✅ Successfully updated policy.")
        else:
             logging.error(f"   ❌ Failed to update policy: {res2.text}")

    def list_businesses(self):
        """List all booking businesses"""
        logging.info("🔍 Listing Booking Businesses...")
        res = requests.get("https://graph.microsoft.com/v1.0/solutions/bookingBusinesses", headers=self.headers)
        if not res.ok:
            logging.error(f"❌ Failed to list businesses: {res.text}")
            return []
        
        businesses = res.json().get("value", [])
        for b in businesses:
            logging.info(f"   🏢 Found Business: {b.get('displayName')} (ID: {b.get('id')})")
        return businesses

    def publish_page(self):
        """Publish the booking business page"""
        logging.info("🚀 Publishing Booking Page...")
        url = f"{self.base_url}/publish"
        res = requests.post(url, headers=self.headers)
        
        if res.ok:
            logging.info("   ✅ Booking Page Published Successfully!")
        else:
            logging.error(f"   ❌ Failed to publish page: {res.text}")

def run():
    logging.info("--- Starting Bookings Configuration Fix (Backend) ---")
    try:
        configurator = BookingsConfigurator()
    except Exception as e:
        logging.error(f"Failed to initialize Configurator: {e}")
        return

    # 0. List Businesses (DEBUG)
    businesses = configurator.list_businesses()
    
    # 1. Get Peter's ID
    peter_id = configurator.get_staff_param("Peter Teehan")
    if not peter_id:
        return

    # 2. Get All Services
    services = configurator.get_services()
    if not services:
        logging.info("⚠️ No services found to update.")
        return

    # 3. Update Each Service
    for service in services:
        configurator.update_service_staff(service['id'], service['displayName'], peter_id)

    # 4. Publish Page
    configurator.publish_page()
    logging.info("--- Configuration Complete ---")

if __name__ == "__main__":
    run()
