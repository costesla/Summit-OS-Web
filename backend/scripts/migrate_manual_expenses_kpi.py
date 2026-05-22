import os
import sys
import json
import logging

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.insert(0, backend_dir)

# Load env vars from local.settings.json
settings_path = os.path.join(backend_dir, "local.settings.json")
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
        for k, v in (settings.get("Values", {}) or {}).items():
            os.environ[str(k)] = str(v)

from services.database import DatabaseClient

def migrate():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Starting database migration for Rides.ManualExpenses...")
    
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        raise ConnectionError("Database connection failed.")
    cursor = conn.cursor()
    
    try:
        # 1. Check if column already exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'ManualExpenses' AND COLUMN_NAME = 'IncludedInKPI'
        """)
        exists = cursor.fetchone()[0] > 0
        
        if not exists:
            logging.info("Adding IncludedInKPI column to Rides.ManualExpenses...")
            cursor.execute("""
                ALTER TABLE Rides.ManualExpenses
                ADD IncludedInKPI BIT NOT NULL CONSTRAINT DF_ManualExpenses_KPI DEFAULT 1
            """)
            conn.commit()
            logging.info("IncludedInKPI column added successfully.")
        else:
            logging.info("IncludedInKPI column already exists.")

        # 2. Backfill existing records (set IncludedInKPI to 0 for Maintenance and General_Expense)
        logging.info("Backfilling existing records...")
        cursor.execute("""
            UPDATE Rides.ManualExpenses
            SET IncludedInKPI = 0
            WHERE Category IN ('Maintenance', 'General_Expense')
        """)
        conn.commit()
        logging.info("Existing records backfilled successfully.")

        # 3. Check if CK_ManualExpenses_KPI_Isolation constraint already exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = 'Rides' 
              AND TABLE_NAME = 'ManualExpenses' 
              AND CONSTRAINT_NAME = 'CK_ManualExpenses_KPI_Isolation'
        """)
        constraint_exists = cursor.fetchone()[0] > 0
        
        if not constraint_exists:
            logging.info("Adding CHECK constraint CK_ManualExpenses_KPI_Isolation...")
            cursor.execute("""
                ALTER TABLE Rides.ManualExpenses
                ADD CONSTRAINT CK_ManualExpenses_KPI_Isolation CHECK (
                    Category IN ('Maintenance', 'General_Expense')
                    OR IncludedInKPI = 1
                )
            """)
            conn.commit()
            logging.info("CHECK constraint CK_ManualExpenses_KPI_Isolation added successfully.")
        else:
            logging.info("CHECK constraint CK_ManualExpenses_KPI_Isolation already exists.")
            
        logging.info("Migration complete!")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
