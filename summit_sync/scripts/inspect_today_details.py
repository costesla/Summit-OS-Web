
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient
from dotenv import load_dotenv

load_dotenv()
db = DatabaseClient()

query = """
SELECT JobID, TripID, Classification, Passenger_FirstName, Earnings_Driver, Notes
FROM Trips
WHERE CreatedAt > CAST(GETDATE() AS DATE)
ORDER BY CreatedAt DESC
"""

results = db.execute_query_with_results(query)

print(f"Found {len(results)} trips today.\n")
for r in results:
    print(f"ID: {r['TripID']} | Class: {r['Classification']} | Passenger: {r['Passenger_FirstName']} | Earn: {r['Earnings_Driver']}")
    print(f"Notes: {r['Notes']}")
    print("-" * 50)
