"""
DB-only diagnostic: check what TRIP-20260529-* records exist in the database.
No Graph/OneDrive credentials needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from services.database import DatabaseClient

db = DatabaseClient()
conn = db.get_connection()
cursor = conn.cursor()

# Check what TRIP records exist for May 29
cursor.execute("""
    SELECT RideID, TripType, Timestamp_Start, Driver_Earnings, Classification, Tessie_DriveID
    FROM Rides.Rides
    WHERE RideID LIKE 'TRIP-20260529-%'
    ORDER BY RideID ASC
""")
rows = cursor.fetchall()

print(f"\n{'='*60}")
print(f"TRIP-20260529-* records in DB: {len(rows)}")
print(f"{'='*60}")
for r in rows:
    print(f"  {r[0]} | {r[1]} | {r[2]} | ${r[3]:.2f} | {r[4]} | Tessie: {r[5]}")

# Also check what ALL records exist for May 29 (Tessie drives too)
cursor.execute("""
    SELECT RideID, TripType, Classification, Timestamp_Start
    FROM Rides.Rides
    WHERE CAST(Timestamp_Start AS DATE) = '2026-05-29'
       OR RideID LIKE '%20260529%'
    ORDER BY Timestamp_Start ASC
""")
all_rows = cursor.fetchall()
print(f"\n{'='*60}")
print(f"ALL records touching 2026-05-29: {len(all_rows)}")
print(f"{'='*60}")
for r in all_rows:
    print(f"  {r[0]} | {r[1]} | {r[2]} | {r[3]}")

cursor.close()
