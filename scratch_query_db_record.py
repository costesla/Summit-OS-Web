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

print("=== Stored Tessie Drives Boundaries ===")
cursor.execute("SELECT MIN(Timestamp_Start) AS Earliest, MAX(Timestamp_Start) AS Latest, COUNT(*) AS TotalDrives FROM Rides.Rides")
row = cursor.fetchone()
if row:
    print(f"Earliest Drive Stored: {row[0]}")
    print(f"Latest Drive Stored:   {row[1]}")
    print(f"Total Drives in DB:    {row[2]}")

cursor.close()
conn.close()
