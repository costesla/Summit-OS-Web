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

drive_id = 'TESSIE-397010117'

print(f"=== Querying Rides.Rides for {drive_id} ===")
cursor.execute("SELECT * FROM Rides.Rides WHERE RideID = ?", (drive_id,))
columns = [col[0] for col in cursor.description]
row = cursor.fetchone()
if row:
    for col, val in zip(columns, row):
        print(f"{col}: {val}")
else:
    print("Not found in Rides.Rides")

cursor.close()
conn.close()
