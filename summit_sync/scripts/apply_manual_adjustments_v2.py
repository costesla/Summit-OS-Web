import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def update_private_earnings_verbose():
    # Attempt to find the trips first to see why they aren't matching
    print("Searching for trips to adjust...")
    query_search = "SELECT TripID, Passenger_FirstName, Notes, CreatedAt FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'"
    results = db.execute_query_with_results(query_search)
    
    milda_ids = []
    jackie_ids = []
    
    for r in results:
        notes = str(r.get('Notes', '')).lower()
        name = str(r.get('Passenger_FirstName', '')).lower()
        
        if 'esmeralda' in notes or 'esmeralda' in name or 'milda' in notes:
            milda_ids.append(r['TripID'])
        if 'jackie' in notes or 'jacuelyn' in notes or 'jackie' in name or 'jacuelyn' in name:
            jackie_ids.append(r['TripID'])

    print(f"Found Milda IDs: {milda_ids}")
    print(f"Found Jackie IDs: {jackie_ids}")

    if milda_ids:
        print(f"Updating Milda trips: {milda_ids}")
        for tid in milda_ids:
            db.execute_non_query("UPDATE Trips SET Earnings_Driver = 24.00, Rider_Payment = 24.00, TripType = 'Private' WHERE TripID = ?", (tid,))
            
    if jackie_ids:
        print(f"Updating Jackie trips: {jackie_ids}")
        for tid in jackie_ids:
            db.execute_non_query("UPDATE Trips SET Rider_Payment = 70.00, Earnings_Driver = 68.57, Uber_ServiceFee = 1.43, TripType = 'Private' WHERE TripID = ?", (tid,))

    if not milda_ids and not jackie_ids:
        print("No specific names found. Searching for generic 'Private_Trip' entries for today to assign...")
        # Fallback: If no names found, looking for the most recent private entries
        query_fallback = "SELECT TripID FROM Trips WHERE TripType = 'Private' AND Earnings_Driver = 0 AND CAST(CreatedAt AS DATE) >= '2026-01-30'"
        fallback_results = db.execute_query_with_results(query_fallback)
        print(f"Found {len(fallback_results)} unpriced private trips.")

if __name__ == "__main__":
    update_private_earnings_verbose()
