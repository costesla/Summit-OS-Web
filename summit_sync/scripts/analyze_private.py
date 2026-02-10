import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def analyze_private():
    query = "SELECT TripID, Classification, Passenger_FirstName, Earnings_Driver, Notes, SourceURL FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'"
    results = db.execute_query_with_results(query)
    
    print("--- Detailed Private Trip Audit ---")
    for r in results:
        if r['TripType' if 'TripType' in r else 'Classification'] != 'Uber':
            notes = str(r.get('Notes', ''))
            print(f"ID: {r['TripID']} | Name: {r['Passenger_FirstName']} | Earn: ${r['Earnings_Driver']:.2f} | Notes: {notes[:60]}")

if __name__ == "__main__":
    # Note: Adding TripType to query if it's there
    query = "SELECT TripID, TripType, Passenger_FirstName, Earnings_Driver, Notes FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'"
    results = db.execute_query_with_results(query)
    for r in results:
        if r['TripType'] != 'Uber':
             print(f"ID: {r['TripID']} | Name: {r['Passenger_FirstName']} | Earn: ${r['Earnings_Driver']} | Notes: {str(r['Notes'])[:50]}")
