import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def search_notes():
    # Searching for Omar or any Private potential
    query = "SELECT TripID, Notes, Passenger_FirstName, Earnings_Driver FROM Trips WHERE Notes LIKE '%Omar%' OR Passenger_FirstName LIKE '%Omar%'"
    results = db.execute_query_with_results(query)
    print(f"--- Omar Matches: {len(results)} ---")
    for r in results:
        print(f"ID: {r['TripID']} | Name: {r['Passenger_FirstName']} | Earn: {r['Earnings_Driver']}")
        print(f"Notes Snippet: {repr(r['Notes'][:500])}")
        print("-" * 20)

if __name__ == "__main__":
    search_notes()
