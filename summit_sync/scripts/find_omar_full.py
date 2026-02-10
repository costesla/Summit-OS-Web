import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_omar_details():
    query = "SELECT TripID, Notes, raw_text FROM Trips WHERE Notes LIKE '%Omar%' OR raw_text LIKE '%Omar%'"
    results = db.execute_query_with_results(query)
    for r in results:
        print(f"ID: {r['TripID']}")
        print(f"Notes: {r['Notes']}")
        print(f"Raw: {r['raw_text']}")
        print("-" * 20)

if __name__ == "__main__":
    find_omar_details()
