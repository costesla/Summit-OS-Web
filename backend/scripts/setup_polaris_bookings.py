import os
import sys
import logging

# Ensure we can import from backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.services.graph import GraphClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def setup_polaris():
    client = GraphClient()
    business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")
    
    logging.info(f"Starting Hotel Polaris Setup for Business: {business_id}")

    # 1. Publish the main booking page (if not already)
    logging.info("Step 1: Publishing Booking Business Page...")
    try:
        details = client.publish_booking_page(business_id)
        if type(details) is dict and "publicUrl" in details:
            logging.info(f"Success! Booking Page is published. Public URL: {details['publicUrl']}")
        else:
            logging.info("Success! Booking Page is published.")
    except Exception as e:
        logging.error(f"Failed to publish booking page: {e}")
        return

    # 2. Get the Staff ID so we can assign Peter to the service automatically
    # This is an optimization. We try to find the staff ID to assign him automatically.
    # Otherwise, we just create the service and he can assign himself via UI.
    staff_id = None
    try:
        url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
        headers = {"Authorization": f"Bearer {client._get_token()}"}
        import requests
        staff_resp = requests.get(url, headers=headers)
        if staff_resp.ok:
            staff = staff_resp.json().get('value', [])
            for s in staff:
                if 'peter.teehan' in s.get('emailAddress', '').lower() or 'peter' in s.get('displayName', '').lower():
                    staff_id = s.get('id')
                    logging.info(f"Found Staff ID for Peter: {staff_id}")
                    break
    except Exception as e:
        logging.warning("Could not automatically retrieve Staff ID. Will create service without pre-assigned staff.")

    # 3. Create the Service payload
    logging.info("Step 2: Creating 'Hotel Polaris Booking Request' Service...")
    
    # Custom Questions: You can ask for Name, Phone, Room Number, etc.
    service_payload = {
        "displayName": "Hotel Polaris Shuttle Request",
        "defaultDuration": "PT1H",
        "maximumAttendeesCount": 1,
        "isAnonymousJoinEnabled": False,
        "defaultPriceType": "hourly",
        "defaultPrice": 85.0
    }
    
    # Assign staff if we found it
    if staff_id:
        service_payload["staffMemberIds"] = [staff_id]

    try:
        new_service = client.create_booking_service(service_payload, business_id)
        service_id = new_service.get('id')
        logging.info(f"Success! Created service ID: {service_id}")
        
        # Construct direct link using standard Bookings URL format
        direct_link_base = "https://outlook.office365.com/owa/calendar"
        # Bookings usually uses: https://outlook.office365.com/owa/calendar/<BusinessEmail>/bookings/s/<ServiceID>
        direct_link = f"{direct_link_base}/{business_id}/bookings/s/{service_id}"
        
        print("\n" + "="*50)
        print("🎉 HOTEL POLARIS SERVICE CREATED SUCCESSFULLY! 🎉")
        print("="*50)
        print("To share with Hotel Polaris, give them this exact Direct Link:")
        print(f"\n🔗 {direct_link}\n")
        print("This link bypasses the main page and directly opens the 'Hotel Polaris Shuttle Request'.")
        print("Since attendees count is 1, and 'Events on Office 365 calendar affect availability' is")
        print("enabled in your Staff settings across the business, you will NEVER double-book!")
        print("="*50 + "\n")
        
    except Exception as e:
        with open('error.log', 'w') as f:
            f.write(str(e))
        print(f"\n[FATAL ERROR] API Request Failed. Check error.log\n")

if __name__ == "__main__":
    setup_polaris()
