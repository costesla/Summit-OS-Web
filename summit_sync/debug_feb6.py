from lib.database import DatabaseClient
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.ERROR)

db = DatabaseClient()
query = "SELECT TripID, Timestamp_Offer, Distance_mi, Earnings_Driver, Pickup_Place, Dropoff_Place, Classification FROM Trips WHERE Timestamp_Offer >= '2026-02-06' ORDER BY Timestamp_Offer"
results = db.execute_query_with_results(query)

for r in results:
    print(f"[{r['TripID']}] {r['Timestamp_Offer']} | {r['Pickup_Place']} -> {r['Dropoff_Place']} | Dist: {r['Distance_mi']} | Earn: ${r['Earnings_Driver']} | {r['Classification']}")
