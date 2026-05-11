import pyodbc

conn = pyodbc.connect(
    'Driver={ODBC Driver 18 for SQL Server};'
    'Server=tcp:summitsqlus23436.database.windows.net,1433;'
    'Database=SummitMediaDB;'
    'Uid=summitadmin;Pwd=Summ1tSync2026!Azure;'
    'Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)
cur = conn.cursor()

print("=== May 6th All Rides ===")
cur.execute("""
    SELECT RideID, Classification, Timestamp_Start, Driver_Earnings, Fare
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-06 00:00:00' AND Timestamp_Start < '2026-05-07 00:00:00'
    ORDER BY Timestamp_Start ASC
""")
rows = cur.fetchall()
print(f"Total rides: {len(rows)}")
for r in rows:
    print(f"  {r[0]} | {r[1]} | {str(r[2])[:16]} | Earn:{r[3]} | Fare:{r[4]}")

print("\n=== TRIP- records for May 6 ===")
cur.execute("SELECT RideID, Timestamp_Start, Driver_Earnings FROM Rides.Rides WHERE RideID LIKE 'TRIP-20260506%' ORDER BY RideID")
trips = cur.fetchall()
print(f"Count: {len(trips)}")
for r in trips:
    print(f"  {r[0]} | {str(r[1])[:16]} | Earn:{r[2]}")

print("\n=== Tessie drive classifications for May 6 ===")
cur.execute("""
    SELECT Classification, COUNT(*) 
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-06 00:00:00' AND Timestamp_Start < '2026-05-07 00:00:00'
      AND RideID LIKE 'TESSIE-%'
    GROUP BY Classification
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
