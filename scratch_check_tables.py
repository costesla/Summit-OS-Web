import os
import sys
import json
import logging

# Setup logging to stdout
logging.basicConfig(level=logging.INFO)

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    print(f"Loading environment from {settings_path}")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

# Add backend to sys.path
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

try:
    import pyodbc
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    print(f"Connecting with connection string: {conn_str[:80]}...")
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    print("\n--- Listing schemas ---")
    cursor.execute("SELECT name FROM sys.schemas")
    for row in cursor.fetchall():
        print(row[0])
        
    print("\n--- Listing tables ---")
    cursor.execute("SELECT SCHEMA_NAME(schema_id) as [Schema], name FROM sys.tables")
    for row in cursor.fetchall():
        print(f"{row[0]}.{row[1]}")
        
    cursor.close()
    conn.close()
except Exception as e:
    import traceback
    traceback.print_exc()
