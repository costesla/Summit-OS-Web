import os
import sys
import logging
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.database import DatabaseClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_powerbi_view():
    """
    Creates a secure, read-only SQL View for Power BI. 
    Explicitly strips out raw_text_hash, driver_id, and raw embeddings to ensure
    absolute zero PII leakage to analytical dashboards.
    """
    client = DatabaseClient()
    conn = client.get_connection()
    
    if not conn:
        logging.error("Failed to connect to the database to setup PowerBI View.")
        sys.exit(1)
        
    cursor = conn.cursor()
    
    sql = """
    CREATE OR ALTER VIEW vw_PowerBI_FSD_Insights AS
    SELECT 
        vector_id,
        source_type,
        timestamp_utc,
        vehicle_id,
        confidence_score,
        source_pointer,
        derivation_reason,
        created_at
    FROM 
        System_Vectors
    WHERE 
        source_type = 'FSD'
    """
    
    try:
        cursor.execute(sql)
        conn.commit()
        logging.info("vw_PowerBI_FSD_Insights created successfully. Power BI can now safely attach to this view.")
    except Exception as e:
        logging.error(f"Error creating Power BI View: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    setup_powerbi_view()
