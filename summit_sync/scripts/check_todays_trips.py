
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient
from dotenv import load_dotenv

load_dotenv()

db = DatabaseClient()
# Query for trips where the offer/created timestamp matches today in MST
query = """
SELECT 
    TripID, 
    TripType, 
    Classification, 
    Rider_Payment, 
    Earnings_Driver, 
    Passenger_FirstName,
    Timestamp_Offer,
    SourceURL,
    Notes
FROM Trips 
WHERE CAST(Timestamp_Offer AT TIME ZONE 'Mountain Standard Time' AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time' AS DATE)
   OR CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time' AS DATE)
ORDER BY Timestamp_Offer DESC
"""

print("--- Checking Today's Trips (MST) ---")
try:
    results = db.execute_query_with_results(query)
    print(f"Total Trips Found Today: {len(results)}")
    
    uber_trips = [r for r in results if r['TripType'] == 'Uber']
    private_trips = [r for r in results if r['TripType'] == 'Private']
    
    print(f"Uber Trips: {len(uber_trips)}")
    for r in uber_trips:
        print(f"  - {r['Classification']} (${r['Earnings_Driver']}) via {r.get('SourceURL', 'Unknown').split('/')[-1]}")

    print(f"Private Trips: {len(private_trips)}")
    for r in private_trips:
         print(f"  - {r['Classification']} (${r['Earnings_Driver']}) | Pass: {r['Passenger_FirstName']}")

except Exception as e:
    print(f"Error: {e}")
