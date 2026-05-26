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

print("=== Searching Rides.Rides for the Maizeland -> Tyler drive ===")
cursor.execute("""
    SELECT RideID, TripType, Classification, Distance_mi, Duration_min, Timestamp_Start, Pickup_Location, Dropoff_Location, Start_SOC, End_SOC, Sidecar_Artifact_JSON
    FROM Rides.Rides 
    WHERE Timestamp_Start >= '2026-05-24 17:30:00' AND Timestamp_Start <= '2026-05-24 18:20:00'
""")
columns = [col[0] for col in cursor.description]
rows = cursor.fetchall()
print(f"Found {len(rows)} drives in the 17:30 to 18:20 time window:")
for r in rows:
    print("\n-------------------------------------------")
    for col, val in zip(columns, r):
        if col != "Sidecar_Artifact_JSON":
            print(f"{col}: {val}")
        else:
            print(f"JSON contains tag: {json.loads(val).get('tag') if val else 'No JSON'}")

cursor.close()
conn.close()
