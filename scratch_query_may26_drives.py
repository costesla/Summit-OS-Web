import os
import sys
import json
import pyodbc
from datetime import datetime, timedelta

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

# May 26 shift: starts midnight Mon May 25 (night shift) to end of May 26
# The shift is night of May 25 through end of May 26
print("=== ALL RIDES WITH Timestamp_Start ON OR NEAR 2026-05-26 ===")
cursor.execute("""
    SELECT RideID, TripType, Timestamp_Start, Duration_min, Distance_mi, Driver_Earnings, Classification
    FROM Rides.Rides 
    WHERE Timestamp_Start >= '2026-05-25 18:00:00' 
      AND Timestamp_Start <= '2026-05-27 06:00:00'
    ORDER BY Timestamp_Start ASC
""")
columns = [col[0] for col in cursor.description]
rows = cursor.fetchall()

uber_min = 0
jackie_min = 0

print(f"{'RideID':<25} {'TripType':<10} {'Timestamp_Start':<22} {'Duration':<10} {'Distance':<10} {'Earnings':<10}")
print("-" * 100)
for r in rows:
    d = dict(zip(columns, r))
    trip_type = d.get('TripType', '') or ''
    dur = d.get('Duration_min') or 0
    print(f"{d['RideID']:<25} {trip_type:<10} {str(d['Timestamp_Start']):<22} {dur:<10} {d['Distance_mi'] or 0:<10} {d['Driver_Earnings'] or 0:<10}")
    if 'Uber' in trip_type or 'uber' in trip_type.lower():
        uber_min += dur
    elif 'Jackie' in trip_type or 'jackie' in trip_type.lower():
        jackie_min += dur

total_min = uber_min + jackie_min
print(f"\n=== HOUR TOTALS ===")
print(f"Uber trips:   {uber_min} min = {uber_min/60:.2f} hours")
print(f"Jackie trips: {jackie_min} min = {jackie_min/60:.2f} hours")
print(f"COMBINED:     {total_min} min = {total_min/60:.2f} hours = {int(total_min//60)}h {int(total_min%60)}m")

cursor.close()
conn.close()
