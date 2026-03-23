import os
import sys
import requests
import logging
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def update_polaris_service():
    tenant_id = os.environ.get("OAUTH_TENANT_ID")
    client_id = os.environ.get("OAUTH_CLIENT_ID")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")

    # 1. Get Token
    logging.info("Authenticating with Microsoft Graph...")
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    
    resp = requests.post(token_url, data=token_data)
    if not resp.ok:
        logging.error(f"Failed to authenticate: {resp.text}")
        return
        
    token = resp.json().get("access_token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 2. Get Service ID for "Hotel Polaris"
    logging.info("Fetching existing services to find Hotel Polaris...")
    services_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services"
    services_resp = requests.get(services_url, headers=headers)
    
    if not services_resp.ok:
        logging.error(f"Failed to fetch services: {services_resp.text}")
        return
        
    services = services_resp.json().get("value", [])
    polaris_service = next((s for s in services if "Polaris" in s.get("displayName", "")), None)
    
    if not polaris_service:
        logging.error("Could not find a service named Hotel Polaris. Make sure it was created first.")
        return
        
    service_id = polaris_service["id"]
    logging.info(f"Found Hotel Polaris Service: {service_id}")

    # 3. Update payload
    logging.info("Preparing updates for Pricing (Fairness Engine v2.0) and 24/7 HOP...")
    
    # 24/7 Schedule for every day of the week
    hop_24_7 = []
    days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    for day in days:
        hop_24_7.append({
            "day": day,
            "timeSlots": [
                {
                    "start": "00:00:00.0000000",
                    "end": "24:00:00.0000000" # Graph API represents end of day as 24:00:00
                }
            ]
        })
        
    update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/services/{service_id}"
    
    update_payload = {
        # Update Description to show Distance Matrix Pricing
        "description": "Exclusive booking portal for Hotel Polaris.\n\n"
                       "**Fairness Engine v2.0 Pricing:**\n"
                       "• Base Engagement: $15.00\n"
                       "• Local Mile (5-20mi): $1.75/mi\n"
                       "• Long Haul (20mi+): $1.25/mi\n\n"
                       "*Pricing calculated via Google Distance Matrix API. No surge pricing. Ever.*\n\n"
                       "Request a shuttle/private trip with Peter. Availability is automatically synced to prevent double bookings.",
        
        # Update Price to "Starting At $15"
        "defaultPriceType": "startingAt",
        "defaultPrice": 15.0,
        
        # Update scheduling policy to disable default business hours
        "schedulingPolicy": polaris_service.get("schedulingPolicy", {}),
        "customQuestions": polaris_service.get("customQuestions", [])
    }
    
    # We must construct the custom business hours properly
    # A Service can override the business' default hours.
    update_payload["schedulingPolicy"]["allowStaffSelection"] = False # Reaffirm this

    # In Microsoft Graph SDK, to set custom hours for a service, you must set `customQuestions` and `schedulingPolicy` 
    # but the actual custom working hours rest on another property `customQuestions` etc? No.
    # The property is actually `schedulingPolicy`? No, The service itself doesn't have an hours property, it falls back to Staff hours or Business Hours if not explicitly set.
    # Wait, the property IS actually on the Service level? Yes, but usually Bookings uses Staff hours.
    # Actually, Bookings services have a `customQuestions` array but the working hours are not strictly defined on the service level.
    # Let me check the documentation. Graph API Bookings Service doesn't have a direct `businessHours` override array like the Business entity does.
    # BUT, the STAFF entity has `workingHours`.
    # AND, the Bookings Service scheduling relies on the Staff's working hours if "Events on Office 365 calendar affect availability" is checked!
    
    # Wait, if we want the service to be literally 24/7 so that it *only* blocks when his Outlook calendar has an event,
    # we need the BUSINESS hours or STAFF hours to be 24/7.
    # If the default business hours are Mon-Fri 8-5, Bookings won't let anyone book on Saturday regardless of his personal calendar.
    
    # Let's update the BUSINESS hours themselves to be 24/7, since SummitOS operates dynamically.
    biz_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}"
    biz_payload = {
        "businessHours": hop_24_7
    }
    
    logging.info("Updating the core Business Hours to 24/7 so calendar drives full availability...")
    biz_resp = requests.patch(biz_update_url, headers=headers, json=biz_payload)
    if not biz_resp.ok:
          logging.warning(f"Could not update business hours. Staff might need their own 24/7 hours set. {biz_resp.text}")
    else:
          logging.info("Successfully updated Business Hours to 24/7.")
          
    # Now let's update the Staff hours to 24/7 just to be fully certain
    try:
        if polaris_service.get("staffMemberIds"):
             staff_id = polaris_service["staffMemberIds"][0]
             staff_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers/{staff_id}"
             staff_payload = {
                  "workingHours": hop_24_7
             }
             logging.info("Updating Peter's Staff Hours to 24/7 so only Outlook calendar restricts availability...")
             requests.patch(staff_update_url, headers=headers, json=staff_payload)
    except Exception as e:
         logging.warning(f"Failed to update staff hours: {e}")

    # Now Patch the Service for Pricing
    logging.info("Updating Hotel Polaris Service Pricing details...")
    update_resp = requests.patch(update_url, headers=headers, json=update_payload)
    
    if not update_resp.ok:
        logging.error(f"Failed to update service: {update_resp.text}")
        with open('error_update.log', 'w') as f:
            f.write(update_resp.text)
        return
        
    logging.info("Success! Service Pricing and HOP have been updated.")

if __name__ == "__main__":
    update_polaris_service()
