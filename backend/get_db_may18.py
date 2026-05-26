import json
import os

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
        
        print("--- Rides.Rides for 2026-05-18 ---")
        cur.execute("SELECT RideID, Distance_mi, Classification, ValidationStatus, Timestamp_Start FROM Rides.Rides WHERE CAST(Timestamp_Start AS DATE) = '2026-05-18' ORDER BY Timestamp_Start")
        rows = cur.fetchall()
        print(f"Total rows: {len(rows)}")
        for r in rows:
            print(r)
            
        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
