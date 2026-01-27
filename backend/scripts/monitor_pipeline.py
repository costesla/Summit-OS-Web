"""
Monitor for new images appearing in the pipeline.
Polls every 10 seconds for 2 minutes.
"""
import time
import os
import pyodbc
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

print("=" * 60)
print("MONITORING PIPELINE FOR TEST IMAGE")
print("=" * 60)
print(f"Started at: {datetime.now().strftime('%I:%M:%S %p')}")
print("Checking every 10 seconds for 2 minutes...")
print()

conn_str = os.environ.get("SQL_CONNECTION_STRING")

for i in range(12):  # 12 checks = 2 minutes
    try:
        with pyodbc.connect(conn_str, timeout=5) as conn:
            cur = conn.cursor()
            
            # Count total trips
            cur.execute("SELECT COUNT(*) FROM Trips")
            count = cur.fetchone()[0]
            
            # Get most recent trip if any
            cur.execute("""
                SELECT TOP 1 
                    TripID, 
                    TripType, 
                    Pickup_Place,
                    CreatedAt
                FROM Trips 
                ORDER BY CreatedAt DESC
            """)
            
            latest = cur.fetchone()
            
            print(f"[{i+1}/12] {datetime.now().strftime('%I:%M:%S %p')} - Total trips: {count}", end="")
            
            if latest and count > 0:
                print(f" | Latest: {latest[0]} ({latest[1]}) at {latest[3]}")
                if i > 0:  # If this is a new trip since we started
                    print("\n" + "=" * 60)
                    print("NEW TRIP DETECTED!")
                    print("=" * 60)
                    print(f"Trip ID: {latest[0]}")
                    print(f"Type: {latest[1]}")
                    print(f"Location: {latest[2]}")
                    print(f"Processed at: {latest[3]}")
                    print("\nPipeline is WORKING! Test successful!")
                    break
            else:
                print(" | No trips yet")
            
    except Exception as e:
        print(f"[{i+1}/12] Error: {str(e)[:50]}")
    
    if i < 11:  # Don't sleep on last iteration
        time.sleep(10)

print("\nMonitoring complete.")
