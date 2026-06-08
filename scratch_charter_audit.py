"""Audit how charter/private trips (Jackie, Daniel, etc.) are stored."""
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

# 1. All non-Uber classifications with earnings
cur.execute("""
    SELECT
        Classification,
        LEFT(RideID, 10) as id_prefix,
        COUNT(*) as cnt,
        ISNULL(SUM(Driver_Earnings), 0) as total_earn,
        COUNT(CASE WHEN Sidecar_Artifact_JSON IS NOT NULL THEN 1 END) as has_sidecar,
        MIN(CONVERT(varchar(10), Timestamp_Start, 23)) as earliest,
        MAX(CONVERT(varchar(10), Timestamp_Start, 23)) as latest
    FROM Rides.Rides
    WHERE Classification NOT LIKE '%ber%'
      AND Classification NOT LIKE 'Untagged%'
      AND Driver_Earnings > 0
    GROUP BY Classification, LEFT(RideID, 10)
    ORDER BY total_earn DESC
""")
print("Non-Uber trips with earnings:")
print(f"{'Classification':<30} {'Prefix':<12} {'Cnt':>4} {'Earn':>9} {'Sidecar':>7} {'Range'}")
print("-" * 80)
for r in cur.fetchall():
    print(f"{str(r[0]):<30} {str(r[1]):<12} {r[2]:>4} {float(r[3]):>9.2f} {r[4]:>7}  {r[5]} – {r[6]}")

# 2. Sample Jackie / Daniel / Esmeralda rows — full columns
print("\n\nSample charter rows (Jackie / Daniel):")
cur.execute("""
    SELECT TOP 6
        RideID, TripType, Classification, Driver_Earnings,
        Pickup_Location, Dropoff_Location, Tessie_DriveID,
        Sidecar_Artifact_JSON,
        CONVERT(varchar(16), Timestamp_Start, 120) as ts
    FROM Rides.Rides
    WHERE (Classification LIKE '%Jackie%' OR Classification LIKE '%Daniel%'
           OR Classification LIKE '%Esmeralda%' OR Classification LIKE '%Private%')
      AND Driver_Earnings > 0
    ORDER BY Timestamp_Start DESC
""")
for r in cur.fetchall():
    sidecar = json.loads(r[7]) if r[7] else {}
    coord_keys = [k for k in sidecar if 'lat' in k.lower() or 'lon' in k.lower() or 'coord' in k.lower()]
    print(f"\n  RideID:   {r[0]}")
    print(f"  Type:     {r[1]}  |  Class: {r[2]}  |  Earn: {float(r[3]):.2f}")
    print(f"  Pickup:   {r[4]}")
    print(f"  Dropoff:  {r[5]}")
    print(f"  TessieID: {r[6]}")
    print(f"  Sidecar keys: {list(sidecar.keys())}")
    if coord_keys:
        print(f"  Coord keys: {coord_keys}")
    print(f"  Timestamp: {r[8]}")

# 3. Are private trips included in the heatmap endpoint?
# The heatmap queries Rides.Rides with no Classification filter —
# all records end up in the address pool for geocoding.
cur.execute("""
    SELECT COUNT(*) as total_private,
           COUNT(CASE WHEN Pickup_Location IS NOT NULL THEN 1 END) as has_pickup,
           COUNT(CASE WHEN Dropoff_Location IS NOT NULL THEN 1 END) as has_dropoff
    FROM Rides.Rides
    WHERE (Classification LIKE '%Jackie%' OR Classification LIKE '%Daniel%'
           OR Classification LIKE '%Esmeralda%'
           OR (Classification LIKE '%Private%' AND Driver_Earnings > 0))
""")
r = cur.fetchone()
print(f"\n\nPrivate/charter trip counts:")
print(f"  Total rows:       {r[0]}")
print(f"  With Pickup addr: {r[1]}")
print(f"  With Dropoff addr:{r[2]}")

# 4. Check if any of these addresses are already in GeoCache
cur.execute("""
    SELECT COUNT(*) as in_cache
    FROM Rides.Rides r
    JOIN Rides.GeoCache g ON g.Address = r.Pickup_Location
    WHERE (r.Classification LIKE '%Jackie%' OR r.Classification LIKE '%Daniel%'
           OR r.Classification LIKE '%Private%')
""")
r = cur.fetchone()
print(f"  Pickup addrs already geocoded: {r[0]}")

conn.close()
