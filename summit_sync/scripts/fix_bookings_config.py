import os
import requests
import json
import logging
from lib.bookings import BookingsClient

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BookingsConfigurator(BookingsClient):
    def __init__(self):
        super().__init__()
        self.headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }
        self.base_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{self.business_id}"

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
        
        return res.json().get("value", [])

    def update_service_staff(self, service_id, service_name, staff_id):
        """Assign ONLY specific staff to a service and reset availability"""
        logging.info(f"⚙️ Updating Service: {service_name} ({service_id})")
        
        url = f"{self.base_url}/services/{service_id}"
        
        # 1. Update Staff Assignment
        payload = {
            "staffMemberIds": [staff_id],
            "defaultPriceType": "notSet", # Resetting some defaults to be safe
            "schedulingPolicy": {
                "timeSlotInterval": "PT30M",
                "minimumLeadTime": "PT4H",
                "maximumAdvance": "P365D",
                "sendConfirmationsToOwner": True,
                "notifyCustomers": True,
                "allowStaffSelection": False # Force assignment
            }
        }
        
        res = requests.patch(url, headers=self.headers, json=payload)
        
        if res.ok:
            logging.info(f"   ✅ Successfully assigned staff & updated policy.")
        else:
            logging.error(f"   ❌ Failed to update service: {res.text}")

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
    logging.info("--- Starting Bookings Configuration Fix ---")
    configurator = BookingsConfigurator()
    
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
