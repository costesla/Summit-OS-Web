import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_missing_data_v2():
    # Search for $9.98 or Cave of the Winds or Payment contexts
    query = "SELECT TripID, raw_text, SourceURL, Earnings_Driver, Passenger_FirstName FROM Trips"
    results = db.execute_query_with_results(query)
    
    match_998 = []
    private_pvt = []
    
    for r in results:
        txt = str(r.get('raw_text', '')).lower()
        if '9.98' in txt or 'cave' in txt or 'manitou' in txt:
            match_998.append(r)
        
        # Look for potential Private Trips (Venmo, Payment, etc)
        if 'payment from' in txt or 'venmo' in txt or 'payment to' in txt:
             private_pvt.append(r)

    print(f"--- 9.98 Matches: {len(match_998)} ---")
    for r in match_998:
         print(f"ID: {r['TripID']} | File: {r['SourceURL']}")
         
    print(f"\n--- Potential Private Trips Found: {len(private_pvt)} ---")
    for r in private_pvt:
         print(f"ID: {r['TripID']} | Name: {r['Passenger_FirstName']} | Earn: ${r['Earnings_Driver']} | Snippet: {str(r['raw_text'][:50])}")

if __name__ == "__main__":
    find_missing_data_v2()
