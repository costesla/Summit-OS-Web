import os
import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
logging.basicConfig(level=logging.INFO)

def check_history():
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        print("Failed to connect to DB")
        return

    # Calculate "Yesterday" (User is in UTC-7, so we should be careful with timezones, 
    # but for a broad check, we'll just check the last 48 hours to be safe)
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    print(f"--- Checking Activity for ~{date_str} ---")

    cursor = conn.cursor()

    # 1. Check Trips
    # We check CreatedAt (ingestion time) AND Timestamp_Offer (trip time)
    query_trips = """
    SELECT TripID, TripType, Classification, Timestamp_Offer, Fare, Earnings_Driver, CreatedAt
    FROM Trips 
    WHERE CAST(CreatedAt AS DATE) = ? OR CAST(Timestamp_Offer AS DATE) = ?
    ORDER BY Timestamp_Offer DESC
    """
    
    try:
        cursor.execute(query_trips, (date_str, date_str))
        rows = cursor.fetchall()
        
        print(f"\n[TRIPS] Found {len(rows)} records:")
        for row in rows:
            # removing 'Total' or 'Offer' to keep it clean
            t_id, t_type, cls, t_time, fare, earn, created = row
            print(f" - {t_time} | {t_type} ({cls}) | Earn: ${earn} | ID: {t_id}")
            
    except Exception as e:
        print(f"Error querying trips: {e}")

    # 2. Check Charging
    query_charge = """
    SELECT SessionID, Start_Time, Energy_Added_kWh, Cost, Location_Name
    FROM ChargingSessions
    WHERE CAST(Start_Time AS DATE) = ?
    ORDER BY Start_Time DESC
    """
    
    try:
        cursor.execute(query_charge, (date_str,))
        rows = cursor.fetchall()
        
        print(f"\n[CHARGING] Found {len(rows)} sessions:")
        for row in rows:
            s_id, start, energy, cost, loc = row
            print(f" - {start} | {energy} kWh | ${cost} | {loc}")

    except Exception as e:
        print(f"Error querying charging: {e}")
        
    conn.close()

if __name__ == "__main__":
    check_history()
