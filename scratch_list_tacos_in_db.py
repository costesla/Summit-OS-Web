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

print("=== LISTING TACO BELLS IN DATABASE ===")
cursor.execute("""
    SELECT * 
    FROM Rides.ManualExpenses 
    WHERE Merchant = 'Taco Bell' AND CAST(Timestamp AS DATE) = '2026-05-26'
""")
columns = [col[0] for col in cursor.description]
rows = cursor.fetchall()
for r in rows:
    print(dict(zip(columns, r)))

cursor.close()
conn.close()
