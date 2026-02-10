
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient
from dotenv import load_dotenv

load_dotenv()

db = DatabaseClient()
query = "SELECT GETDATE() as DB_Local, GETUTCDATE() as DB_UTC"

try:
    results = db.execute_query_with_results(query)
    print("--- DB Time Check ---")
    for r in results:
        print(r)
except Exception as e:
    print(f"Query 1 Failed: {e}")

print("\n--- DailyKPIs Check ---")
# Check what dates are available in the view
query_view = "SELECT TOP 5 [Date] FROM v_DailyKPIs ORDER BY [Date] DESC"
results_view = db.execute_query_with_results(query_view)
for r in results_view:
    print(r)
