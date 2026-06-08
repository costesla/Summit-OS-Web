import os
import pyodbc
import datetime
from dotenv import load_dotenv

# Set paths
sys_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
import sys
if sys_path not in sys.path:
    sys.path.append(sys_path)

load_dotenv(os.path.join(sys_path, '.env'))

from lib.database import DatabaseClient

def run_health_check():
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        print("[FAIL] Could not connect to SQL Database.")
        return
        
    cursor = conn.cursor()
    print("==================================================")
    print("        SUMMITOS DATABASE HEALTH AUDIT")
    print("==================================================")
    
    # 1. Check schema counts
    cursor.execute("SELECT COUNT(*) FROM Trips")
    trips_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM Rides.Rides")
    rides_count = cursor.fetchone()[0]
    
    print(f"\n[INFO] Total legacy Trips: {trips_count}")
    print(f"[INFO] Total Rides.Rides rows: {rides_count}")
    
    # 2. Check the last 7 days of Rides.Rides activity
    print("\n--- Last 7 Days Activities (Rides.Rides) ---")
    query = """
    SELECT 
        CAST(Timestamp_Start AS DATE) as [Date],
        COUNT(*) as TotalRows,
        SUM(CASE WHEN RideID LIKE 'TRIP-%' THEN 1 ELSE 0 END) as TripCount,
        SUM(CASE WHEN RideID LIKE 'TESSIE-%' THEN 1 ELSE 0 END) as TessieDrives,
        SUM(CASE WHEN RideID LIKE 'INV-%' THEN 1 ELSE 0 END) as PrivateBookings
    FROM Rides.Rides
    WHERE Timestamp_Start >= DATEADD(day, -7, GETDATE())
    GROUP BY CAST(Timestamp_Start AS DATE)
    ORDER BY [Date] DESC
    """
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    
    if not rows:
        print("[WARN] No database activity recorded in the last 7 days.")
    else:
        for r in rows:
            data = dict(zip(columns, r))
            print(f"Date: {data['Date']} | Trips: {data['TripCount']} | Tessie: {data['TessieDrives']} | Bookings: {data['PrivateBookings']} | Total rows: {data['TotalRows']}")
            
    # 3. Check for active/sleeping Tesla live connection
    try:
        from lib.tessie import TessieClient
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if vin:
            status = tessie.get_vehicle_state(vin)
            if status:
                charging_state = status.get("charge_state", {}).get("charging_state", "Unknown")
                battery = status.get("charge_state", {}).get("battery_level", 0)
                print(f"\n[PASS] Tesla Live Status: Connected (Battery: {battery}%, Charging: {charging_state})")
            else:
                print("\n[WARN] Tesla vehicle unreachable or asleep.")
        else:
            print("\n[WARN] TESSIE_VIN environment variable not set.")
    except Exception as e:
        print(f"\n[FAIL] Tesla live check failed: {e}")
        
    print("\n==================================================")
    print("Health check completed.")
    conn.close()

if __name__ == "__main__":
    run_health_check()
