import json
import os
import datetime
from zoneinfo import ZoneInfo

def main():
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            for k, v in settings.get('Values', {}).items():
                os.environ[k] = v

        from services.tessie import TessieClient
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")

        print("VIN:", vin)
        
        # May 17th MST to UTC
        day_dt = datetime.datetime.strptime("2026-05-17", "%Y-%m-%d")
        from_dt_utc = day_dt + datetime.timedelta(hours=7)
        to_dt_utc   = day_dt + datetime.timedelta(hours=31)
        from_ts = int(from_dt_utc.timestamp())
        to_ts   = int(to_dt_utc.timestamp())

        print(f"Querying Tessie from {from_dt_utc} ({from_ts}) to {to_dt_utc} ({to_ts})...")
        
        # 1. Fetch drives
        drives = tessie.get_tagged_drives(vin, from_ts, to_ts)
        print(f"\nFound {len(drives)} drives:")
        for idx, d in enumerate(drives, 1):
            print(f"{idx}. ID: {d.get('id') or d.get('drive_id')} | Started: {d.get('started_at')} | Dist: {d.get('odometer_distance')} | Tag: {d.get('tag')}")
            
        # 2. Let's inspect database Rides.Rides mileage for May 17th
        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        print("\n--- Rides.Rides mileage for 2026-05-17 ---")
        cur.execute("SELECT RideID, Distance_mi, Tessie_Distance, Timestamp_Start FROM Rides.Rides WHERE CAST(Timestamp_Start AS DATE) = '2026-05-17' ORDER BY Timestamp_Start")
        for row in cur.fetchall():
            print(row)
        
        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
