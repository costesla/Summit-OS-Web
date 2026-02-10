import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def check_ocr_by_id(ids):
    for tid in ids:
        query = f"SELECT TripID, raw_text FROM Trips WHERE TripID = '{tid}'"
        results = db.execute_query_with_results(query)
        if results:
            print(f"\n--- {tid} RAW TEXT ---")
            print(results[0]['raw_text'])

if __name__ == "__main__":
    check_ocr_by_id(['T485345c2', 'T17b3262a', 'T91767da0'])
