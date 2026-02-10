import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_missing_data():
    # Search for $9.98 or Cave of the Winds
    query = "SELECT TripID, Raw_Text, SourceURL FROM Trips WHERE Raw_Text LIKE '%9.98%' OR Raw_Text LIKE '%Cave%'"
    results = db.execute_query_with_results(query)
    print(f"Searching for 9.98/Cave... Found {len(results)} records.")
    for r in results:
        print(f"ID: {r['TripID']} | Text: {str(r['Raw_Text'])[:100]} | File: {r['SourceURL']}")

if __name__ == "__main__":
    find_missing_data()
