import os, json, sys

backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
with open(os.path.join(backend_dir, 'local.settings.json')) as f:
    settings = json.load(f)
for k,v in settings.get('Values', {}).items():
    os.environ[k] = v

sys.path.insert(0, backend_dir)
from services.database import DatabaseClient

db = DatabaseClient()
conn = db.get_connection()
cur = conn.cursor()

# Earnings by RideID type
cur.execute("""
    SELECT
        CASE
            WHEN RideID LIKE 'TRIP-%'   THEN 'TRIP_OCR'
            WHEN RideID LIKE 'UBER-%'   THEN 'UBER_TS'
            WHEN RideID LIKE 'TESSIE-%' THEN 'TESSIE'
            ELSE 'Other'
        END as id_type,
        COUNT(*) as cnt,
        COUNT(CASE WHEN Driver_Earnings > 0 THEN 1 END) as with_earn,
        ISNULL(SUM(Driver_Earnings), 0) as total_earn
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-01'
      AND Timestamp_Start <  '2026-06-01'
    GROUP BY
        CASE
            WHEN RideID LIKE 'TRIP-%'   THEN 'TRIP_OCR'
            WHEN RideID LIKE 'UBER-%'   THEN 'UBER_TS'
            WHEN RideID LIKE 'TESSIE-%' THEN 'TESSIE'
            ELSE 'Other'
        END
    ORDER BY total_earn DESC
""")
print("Type       | Count | WithEarnings | TotalEarnings")
print("-" * 52)
grand = 0
for r in cur.fetchall():
    earn = float(r[3])
    grand += earn
    print(f"{r[0]:<10} | {r[1]:>5} | {r[2]:>12} | {earn:>12.2f}")
print("-" * 52)
print(f"{'TOTAL':<10} | {'':>5} | {'':>12} | {grand:>12.2f}")

# Show a single day in detail to see the duplication pattern
print("\n--- May 8 earnings by type ---")
cur.execute("""
    SELECT
        RideID,
        TripType,
        Classification,
        ISNULL(Driver_Earnings, 0) as earn,
        CONVERT(varchar(16), Timestamp_Start, 120) as ts
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-08'
      AND Timestamp_Start <  '2026-05-09'
      AND Driver_Earnings > 0
    ORDER BY Timestamp_Start, RideID
""")
day_total = 0
for r in cur.fetchall():
    earn = float(r[3])
    day_total += earn
    print(f"  {r[0]:<30} {r[2]:<22} {earn:>7.2f}  {r[4]}")
print(f"  May 8 total: {day_total:.2f}")

conn.close()
