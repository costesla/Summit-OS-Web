import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_omar():
    query = "SELECT TripID, Notes FROM Trips WHERE Notes LIKE '%Omar%'"
    results = db.execute_query_with_results(query)
    for r in results:
        print(f"ID: {r['TripID']} | Notes: {r['Notes'][:100]}")

if __name__ == "__main__":
    find_omar()
