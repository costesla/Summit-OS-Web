import json
import os
import datetime

def main():
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            for k, v in settings.get('Values', {}).items():
                os.environ[k] = v

        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        
        # Let's fetch the same rides
        cur.execute("""
            SELECT Timestamp_Start, Driver_Earnings, RideID
            FROM Rides.Rides
            WHERE Driver_Earnings > 0
              AND Timestamp_Start IS NOT NULL
        """)
        earned_rides = [(row[0], float(row[1]), row[2]) for row in cur.fetchall()]
        cur.close()
        conn.close()

        print(f"Total earned rides fetched: {len(earned_rides)}")
        
        # Let's mock a drive from May 18th: e.g. 2026-05-18 20:42 MST (Row 14 in screen)
        drive_date = "2026-05-18"
        drive_time = "20:42"
        drive_dt = datetime.datetime.strptime(f"{drive_date}T{drive_time}:00", "%Y-%m-%dT%H:%M:%S")
        
        matches = []
        for ride_ts, earnings, ride_id in earned_rides:
            diff = abs((ride_ts - drive_dt).total_seconds())
            if diff <= 14400:
                matches.append((ride_ts, earnings, ride_id, diff))
                
        print(f"\nMatches for drive at {drive_dt}:")
        for m in matches:
            print(m)

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
