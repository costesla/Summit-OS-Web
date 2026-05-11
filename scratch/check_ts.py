import pyodbc

conn = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};Server=tcp:summitsqlus23436.database.windows.net,1433;Database=SummitMediaDB;Uid=summitadmin;Pwd=Summ1tSync2026!Azure;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;')
cur = conn.cursor()

# Get recent rides with earnings
cur.execute("""
    SELECT TOP 10 RideID, Timestamp_Start, Driver_Earnings
    FROM Rides.Rides
    WHERE Driver_Earnings > 0
    ORDER BY Timestamp_Start DESC
""")
print("=== Recent Rides with Earnings ===")
for r in cur.fetchall():
    print(f"  RideID={r[0]}  Timestamp_Start={r[1]}  Earnings={r[2]}")

print()
print("=== Diagnosis ===")
print("Tessie drive times (from API): 13:36, 14:06, 17:46, 18:37, 19:05 MST on 2026-05-04")
print("These in UTC would be: 20:36, 21:06, 00:46+1day, 01:37+1day, 02:05+1day")
print("SQL Timestamp_Start for the rides are in local time or UTC?")
