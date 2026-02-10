import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def view_notes():
    ids = ['Ta6b3a320', 'T7f521190', 'Ta9be982d', 'Tb7f5922e', 'T16135281', 'T49928386']
    id_list = ",".join([f"'{i}'" for i in ids])
    query = f"SELECT TripID, Notes FROM Trips WHERE TripID IN ({id_list})"
    results = db.execute_query_with_results(query)
    for r in results:
        print(f"--- {r['TripID']} ---")
        # Strip non-ascii for terminal safety
        safe_notes = "".join([i if ord(i) < 128 else ' ' for i in str(r['Notes'])])
        print(safe_notes)
        print("-" * 30)

if __name__ == "__main__":
    view_notes()
    
    # Also search for "Cave" or "Winds" or "Manitou"
    print("\n--- Searching for Keywords ---")
    query_kw = "SELECT TripID, Notes FROM Trips WHERE Notes LIKE '%Cave%' OR Notes LIKE '%Winds%' OR Notes LIKE '%Manitou%'"
    res_kw = db.execute_query_with_results(query_kw)
    for r in res_kw:
        safe_note = "".join([i if ord(i) < 128 else ' ' for i in str(r['Notes'])])
        print(f"MATCH {r['TripID']}: {safe_note[:500]}")
