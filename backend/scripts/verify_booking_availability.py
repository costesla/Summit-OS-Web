import requests
import json
import datetime

# Test for tomorrow
tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
URL = f"https://www.costesla.com/api/calendar-availability?date={tomorrow}"

print(f"Testing Booking Availability: {URL}")

try:
    response = requests.get(URL, timeout=20)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        # print(json.dumps(data, indent=2)) 
        
        if data.get("success"):
            slots = data.get("slots", [])
            print(f"SUCCESS: Booking Engine Verified. Found {len(slots)} available slots for {tomorrow}.")
            if slots:
                print(f"First slot: {slots[0]['start']} - {slots[0]['end']}")
        else:
            print("FAILED: Engine returned success: False")
            print(data)
    else:
        print(f"FAILED: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"ERROR: {e}")
