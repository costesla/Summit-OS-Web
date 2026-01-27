
import os
import sys
import pyodbc
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()

def view_latest_trip():
    db = DatabaseClient()
    conn = db.get_connection()
    
    if not conn:
        print("Failed to connect to database.")
        return

    # Query specifically for the trip we just inserted or the latest ones
    query = """
    SELECT TOP 1
        TripID, 
        Format(Timestamp_Offer, 'yyyy-MM-dd HH:mm') as Time,
        Pickup_Place, 
        Dropoff_Place, 
        Payment_Method,
        Rider_Payment as Amount,
        Classification,
        Tessie_DriveID,
        Uber_Distance
    FROM Trips
    ORDER BY LastUpdated DESC
    """
    
    try:
        df = pd.read_sql(query, conn)
        if not df.empty:
            print("\nVerification - Latest Trip in DB:")
            print(df.to_string(index=False))
        else:
            print("No trips found.")
    except Exception as e:
        print(f"Error viewing data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    view_latest_trip()
