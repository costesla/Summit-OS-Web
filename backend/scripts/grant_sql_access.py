
from lib.database import DatabaseClient
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

def grant_access():
    db = DatabaseClient()
    
    # The Principal Name for a System-Assigned Identity is usually the name of the Function App
    identity_name = "summitsyncfuncus23436"
    
    # SQL to create a user from the external provider and grant permissions
    sql = f"""
    IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = '{identity_name}')
    BEGIN
        CREATE USER [{identity_name}] FROM EXTERNAL PROVIDER;
        ALTER ROLE db_datareader ADD MEMBER [{identity_name}];
        ALTER ROLE db_datawriter ADD MEMBER [{identity_name}];
    END
    """
    
    try:
        logging.info(f"Granting access to Managed Identity: {identity_name}")
        db.execute_query(sql)
        logging.info("Successfully granted SQL permissions!")
    except Exception as e:
        logging.error(f"Failed to grant permissions: {e}")
        logging.info("Note: This often requires the script runner to be the SQL AD Admin.")

if __name__ == "__main__":
    grant_access()
