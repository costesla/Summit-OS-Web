import logging
import os
import sys
import json
from datetime import date

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def test_view():
    load_dotenv()
    db = DatabaseClient()
    
    print("--- Querying v_DailyKPIs ---")
    try:
        query = "SELECT * FROM v_DailyKPIs"
        results = db.execute_query_with_results(query)
        if results:
            print(json.dumps(results, indent=4, default=str))
        else:
            print("No data found in v_DailyKPIs (or empty result).")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_view()
