import pyodbc
import json

conn = pyodbc.connect(
    'Driver={ODBC Driver 18 for SQL Server};'
    'Server=tcp:summitsqlus23436.database.windows.net,1433;'
    'Database=SummitMediaDB;'
    'Uid=summitadmin;'
    'Pwd=Summ1tSync2026!Azure;'
    'Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)
cur = conn.cursor()

# ── 1. Inspect the bad UBER- records ──────────────────────────────────────────
print("=== Bad UBER- records (UBER-1777937xxx) ===")
cur.execute("""
    SELECT RideID, Timestamp_Start, Fare, Driver_Earnings, Platform_Cut, Sidecar_Artifact_JSON
    FROM Rides.Rides
    WHERE RideID LIKE 'UBER-1777937%'
    ORDER BY Timestamp_Start
""")
bad_rows = cur.fetchall()
print(f"Count: {len(bad_rows)}")
for r in bad_rows:
    sidecar_preview = str(r[5])[:200] if r[5] else "None"
    print(f"  {r[0]} | {str(r[1])[:16]} | Fare:{r[2]} Earn:{r[3]} Cut:{r[4]}")
    print(f"    Sidecar: {sidecar_preview}")

# ── 2. Delete the bad records ──────────────────────────────────────────────────
print("\n=== Deleting bad UBER-1777937xxx records... ===")
cur.execute("DELETE FROM Rides.Rides WHERE RideID LIKE 'UBER-1777937%'")
deleted = cur.rowcount
conn.commit()
print(f"Deleted {deleted} bad records.")

# ── 3. Verify May 4th state after cleanup ─────────────────────────────────────
print("\n=== May 4th rides after cleanup ===")
cur.execute("""
    SELECT Classification, COUNT(*) as cnt, SUM(ISNULL(Driver_Earnings,0)) as total_earn
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-04 00:00:00' AND Timestamp_Start < '2026-05-05 00:00:00'
    GROUP BY Classification
    ORDER BY Classification
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} rides | Earnings: ${float(r[2]):.2f}")

# ── 4. Check what Tessie Uber_Dropoff rides still need fare matching ──────────
print("\n=== Uber_Dropoff rides still needing fare match ===")
cur.execute("""
    SELECT RideID, Timestamp_Start
    FROM Rides.Rides
    WHERE Classification IN ('Uber_Dropoff', 'Manual_Entry')
      AND (Fare IS NULL OR Fare = 0)
      AND Timestamp_Start >= '2026-05-04 00:00:00' AND Timestamp_Start < '2026-05-05 00:00:00'
    ORDER BY Timestamp_Start
""")
unmatched = cur.fetchall()
print(f"Unmatched: {len(unmatched)}")
for r in unmatched:
    print(f"  {r[0]} | {str(r[1])[:16]}")

conn.close()
print("\nDone. Now run the cloud scan for 'Uber Driver/2026/May/Week 1/04' via the dashboard.")
