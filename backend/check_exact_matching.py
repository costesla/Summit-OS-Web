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
        
        # Let's fetch all Rides.Rides with earnings for 2026-05-18
        cur.execute("""
            SELECT RideID, Tessie_DriveID, Timestamp_Start, Driver_Earnings
            FROM Rides.Rides
            WHERE Driver_Earnings > 0
              AND Timestamp_Start IS NOT NULL
        """)
        earned_rides = []
        for row in cur.fetchall():
            ride_id = row[0]
            tessie_id = row[1]
            ts = row[2]
            earnings = float(row[3])
            earned_rides.append({
                "RideID": ride_id,
                "Tessie_DriveID": tessie_id,
                "Timestamp_Start": ts,
                "Driver_Earnings": earnings
            })
            
        cur.close()
        conn.close()

        # Let's mock the drives returned by Tessie for May 18th evenings
        drives = [
            {"tessie_drive_id": "395029798", "time_mst": "20:52", "date": "2026-05-18"},
            {"tessie_drive_id": "395028453", "time_mst": "20:42", "date": "2026-05-18"},
            {"tessie_drive_id": "395027333", "time_mst": "20:31", "date": "2026-05-18"},
            {"tessie_drive_id": "395025969", "time_mst": "20:18", "date": "2026-05-18"},
            {"tessie_drive_id": "395022176", "time_mst": "19:47", "date": "2026-05-18"},
            {"tessie_drive_id": "395020137", "time_mst": "19:42", "date": "2026-05-18"},
            {"tessie_drive_id": "395015469", "time_mst": "19:05", "date": "2026-05-18"},
            {"tessie_drive_id": "395012753", "time_mst": "18:56", "date": "2026-05-18"},
            {"tessie_drive_id": "395008421", "time_mst": "18:26", "date": "2026-05-18"},
            {"tessie_drive_id": "395005635", "time_mst": "18:18", "date": "2026-05-18"},
            {"tessie_drive_id": "394999660", "time_mst": "17:55", "date": "2026-05-18"},
            {"tessie_drive_id": "394999024", "time_mst": "17:35", "date": "2026-05-18"},
            {"tessie_drive_id": "394994843", "time_mst": "17:25", "date": "2026-05-18"},
        ]

        print("--- ID-Based & Tight Timing Match Test ---")
        for d in drives:
            drive_dt = datetime.datetime.strptime(f"{d['date']}T{d['time_mst']}:00", "%Y-%m-%dT%H:%M:%S")
            matched_ride = None
            match_method = None
            
            # 1. Try exact ID match
            for ride in earned_rides:
                r_id = ride["RideID"] or ""
                t_id = ride["Tessie_DriveID"] or ""
                d_id = d["tessie_drive_id"]
                
                # Check if drive ID is contained in either RideID or Tessie_DriveID
                if d_id in r_id or d_id in t_id:
                    matched_ride = ride
                    match_method = "EXACT ID"
                    break
                    
            # 2. Try tight time match (within 30 mins) if no exact ID match
            if not matched_ride:
                best_diff = 999999
                for ride in earned_rides:
                    diff = abs((ride["Timestamp_Start"] - drive_dt).total_seconds())
                    if diff <= 1800 and diff < best_diff: # 30 mins
                        best_diff = diff
                        matched_ride = ride
                        match_method = "TIME MATCH (30m)"

            if matched_ride:
                print(f"Drive {d['tessie_drive_id']} at {d['time_mst']} -> Matched via {match_method}: Ride {matched_ride['RideID']} | Earnings: ${matched_ride['Driver_Earnings']:.2f}")
            else:
                print(f"Drive {d['tessie_drive_id']} at {d['time_mst']} -> NO MATCH")

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
