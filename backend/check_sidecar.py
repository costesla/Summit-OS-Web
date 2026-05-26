import json
import os

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
            SELECT RideID, Sidecar_Artifact_JSON, Classification
            FROM Rides.Rides 
            WHERE CAST(Timestamp_Start AS DATE) = '2026-05-18' 
              AND Sidecar_Artifact_JSON IS NOT NULL
            ORDER BY Timestamp_Start
        """)
        rows = cur.fetchall()
        print(f"Total rides with Sidecar_Artifact_JSON on 2026-05-18: {len(rows)}")
        if rows:
            print(f"RideID: {rows[0][0]}")
            print(f"Classification: {rows[0][2]}")
            print("Sidecar content snippet:")
            print(rows[0][1][:500])
            
        cur.close()
        conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
