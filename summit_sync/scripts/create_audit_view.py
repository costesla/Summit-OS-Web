import logging
import os
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def create_audit_view():
    load_dotenv()
    db = DatabaseClient()
    logging.basicConfig(level=logging.INFO)
    
    logging.info("Creating v_CDOT_Compliance_Audit View...")

    query = """
    CREATE OR ALTER VIEW v_CDOT_Compliance_Audit AS
    SELECT 
        Format(CreatedAt, 'yyyy-MM-dd') AS [Date],
        Format(CreatedAt, 'HH:mm:ss') AS [Time],
        Passenger_FirstName AS [Passenger],
        Pickup_Address_Full AS [Pickup_Location],
        Dropoff_Address_Full AS [Dropoff_Location],
        Tessie_Distance_Mi AS [Distance_Miles],
        Fare AS [Fare_Amount],
        Insurance_Fees AS [Fees_Surcharges],
        Payment_Method AS [Payment_Type],
        TripID AS [Reference_ID]
    FROM Trips
    WHERE Is_CDOT_Reportable = 1
    """

    try:
        db.execute_query(query)
        logging.info("Successfully created view v_CDOT_Compliance_Audit")
        
        # Verify
        res = db.execute_query_with_results("SELECT TOP 5 * FROM v_CDOT_Compliance_Audit")
        logging.info(f"Sample Data: {res}")
        
    except Exception as e:
        logging.error(f"Failed to create view: {e}")

if __name__ == "__main__":
    create_audit_view()
