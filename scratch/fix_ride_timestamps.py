"""
Fix Timestamp_Start for rides ingested from May 4th screenshots.
The sync script stored timestamps as UTC-parsed from filenames that were already in local (MST) time,
causing a 7-hour offset. This corrects them by adding 7 hours.

Current: 2026-05-04 04:37 (wrong - was parsed as UTC from 17:37 local)
Correct: 2026-05-04 17:37 (actual local time from filename Screenshot_20260504_172506...)
"""
import pyodbc
from datetime import timedelta

conn = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};Server=tcp:summitsqlus23436.database.windows.net,1433;Database=SummitMediaDB;Uid=summitadmin;Pwd=Summ1tSync2026!Azure;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;')
cur = conn.cursor()

# Get all rides with wrong timestamps (clustered in the 04:37-04:42 window on May 4th)
cur.execute("""
    SELECT RideID, Timestamp_Start, Source_URL
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-04 04:00:00'
      AND Timestamp_Start <= '2026-05-04 05:00:00'
""")
rides = cur.fetchall()
print(f"Found {len(rides)} rides to fix")

for ride in rides:
    ride_id, ts, source_url = ride
    corrected_ts = ts + timedelta(hours=7)  # Add 7 hours to convert stored-as-UTC to actual local time
    print(f"  {ride_id}: {ts} -> {corrected_ts}")
    cur.execute(
        "UPDATE Rides.Rides SET Timestamp_Start = ? WHERE RideID = ?",
        (corrected_ts, ride_id)
    )

conn.commit()
print(f"\nDone. Updated {len(rides)} rides.")
cur.close()
conn.close()
