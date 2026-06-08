"""
DB audit: understand the full scope of duplicate earnings and data quality issues
across all record types in Rides.Rides.
"""
import os, json, sys
from decimal import Decimal

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

print("=" * 70)
print("RIDES.RIDES — FULL DATA AUDIT")
print("=" * 70)

# 1. Record type breakdown — ALL TIME
cur.execute("""
    SELECT
        CASE
            WHEN RideID LIKE 'TRIP-%'   THEN 'TRIP (OCR canonical)'
            WHEN RideID LIKE 'UBER-%'   THEN 'UBER (timestamp ref)'
            WHEN RideID LIKE 'TESSIE-%' THEN 'TESSIE (drive ref)'
            ELSE                             'Other / legacy'
        END as id_type,
        COUNT(*) as total_rows,
        COUNT(CASE WHEN Driver_Earnings > 0 THEN 1 END) as rows_with_earnings,
        ISNULL(SUM(Driver_Earnings), 0) as sum_earnings,
        MIN(Timestamp_Start) as earliest,
        MAX(Timestamp_Start) as latest
    FROM Rides.Rides
    GROUP BY
        CASE
            WHEN RideID LIKE 'TRIP-%'   THEN 'TRIP (OCR canonical)'
            WHEN RideID LIKE 'UBER-%'   THEN 'UBER (timestamp ref)'
            WHEN RideID LIKE 'TESSIE-%' THEN 'TESSIE (drive ref)'
            ELSE                             'Other / legacy'
        END
    ORDER BY sum_earnings DESC
""")
print("\n1. ALL-TIME record type breakdown:")
print(f"{'Type':<25} {'Rows':>6} {'WithEarn':>9} {'SumEarn':>10}  {'Earliest':<12} {'Latest':<12}")
print("-" * 80)
for r in cur.fetchall():
    print(f"{r[0]:<25} {r[1]:>6} {r[2]:>9} {float(r[3]):>10.2f}  {str(r[4])[:10]:<12} {str(r[5])[:10]:<12}")

# 2. 'Other / legacy' — what are these?
cur.execute("""
    SELECT TOP 10 RideID, TripType, Classification, Driver_Earnings,
                  CONVERT(varchar(16), Timestamp_Start, 120) as ts
    FROM Rides.Rides
    WHERE RideID NOT LIKE 'TRIP-%'
      AND RideID NOT LIKE 'UBER-%'
      AND RideID NOT LIKE 'TESSIE-%'
      AND Driver_Earnings > 0
    ORDER BY Timestamp_Start DESC
""")
rows = cur.fetchall()
print(f"\n2. 'Other' records with earnings (sample of {len(rows)}):")
for r in rows:
    print(f"  {r[0]:<30} {r[1]:<12} {r[2]:<22} {float(r[3]):>8.2f}  {r[4]}")

# 3. TESSIE records with earnings — how many are true duplicates of a TRIP record?
cur.execute("""
    SELECT
        COUNT(*) as tessie_with_earn,
        COUNT(CASE WHEN trip_match.RideID IS NOT NULL THEN 1 END) as has_matching_trip,
        COUNT(CASE WHEN trip_match.RideID IS NULL     THEN 1 END) as no_matching_trip,
        SUM(t.Driver_Earnings) as total_earn_to_zero_out,
        SUM(CASE WHEN trip_match.RideID IS NULL THEN t.Driver_Earnings ELSE 0 END) as orphan_earn
    FROM Rides.Rides t
    LEFT JOIN Rides.Rides trip_match
        ON  trip_match.RideID LIKE 'TRIP-%'
        AND CAST(trip_match.Timestamp_Start AS DATE) = CAST(t.Timestamp_Start AS DATE)
        AND ABS(DATEDIFF(minute, trip_match.Timestamp_Start, t.Timestamp_Start)) <= 30
        AND trip_match.Driver_Earnings > 0
    WHERE t.RideID LIKE 'TESSIE-%'
      AND t.Driver_Earnings > 0
""")
r = cur.fetchone()
print(f"\n3. TESSIE records with earnings:")
print(f"   Total TESSIE rows with earnings:   {r[0]}")
print(f"   Have a matching TRIP record:       {r[1]}  <-- safe to zero out")
print(f"   No matching TRIP record (orphan):  {r[2]}  <-- keep these")
print(f"   Earnings to zero out (duplicates): ${float(r[3] or 0):.2f}")
print(f"   Orphan earnings to preserve:       ${float(r[4] or 0):.2f}")

# 4. UBER records with earnings — same check
cur.execute("""
    SELECT
        COUNT(*) as uber_with_earn,
        COUNT(CASE WHEN trip_match.RideID IS NOT NULL THEN 1 END) as has_matching_trip,
        COUNT(CASE WHEN trip_match.RideID IS NULL     THEN 1 END) as no_matching_trip,
        SUM(t.Driver_Earnings) as total_earn,
        SUM(CASE WHEN trip_match.RideID IS NULL THEN t.Driver_Earnings ELSE 0 END) as orphan_earn
    FROM Rides.Rides t
    LEFT JOIN Rides.Rides trip_match
        ON  trip_match.RideID LIKE 'TRIP-%'
        AND CAST(trip_match.Timestamp_Start AS DATE) = CAST(t.Timestamp_Start AS DATE)
        AND ABS(DATEDIFF(minute, trip_match.Timestamp_Start, t.Timestamp_Start)) <= 30
        AND trip_match.Driver_Earnings > 0
    WHERE t.RideID LIKE 'UBER-%'
      AND t.Driver_Earnings > 0
""")
r = cur.fetchone()
print(f"\n4. UBER-timestamp records with earnings:")
print(f"   Total UBER rows with earnings:     {r[0]}")
print(f"   Have a matching TRIP record:       {r[1]}  <-- safe to zero out")
print(f"   No matching TRIP record (orphan):  {r[2]}  <-- keep these")
print(f"   Earnings to zero out (duplicates): ${float(r[3] or 0):.2f}")
print(f"   Orphan earnings to preserve:       ${float(r[4] or 0):.2f}")

# 5. What would the clean total look like — all time?
cur.execute("""
    SELECT
        ISNULL(SUM(Driver_Earnings), 0) as trip_only_total,
        COUNT(DISTINCT CAST(Timestamp_Start AS DATE)) as days_with_trips,
        COUNT(*) as trip_rows
    FROM Rides.Rides
    WHERE RideID LIKE 'TRIP-%'
      AND Driver_Earnings > 0
""")
r = cur.fetchone()
print(f"\n5. Clean totals (TRIP-* only):")
print(f"   All-time earnings:  ${float(r[0]):.2f}")
print(f"   Days with trips:    {r[1]}")
print(f"   Trip records:       {r[2]}")

# 6. Duplicate pattern — any TRIP records with the same timestamp (self-duplication)?
cur.execute("""
    SELECT COUNT(*) as dup_count
    FROM (
        SELECT Timestamp_Start, COUNT(*) as cnt
        FROM Rides.Rides
        WHERE RideID LIKE 'TRIP-%'
          AND Driver_Earnings > 0
        GROUP BY Timestamp_Start
        HAVING COUNT(*) > 1
    ) x
""")
r = cur.fetchone()
print(f"\n6. TRIP-* self-duplicates (same timestamp): {r[0]}")

conn.close()
print("\n" + "=" * 70)
