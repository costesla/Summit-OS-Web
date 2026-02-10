import os
import datetime
from lib.database import DatabaseClient
from dotenv import load_dotenv

def verify_data():
    load_dotenv()
    db = DatabaseClient()
    
    # Query for trips with Timestamp_Offer on Feb 6, 2026
    query = """
    SELECT COUNT(*) as TripCount, SUM(Rider_Payment) as TotalPayment, SUM(Earnings_Driver) as TotalEarnings
    FROM Trips 
    WHERE Timestamp_Offer >= '2026-02-06 00:00:00' AND Timestamp_Offer < '2026-02-07 00:00:00'
    """
    
    print("--- Verifying Feb 6 Data ---")
    results = db.execute_query_with_results(query)
    
    if results:
        row = results[0]
        print(f"Trips Found: {row.get('TripCount')}")
        print(f"Total Rider Payment: {row.get('TotalPayment')}")
        print(f"Total Driver Earnings: {row.get('TotalEarnings')}")
    else:
        print("No data returned.")

    # Also check via CreatedAt for debugging
    query_created = """
    SELECT COUNT(*) as CountStart
    FROM Trips
    WHERE CreatedAt >= DATEADD(hour, -1, GETDATE())
    """
    results_created = db.execute_query_with_results(query_created)
    if results_created:
        print(f"Trips Created/Updated in last hour: {results_created[0].get('CountStart')}")

if __name__ == "__main__":
    verify_data()
