import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def check_stamps():
    query = "SELECT TOP 10 TripID, CreatedAt, TripType FROM Trips ORDER BY CreatedAt DESC"
    results = db.execute_query_with_results(query)
    for r in results:
        print(f"ID: {r.get('TripID')} | TS: {r.get('CreatedAt')} | Type: {r.get('TripType')}")

if __name__ == "__main__":
    check_stamps()
