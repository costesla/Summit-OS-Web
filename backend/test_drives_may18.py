import json
import os
import datetime
from zoneinfo import ZoneInfo

def main():
    try:
        # Load .env file
        env_path = '.env'
        if os.path.exists(env_path):
            print("Loading environment from:", env_path)
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        parts = line.split('=', 1)
                        key = parts[0].strip()
                        val = parts[1].strip().strip('"').strip("'")
                        os.environ[key] = val

        # Load local settings for DB connection & Tessie config
        # Try both root and backend directory paths
        settings_path = 'local.settings.json'
        if not os.path.exists(settings_path):
            settings_path = os.path.join('backend', 'local.settings.json')
            
        if os.path.exists(settings_path):
            print("Using settings path:", settings_path)
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                for k, v in settings.get('Values', {}).items():
                    os.environ[k] = v

        from services.tessie import TessieClient
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        print("VIN:", vin)
        print("API Key configured:", bool(os.environ.get("TESSIE_API_KEY")))

        # May 18th MST to UTC
        # MDT is UTC-6
        day_dt = datetime.datetime.strptime("2026-05-18", "%Y-%m-%d")
        from_dt_utc = day_dt + datetime.timedelta(hours=6)
        to_dt_utc   = day_dt + datetime.timedelta(hours=30)
        from_ts = int(from_dt_utc.timestamp())
        to_ts   = int(to_dt_utc.timestamp())

        print(f"Querying Tessie from {from_dt_utc} ({from_ts}) to {to_dt_utc} ({to_ts})...")
        
        # 1. Fetch drives from Tessie Client
        drives = tessie.get_tagged_drives(vin, from_ts, to_ts)
        print(f"\nFound {len(drives)} drives:")
        for idx, d in enumerate(drives, 1):
            print(f"{idx}. ID: {d.get('id') or d.get('drive_id')} | Started: {d.get('started_at')} | Dist: {d.get('odometer_distance')} | Tag: {d.get('tag')} | Date: {d.get('date') or d.get('started_at')}")
            
        # 2. Inspect database Rides.Rides for May 18th
        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        print("\n--- Rides.Rides for 2026-05-18 ---")
        cur.execute("SELECT RideID, Distance_mi, Tessie_Distance, Timestamp_Start FROM Rides.Rides WHERE CAST(Timestamp_Start AS DATE) = '2026-05-18' ORDER BY Timestamp_Start")
        rows = cur.fetchall()
        print(f"Found {len(rows)} rides in database:")
        for row in rows:
            print(row)
        
        cur.close()
        conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
