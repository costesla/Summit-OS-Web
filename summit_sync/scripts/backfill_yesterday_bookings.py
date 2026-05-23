import os
import sys
import json
import pyodbc
import datetime

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.reconciliation import ReconciliationEngine

def main():
    try:
        # Load env
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend')
        settings_path = os.path.join(backend_dir, 'local.settings.json')
        if os.path.exists(settings_path):
            print(f"Loading env from {settings_path}")
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                for k, v in settings.get('Values', {}).items():
                    os.environ[k] = v

        # Also load Tessie keys from summitsyncfunc-settings.json in the root workspace
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sync_settings_path = os.path.join(root_dir, 'summitsyncfunc-settings.json')
        if os.path.exists(sync_settings_path):
            print(f"Loading Tessie keys from {sync_settings_path}")
            with open(sync_settings_path, 'r') as f:
                sync_settings = json.load(f)
                for item in sync_settings:
                    name = item.get('name')
                    value = item.get('value')
                    if name in ['TESSIE_API_KEY', 'TESSIE_VIN']:
                        os.environ[name] = value

        conn_str = os.environ.get("SQL_CONNECTION_STRING")
        if not conn_str:
            print("SQL_CONNECTION_STRING not found.")
            return

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        print("Clearing any existing manual Jackie bookings on 2026-05-22 to ensure clean matching...")
        cursor.execute("DELETE FROM Trips WHERE Passenger_FirstName = 'Jackie' AND CAST(Timestamp_Offer AS DATE) = '2026-05-22'")
        conn.commit()

        print("Inserting 5 private bookings for Jackie on 2026-05-22...")
        
        # The 5 drives' start times from gestern with durations (minutes)
        drives_info = [
            ("P-JACKIE-0522-1", "2026-05-22 17:18:23", 17.64, 29.7),
            ("P-JACKIE-0522-2", "2026-05-22 18:13:04", 26.28, 35.6),
            ("P-JACKIE-0522-3", "2026-05-22 18:48:55", 0.11, 1.23),
            ("P-JACKIE-0522-4", "2026-05-22 18:58:27", 3.18, 16.75),
            ("P-JACKIE-0522-5", "2026-05-22 19:18:11", 19.62, 31.3)
        ]
        
        insert_query = """
        INSERT INTO Trips (
            TripID, TripType, Timestamp_Offer, Distance_mi, Duration_min, 
            Passenger_FirstName, Notes, Classification, Fare, CreatedAt, LastUpdated
        ) VALUES (?, 'Private', ?, ?, ?, 'Jackie', 'Manual round trip yesterday', 'Private_Booking', ?, GETDATE(), GETDATE())
        """
        
        for index, (trip_id, start_time, dist, duration) in enumerate(drives_info):
            # Put the $30 payment on the first segment, others at $0
            fare_val = 30.00 if index == 0 else 0.00
            cursor.execute(insert_query, (trip_id, start_time, dist, duration, fare_val))
            
        conn.commit()
        print("Successfully inserted 5 private bookings.")

        cursor.close()
        conn.close()

        # Run the Reconciliation Engine to match, link, and tag the drives!
        print("\nStarting Reconciliation Engine to match, link, and tag...")
        engine = ReconciliationEngine()
        engine.reconcile_private_trips(days_back=7)
        print("Live Backfill and Reconciliation Completed Successfully.")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
