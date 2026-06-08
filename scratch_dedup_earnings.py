"""
One-time cleanup: zero out Driver_Earnings on TESSIE-* and UBER-* rows that
duplicate an earnings amount already captured on a canonical TRIP-* record.

Rows are NOT deleted — they remain for drive-tracking purposes. Only the
Driver_Earnings and Tip columns are zeroed so they no longer inflate totals.

Run once, verify output, then the daily timer keeps it clean going forward.
"""
import os, json, sys

backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
with open(os.path.join(backend_dir, 'local.settings.json')) as f:
    settings = json.load(f)
for k, v in settings.get('Values', {}).items():
    os.environ[k] = v
sys.path.insert(0, backend_dir)

from services.database import DatabaseClient

db = DatabaseClient()
conn = db.get_connection()
cur = conn.cursor()

# ── DRY RUN: show what would be zeroed ─────────────────────────────────────
print("DRY RUN — rows that will be zeroed out:\n")

cur.execute("""
    SELECT r.RideID, r.Classification,
           CONVERT(varchar(16), r.Timestamp_Start, 120) as ts,
           r.Driver_Earnings
    FROM Rides.Rides r
    WHERE r.RideID LIKE 'TESSIE-%'
      AND r.Driver_Earnings > 0
      AND EXISTS (
          SELECT 1 FROM Rides.Rides t
          WHERE t.RideID LIKE 'TRIP-%'
            AND t.Driver_Earnings > 0
            AND CAST(t.Timestamp_Start AS DATE) = CAST(r.Timestamp_Start AS DATE)
            AND ABS(DATEDIFF(minute, t.Timestamp_Start, r.Timestamp_Start)) <= 30
      )
    ORDER BY r.Timestamp_Start
""")
tessie_rows = cur.fetchall()
tessie_total = sum(float(r[3]) for r in tessie_rows)
print(f"TESSIE duplicates: {len(tessie_rows)} rows  total ${tessie_total:.2f}")

cur.execute("""
    SELECT r.RideID, r.Classification,
           CONVERT(varchar(16), r.Timestamp_Start, 120) as ts,
           r.Driver_Earnings
    FROM Rides.Rides r
    WHERE r.RideID LIKE 'UBER-%'
      AND r.Driver_Earnings > 0
      AND EXISTS (
          SELECT 1 FROM Rides.Rides t
          WHERE t.RideID LIKE 'TRIP-%'
            AND t.Driver_Earnings > 0
            AND CAST(t.Timestamp_Start AS DATE) = CAST(r.Timestamp_Start AS DATE)
            AND ABS(DATEDIFF(minute, t.Timestamp_Start, r.Timestamp_Start)) <= 30
      )
    ORDER BY r.Timestamp_Start
""")
uber_rows = cur.fetchall()
uber_total = sum(float(r[3]) for r in uber_rows)
print(f"UBER   duplicates: {len(uber_rows)} rows  total ${uber_total:.2f}")
print(f"\nTotal to zero:     {len(tessie_rows)+len(uber_rows)} rows  ${tessie_total+uber_total:.2f}")

answer = input("\nProceed with cleanup? (yes/no): ").strip().lower()
if answer != 'yes':
    print("Aborted.")
    conn.close()
    sys.exit(0)

# ── EXECUTE CLEANUP ─────────────────────────────────────────────────────────
print("\nExecuting...")

cur.execute("""
    UPDATE Rides.Rides
    SET Driver_Earnings = 0, Tip = 0, LastUpdated = GETDATE()
    WHERE RideID LIKE 'TESSIE-%'
      AND Driver_Earnings > 0
      AND EXISTS (
          SELECT 1 FROM Rides.Rides t
          WHERE t.RideID LIKE 'TRIP-%'
            AND t.Driver_Earnings > 0
            AND CAST(t.Timestamp_Start AS DATE) = CAST(Rides.Timestamp_Start AS DATE)
            AND ABS(DATEDIFF(minute, t.Timestamp_Start, Rides.Timestamp_Start)) <= 30
      )
""")
tessie_affected = cur.rowcount
print(f"  TESSIE rows zeroed: {tessie_affected}")

cur.execute("""
    UPDATE Rides.Rides
    SET Driver_Earnings = 0, Tip = 0, LastUpdated = GETDATE()
    WHERE RideID LIKE 'UBER-%'
      AND Driver_Earnings > 0
      AND EXISTS (
          SELECT 1 FROM Rides.Rides t
          WHERE t.RideID LIKE 'TRIP-%'
            AND t.Driver_Earnings > 0
            AND CAST(t.Timestamp_Start AS DATE) = CAST(Rides.Timestamp_Start AS DATE)
            AND ABS(DATEDIFF(minute, t.Timestamp_Start, Rides.Timestamp_Start)) <= 30
      )
""")
uber_affected = cur.rowcount
print(f"  UBER   rows zeroed: {uber_affected}")

conn.commit()
print(f"\nDone. {tessie_affected + uber_affected} rows cleaned.")

# ── VERIFY ──────────────────────────────────────────────────────────────────
cur.execute("""
    SELECT
        ISNULL(SUM(CASE WHEN RideID LIKE 'TRIP-%' THEN Driver_Earnings END), 0),
        ISNULL(SUM(CASE WHEN RideID LIKE 'TESSIE-%' THEN Driver_Earnings END), 0),
        ISNULL(SUM(CASE WHEN RideID LIKE 'UBER-%' THEN Driver_Earnings END), 0)
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-01'
      AND Timestamp_Start <  '2026-06-01'
""")
r = cur.fetchone()
print(f"\nMay verification after cleanup:")
print(f"  TRIP-*   earnings: ${float(r[0]):.2f}  (canonical)")
print(f"  TESSIE-* earnings: ${float(r[1]):.2f}  (should be near $0 for matched rows)")
print(f"  UBER-*   earnings: ${float(r[2]):.2f}  (should be near $0 for matched rows)")

conn.close()
