
import os
import sys
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def correct_trip():
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found.")
        return

    trip_id = "TESSIE-360556521"
    
    print(f"Correcting data for trip {trip_id}...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # 1. Update query to clear Uber fields and ensure Private fields are set
        # We want Uber_Distance/Uber_Duration to be NULL implies it's not from Uber OCR
        # We want TripType = 'Private'
        
        query = """
        UPDATE Trips 
        SET 
            TripType = 'Private',
            Classification = 'Private_Trip',
            Uber_Distance = NULL,
            Uber_Duration = NULL,
            Tessie_Distance = Distance_mi, -- Ensure these match the source of truth
            Tessie_Duration = Duration_min
        WHERE TripID = ?
        """
        
        cursor.execute(query, (trip_id,))
        conn.commit()
        
        print(f"Trip {trip_id} corrected:")
        print("   - TripType set to 'Private'")
        print("   - Uber_Distance/Duration cleared (NULL)")
        print("   - Tessie_Distance/Duration synced")
        
    except Exception as e:
        print(f"Failed to correct trip: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    correct_trip()
