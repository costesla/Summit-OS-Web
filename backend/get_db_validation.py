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
        
        # 1. Columns of dbo.Drive_Telemetry
        print("--- dbo.Drive_Telemetry Columns ---")
        cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Drive_Telemetry'")
        for col in cur.fetchall():
            print(f"- {col[0]} ({col[1]})")
            
        # 2. Query Rides.Rides ValidationStatus for 2026-05-17
        print("\n--- Rides.Rides for 2026-05-17 ---")
        cur.execute("SELECT RideID, Distance_mi, Classification, ValidationStatus, Timestamp_Start FROM Rides.Rides WHERE CAST(Timestamp_Start AS DATE) = '2026-05-17'")
        for r in cur.fetchall():
            print(r)
            
        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
