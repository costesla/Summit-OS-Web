
import os
import pyodbc
import logging
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load Env
# Try to load from backend/.env or similar if needed, but usually env is set in shell or .env file in root
# Assuming run from root or backend/scripts
load_dotenv()

# We might need to point to the right .env file if it's not picked up
if not os.environ.get("SQL_CONNECTION_STRING"):
    # Try loading from parent directories
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, "../../"))
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        # Try backend/.env
        env_path = os.path.join(root_dir, "backend", ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            # Try summit_sync/.env
            env_path = os.path.join(root_dir, "summit_sync", ".env")
            if os.path.exists(env_path):
                load_dotenv(env_path)

def get_connection():
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        logging.error("SQL_CONNECTION_STRING not found.")
        return None
    try:
        return pyodbc.connect(conn_str)
    except Exception as e:
        logging.error(f"Connection failed: {e}")
        return None

def run_migration():
    script_path = os.path.join(os.path.dirname(__file__), "sql", "update_schema_v2.sql")
    if not os.path.exists(script_path):
        logging.error(f"Migration script not found at {script_path}")
        return

    logging.info(f"Reading migration script: {script_path}")
    with open(script_path, "r") as f:
        sql_script = f.read()

    conn = get_connection()
    if not conn:
        return

    cursor = conn.cursor()
    try:
        # Split by GO if needed, or run as whole if driver supports it. 
        # pyodbc usually executes one batch. MS SQL requires splitting by GO for some DDl.
        # Simple parser to split by GO on a new line
        batches = [b for b in sql_script.split("GO") if b.strip()]
        
        for batch in batches:
            logging.info("Executing batch...")
            cursor.execute(batch)
            conn.commit()
            
        logging.info("Migration completed successfully.")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
