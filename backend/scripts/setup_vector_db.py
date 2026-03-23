import os
import sys
import logging
from dotenv import load_dotenv

# Load env variables for local execution
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

# Add backend to path so we can import services
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.database import DatabaseClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_system_vectors_table():
    client = DatabaseClient()
    conn = client.get_connection()
    
    if not conn:
        logging.error("Failed to connect to the database to setup System_Vectors.")
        sys.exit(1)
        
    cursor = conn.cursor()
    
    sql = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'System_Vectors')
    BEGIN
        CREATE TABLE System_Vectors (
            vector_id NVARCHAR(128) PRIMARY KEY,
            source_type NVARCHAR(50) NOT NULL CHECK (source_type IN ('FSD', 'Passenger', 'Financial', 'Operations', 'Compliance')),
            timestamp_utc DATETIME2 NOT NULL,
            vehicle_id NVARCHAR(128) NOT NULL,
            driver_id NVARCHAR(128) NOT NULL, -- Hashed
            confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
            embedding_model_version NVARCHAR(50) NOT NULL,
            raw_text_hash NVARCHAR(128) NOT NULL,
            source_pointer NVARCHAR(256) NOT NULL,
            derivation_reason NVARCHAR(MAX) NOT NULL,
            embedding VECTOR(1536) NOT NULL,
            created_at DATETIME2 DEFAULT GETUTCDATE()
        );
        PRINT 'System_Vectors table created successfully.';
    END
    ELSE
    BEGIN
        PRINT 'System_Vectors table already exists.';
    END
    """
    
    try:
        cursor.execute(sql)
        conn.commit()
        logging.info("Schema setup script completed successfully.")
    except Exception as e:
        logging.error(f"Error creating System_Vectors table: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    setup_system_vectors_table()
