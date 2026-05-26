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

print("\n=== All Rides between 18:00 and 19:30 on 2026-05-24 ===")
cursor.execute("""
    SELECT RideID, TripType, Timestamp_Start, Duration_min, Distance_mi, Driver_Earnings, Tessie_DriveID, Start_SOC, End_SOC
    FROM Rides.Rides 
    WHERE Timestamp_Start >= '2026-05-24 18:00:00' AND Timestamp_Start <= '2026-05-24 19:30:00'
    ORDER BY Timestamp_Start ASC
""")
columns = [col[0] for col in cursor.description]
rows = cursor.fetchall()
for r in rows:
    print(dict(zip(columns, r)))

cursor.close()
conn.close()
