import os
import sys
import json
import pyodbc

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

conn_str = os.environ.get("SQL_CONNECTION_STRING")
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

print("=== Querying TRIP records for May 24th ===")
cursor.execute("""
    SELECT RideID, Tessie_DriveID, TripType, Classification, Distance_mi, Driver_Earnings, Timestamp_Start
    FROM Rides.Rides 
    WHERE RideID LIKE 'TRIP-20260524-%'
    ORDER BY RideID ASC
""")
columns = [col[0] for col in cursor.description]
for row in cursor.fetchall():
    print(dict(zip(columns, row)))

print("\n=== Querying target Tessie drive in Rides.Rides ===")
cursor.execute("""
    SELECT RideID, TripType, Classification, Tessie_DriveID, Distance_mi, Driver_Earnings, Timestamp_Start
    FROM Rides.Rides 
    WHERE RideID = 'TESSIE-397010117'
""")
columns = [col[0] for col in cursor.description]
row = cursor.fetchone()
if row:
    print(dict(zip(columns, row)))

cursor.close()
conn.close()
