import json
import os
import datetime

def main():
    try:
        settings_path = 'local.settings.json'
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                for k, v in settings.get('Values', {}).items():
                    os.environ[k] = v

        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        
        print("Querying Rides.Rides for 2026-05-22...")
        cur.execute("""
            SELECT RideID, TripType, Classification, Distance_mi, Duration_min, 
                   Timestamp_Start, Pickup_Location, Dropoff_Location, Driver_Earnings, Fare, Tip
            FROM Rides.Rides 
            WHERE CAST(Timestamp_Start AS DATE) = '2026-05-22' OR RideID LIKE 'TRIP-20260522-%'
            ORDER BY Timestamp_Start, RideID
        """)
        rows = cur.fetchall()
        print(f"Found {len(rows)} rides in database:")
        for r in rows:
            print(f"RideID: {r[0]} | TripType: {r[1]} | Class: {r[2]} | Dist: {r[3]} | Start: {r[5]} | Earn: {r[8]} | Fare: {r[9]} | Tip: {r[10]}")
            
        cur.close()
        conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
