import logging
import os
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def migrate_compliance_schema():
    load_dotenv()
    db = DatabaseClient()
    logging.basicConfig(level=logging.INFO)
    
    logging.info("Starting CDOT Compliance Schema Migration...")

    commands = [
        # 1. Is_CDOT_Reportable
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Is_CDOT_Reportable')
        BEGIN
            ALTER TABLE Trips ADD Is_CDOT_Reportable BIT NOT NULL DEFAULT 0;
            PRINT 'Added Is_CDOT_Reportable';
        END
        """,
        # 2. Tessie_Distance_Mi
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Tessie_Distance_Mi')
        BEGIN
            ALTER TABLE Trips ADD Tessie_Distance_Mi DECIMAL(10, 2);
            PRINT 'Added Tessie_Distance_Mi';
        END
        """,
        # 3. Pickup_Address_Full
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Pickup_Address_Full')
        BEGIN
            ALTER TABLE Trips ADD Pickup_Address_Full NVARCHAR(500);
            PRINT 'Added Pickup_Address_Full';
        END
        """,
        # 4. Dropoff_Address_Full
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Dropoff_Address_Full')
        BEGIN
            ALTER TABLE Trips ADD Dropoff_Address_Full NVARCHAR(500);
            PRINT 'Added Dropoff_Address_Full';
        END
        """,
        # 5. Passenger_FirstName
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Passenger_FirstName')
        BEGIN
            ALTER TABLE Trips ADD Passenger_FirstName NVARCHAR(100);
            PRINT 'Added Passenger_FirstName';
        END
        """,
        # 6. Insurance_Fees
        """
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips' AND COLUMN_NAME = 'Insurance_Fees')
        BEGIN
            ALTER TABLE Trips ADD Insurance_Fees DECIMAL(19, 4);
            PRINT 'Added Insurance_Fees';
        END
        """
    ]

    try:
        for cmd in commands:
            db.execute_query(cmd)
        logging.info("Migration commands executed successfully.")
        
        # Verify
        check_query = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'Trips' 
        AND COLUMN_NAME IN ('Is_CDOT_Reportable', 'Tessie_Distance_Mi', 'Pickup_Address_Full', 'Passenger_FirstName')
        """
        results = db.execute_query_with_results(check_query)
        found_cols = [row['COLUMN_NAME'] for row in results]
        logging.info(f"Verified Columns: {found_cols}")
        
    except Exception as e:
        logging.error(f"Migration Failed: {e}")

if __name__ == "__main__":
    migrate_compliance_schema()
