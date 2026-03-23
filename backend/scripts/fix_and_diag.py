import os
import requests
import json
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
load_dotenv(env_path)

def fix_and_diag():
    tenant_id = os.environ.get("OAUTH_TENANT_ID")
    client_id = os.environ.get("OAUTH_CLIENT_ID")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    business_id = os.environ.get("MS_BOOKINGS_BUSINESS_ID", "SummitOS@costesla.com")

    # Get Token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    resp = requests.post(token_url, data=token_data)
    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("=== BOOKINGS TIMEZONE CHECK ===")
    st_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers"
    staffs = requests.get(st_url, headers=headers).json().get("value", [])
    peter = next((s for s in staffs if "peter" in s.get("emailAddress", "").lower()), None)
    
    if peter:
        staff_id = peter["id"]
        print(f"Peter's Timezone: {peter.get('timeZone')}")

        # Let's forcefully reset Peter's working hours to a strictly valid format:
        # Every day 00:00 to 24:00 is acceptable in some systems, or 00:00 to 23:59.
        # But wait, earlier 23:30 failed?! Maybe there was a duplicate day.
        # Let's just give him a fresh array.
        fresh_hours = []
        days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        for day in days:
            fresh_hours.append({
                "day": day,
                "timeSlots": [
                    {
                        "startTime": "00:00:00.0000000",
                        "endTime": "24:00:00.0000000" 
                    }
                ]
            })

        print("\nPatching Peter's Working Hours to fresh 24/7...")
        staff_update_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/staffMembers/{staff_id}"
        staff_resp = requests.patch(staff_update_url, headers=headers, json={"workingHours": fresh_hours, "useBusinessHours": False})
        
        if staff_resp.ok:
            print("SUCCESS: Staff hours fully reset to 24/7.")
        else:
            print(f"FAILED Staff patch with 24:00: {staff_resp.text}")
            # Try fallback 06:00 to 23:00
            fallback_hours = []
            for day in days:
                fallback_hours.append({
                    "day": day,
                    "timeSlots": [
                        {
                            "startTime": "06:00:00.0000000",
                            "endTime": "23:00:00.0000000" 
                        }
                    ]
                })
            f_resp = requests.patch(staff_update_url, headers=headers, json={"workingHours": fallback_hours, "useBusinessHours": False})
            print(f"Fallback Patch Result: {f_resp.status_code}")
    else:
        print("Peter not found.")

    # 4. Use Bookings Availability API using Windows time zone
    print("\n[BOOKINGS ENGINE AVAILABILITY TEST: Mountain Standard Time]")
    av_url = f"https://graph.microsoft.com/v1.0/solutions/bookingBusinesses/{business_id}/getStaffAvailability"
    av_payload = {
        "staffIds": [peter['id']],
        "startDateTime": {
            "dateTime": "2026-02-20T00:00:00.0000000",
            "timeZone": "Mountain Standard Time"
        },
        "endDateTime": {
            "dateTime": "2026-02-20T23:59:00.0000000",
            "timeZone": "Mountain Standard Time"
        }
    }
    av_resp = requests.post(av_url, headers=headers, json=av_payload)
    if av_resp.ok:
        av_data = av_resp.json().get("value", [])
        for staff_av in av_data:
             print(f"Availability Items for Staff:")
             for slot in staff_av.get("availabilityItems", []):
                 print(f"  Status: {slot.get('status')} | {slot.get('startDateTime', {}).get('dateTime')} -> {slot.get('endDateTime', {}).get('dateTime')}")
    else:
        print(f"Failed to get availability: {av_resp.text}")

if __name__ == "__main__":
    fix_and_diag()
