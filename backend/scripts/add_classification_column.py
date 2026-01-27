
import os
import sys
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def add_column():
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found.")
        return

    print("Connecting to SQL to add 'Classification' column...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Check if column exists first to avoid error
        query = """
        IF NOT EXISTS (
            SELECT * FROM sys.columns 
            WHERE object_id = OBJECT_ID(N'dbo.Trips') 
            AND name = 'Classification'
        )
        BEGIN
            ALTER TABLE dbo.Trips ADD Classification NVARCHAR(50);
            PRINT 'Column added successfully.';
        END
        ELSE
        BEGIN
            PRINT 'Column already exists.';
        END
        """
        
        cursor.execute(query)
        conn.commit()
        print("Schema update completed.")
        
    except Exception as e:
        print(f"Failed to update schema: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    add_column()
