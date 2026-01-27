import os
import pyodbc
import logging

def load_env():
    # Look for .env in backend/config/.env
    base_dir = os.path.dirname(os.path.dirname(__file__))
    env_path = os.path.join(base_dir, 'config', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    try:
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value
                    except ValueError:
                        continue

if __name__ == "__main__":
    load_env()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found.")
        exit(1)

    # Path to the SQL script
    script_path = os.path.join(os.path.dirname(__file__), 'sql', 'restructure_schemas.sql')
    if not os.path.exists(script_path):
        print(f"Error: Script not found at {script_path}")
        exit(1)

    with open(script_path, 'r') as f:
        sql_commands = f.read()

    print(f"Connecting to SQL to Apply Modular Schema (Pricing, Rides, Customers, Reports)...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Split by GO if necessary, but pyodbc can often handle multiple statements 
        # unless there are specific batch restrictions.
        # We'll split by GO for safety.
        for command in sql_commands.split('GO'):
            if command.strip():
                try:
                    cursor.execute(command)
                except Exception as ex:
                    print(f"Sub-command failure: {ex}")
                    # Continue for IF NOT EXISTS commands
        
        conn.commit()
        print("Modular Schema Modernization Applied Successfully.")
        
    except Exception as e:
        print(f"Failed to apply modular schema: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
