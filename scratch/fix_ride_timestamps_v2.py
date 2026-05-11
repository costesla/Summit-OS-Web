"""
Re-derive Timestamp_Start for the 12 May 4th rides from their Source_URL filenames.
The filenames contain the actual local MST time.
"""
import pyodbc, re, datetime

conn = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};Server=tcp:summitsqlus23436.database.windows.net,1433;Database=SummitMediaDB;Uid=summitadmin;Pwd=Summ1tSync2026!Azure;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;')
cur = conn.cursor()

cur.execute("""
    SELECT RideID, Timestamp_Start, Source_URL
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-04 11:00:00'
      AND Timestamp_Start <= '2026-05-04 12:00:00'
""")
rides = cur.fetchall()
print(f"Found {len(rides)} rides to fix")

fixed = 0
for ride in rides:
    ride_id, ts, source_url = ride
    # Try to extract timestamp from filename
    # Patterns: Screenshot_20260504_172506 or Screenshot_20260504-172506
    m = re.search(r'Screenshot[_\s]?(\d{8})[_\-](\d{6})', source_url or '')
    if m:
        dt = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
        print(f"  {ride_id}: {ts} -> {dt}  (from {source_url[:50]})")
        cur.execute("UPDATE Rides.Rides SET Timestamp_Start = ? WHERE RideID = ?", (dt, ride_id))
        fixed += 1
    else:
        print(f"  {ride_id}: COULD NOT parse from '{source_url}'")

conn.commit()
print(f"\nFixed {fixed} of {len(rides)} rides.")
cur.close()
conn.close()
