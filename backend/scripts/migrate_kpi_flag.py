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
    logging.info("Starting database migration for Rides.ManualExpenses strict KPI constraint...")
    
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        raise ConnectionError("Database connection failed.")
    cursor = conn.cursor()
    
    try:
        # 1. Column creation if not exists
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

        # 2. Backfill existing records
        logging.info("Backfilling capital maintenance records to IncludedInKPI = 0...")
        cursor.execute("""
            UPDATE Rides.ManualExpenses
            SET IncludedInKPI = 0
            WHERE Category IN ('Maintenance', 'General_Expense')
        """)
        conn.commit()

        logging.info("Backfilling operational records to IncludedInKPI = 1...")
        cursor.execute("""
            UPDATE Rides.ManualExpenses
            SET IncludedInKPI = 1
            WHERE Category NOT IN ('Maintenance', 'General_Expense')
        """)
        conn.commit()
        logging.info("Existing records backfilled successfully.")

        # 3. Verify safety (Fail-Fast Principle)
        logging.info("Verifying database safety constraints...")
        
        # Check for operational records with IncludedInKPI = 0
        cursor.execute("""
            SELECT COUNT(*) 
            FROM Rides.ManualExpenses
            WHERE Category NOT IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 0
        """)
        operational_with_zero = cursor.fetchone()[0]
        if operational_with_zero > 0:
            raise ValueError(
                f"DATABASE KPI CONTAMINATION: Detected {operational_with_zero} operational "
                f"records with IncludedInKPI = 0. Failing fast to protect financial integrity."
            )

        # Check for capital records with IncludedInKPI = 1
        cursor.execute("""
            SELECT COUNT(*) 
            FROM Rides.ManualExpenses
            WHERE Category IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 1
        """)
        capital_with_one = cursor.fetchone()[0]
        if capital_with_one > 0:
            raise ValueError(
                f"DATABASE KPI CONTAMINATION: Detected {capital_with_one} capital maintenance "
                f"records with IncludedInKPI = 1. Failing fast to protect financial integrity."
            )

        logging.info("Verification passed! No KPI contamination detected.")

        # 4. Drop existing constraint if it exists to allow update
        logging.info("Dropping existing CK_ManualExpenses_KPI_Isolation constraint if it exists...")
        cursor.execute("""
            IF EXISTS (
                SELECT * FROM sys.objects 
                WHERE object_id = OBJECT_ID(N'Rides.CK_ManualExpenses_KPI_Isolation') 
                  AND type = 'C'
            )
            ALTER TABLE Rides.ManualExpenses
            DROP CONSTRAINT CK_ManualExpenses_KPI_Isolation
        """)
        conn.commit()

        # 5. Create new strict check constraint
        logging.info("Adding new strict mutual CHECK constraint...")
        cursor.execute("""
            ALTER TABLE Rides.ManualExpenses
            ADD CONSTRAINT CK_ManualExpenses_KPI_Isolation CHECK (
                (Category IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 0)
                OR
                (Category NOT IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 1)
            )
        """)
        conn.commit()
        logging.info("Strict CHECK constraint applied successfully.")
        
        logging.info("Database migration successfully finished!")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
