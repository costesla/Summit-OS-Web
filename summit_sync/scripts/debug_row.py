import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def debug_one_row():
    query = "SELECT TOP 1 * FROM Trips"
    results = db.execute_query_with_results(query)
    if results:
        print(results[0].keys())
        for k, v in results[0].items():
            print(f"{k}: {type(v)}")

if __name__ == "__main__":
    debug_one_row()
