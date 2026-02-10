
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient
from dotenv import load_dotenv

load_dotenv()
db = DatabaseClient()

query = """
SELECT TOP 20 TripID, TripType, Classification, Earnings_Driver, Passenger_FirstName, CreatedAt, SourceURL
FROM Trips
ORDER BY CreatedAt DESC
"""

results = db.execute_query_with_results(query)

with open("recent_trips_dump.txt", "w") as f:
    f.write(f"Count: {len(results)}\n")
    for r in results:
        f.write(str(r) + "\n")
