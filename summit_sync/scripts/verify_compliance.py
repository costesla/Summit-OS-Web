import logging
import os
import sys
import time

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def verify_compliance():
    load_dotenv()
    db = DatabaseClient()
    
    unique_id = f"TEST_AUDIT_{int(time.time())}"
    
    print(f"Inserting Test Trip: {unique_id}")
    
    # Simulate a Private Trip payload that function_app would save
    test_trip = {
        "trip_id": unique_id,
        "classification": "Private_Booking",
        "start_location": "Airport",
        "end_location": "Hotel",
        "fare": 50.00,
        "timestamp_epoch": time.time(),
        
        # New Compliance Fields explicitly
        "is_cdot_reportable": True,
        "passenger_firstname": "Auditor",
        "pickup_address_full": "123 Test Runway, Denver, CO",
        "dropoff_address_full": "456 Compliance St, Colorado Springs, CO",
        "tessie_distance_mi": 45.5
    }
    
    try:
        db.save_trip(test_trip)
        print("Trip saved. Querying Verification...")
        
        # Verify
        query = f"SELECT Is_CDOT_Reportable, Passenger_FirstName, Pickup_Address_Full FROM Trips WHERE TripID = '{unique_id}'"
        result = db.execute_query_with_results(query)
        
        if result:
            row = result[0]
            print(f"Result: {row}")
            if row['Is_CDOT_Reportable']:
                print("SUCCESS: Is_CDOT_Reportable is TRUE")
            else:
                print("FAILURE: Is_CDOT_Reportable is FALSE")
                
            if row['Passenger_FirstName'] == "Auditor":
                print("SUCCESS: Passenger_FirstName matched")
        else:
            print("FAILURE: Trip not found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_compliance()
