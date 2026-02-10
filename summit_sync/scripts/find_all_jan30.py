import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_all_private():
    # Look for anything not classified as Uber_Core
    query = "SELECT TripID, Classification, Passenger_FirstName, Earnings_Driver, Notes FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'"
    results = db.execute_query_with_results(query)
    
    print(f"--- All Jan 30/31 Entries ({len(results)}) ---")
    for r in results:
        is_uber = r['Classification'] == 'Uber_Core'
        status = "[UBER]" if is_uber else "[PVT ]"
        print(f"{status} ID: {r['TripID']} | Name: {r['Passenger_FirstName']} | Earn: ${r['Earnings_Driver']:.2f}")

if __name__ == "__main__":
    find_all_private()
