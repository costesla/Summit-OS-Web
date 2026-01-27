"""
Quick script to check if the test image made it to Azure and was processed.
"""
import os
import pyodbc
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

print("=" * 60)
print("CHECKING FOR TEST IMAGE IN PIPELINE")
print("=" * 60)

# Check SQL for recent trips (last 30 minutes)
conn_str = os.environ.get("SQL_CONNECTION_STRING")
cutoff_time = datetime.now() - timedelta(minutes=30)

try:
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cur = conn.cursor()
        
        # Get most recent trips
        query = """
        SELECT TOP 5 
            TripID,
            TripType,
            Pickup_Place,
            Dropoff_Place,
            Fare,
            Timestamp_Dropoff
        FROM Trips 
        ORDER BY CreatedAt DESC
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        if rows:
            print("\nMost Recent Trips in Database:")
            print("-" * 60)
            for row in rows:
                print(f"Trip ID: {row[0]}")
                print(f"  Type: {row[1]}")
                print(f"  Route: {row[2]} -> {row[3]}")
                print(f"  Fare: ${row[4] if row[4] else 'N/A'}")
                print(f"  Time: {row[5]}")
                print("-" * 60)
        else:
            print("\nNo trips found in database yet.")
            print("Waiting for first screenshot to be processed...")
            
except Exception as e:
    print(f"Error querying database: {str(e)}")

print("\nTo manually trigger processing of an image:")
print("1. Get the blob URL from Azure Portal")
print("2. Run: python summit_sync/scripts/backfill_http.py")
