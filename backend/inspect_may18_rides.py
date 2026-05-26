import json
import os
import datetime

def main():
    try:
        # Load local settings for DB connection
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
        
        cur.execute("""
            SELECT RideID, TripType, Classification, Distance_mi, Duration_min, 
                   Tessie_DriveID, Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi, Timestamp_Start
            FROM Rides.Rides 
            WHERE CAST(Timestamp_Start AS DATE) = '2026-05-18' 
            ORDER BY Timestamp_Start
        """)
        rows = cur.fetchall()
        print(f"Total rides on 2026-05-18: {len(rows)}")
        for idx, row in enumerate(rows[:15], 1):
            print(f"{idx}. RideID: {row[0]} | Type: {row[1]} | Class: {row[2]} | Dist: {row[3]} | Dur: {row[4]} | TessieID: {row[5]} | SOC: {row[6]}->{row[7]} | Start: {row[10]}")
            
        cur.close()
        conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
