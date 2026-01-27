
import os
import pyodbc
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        print("SQL_CONNECTION_STRING not found.")
        return

    print("Connecting to SQL for migration...")
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    try:
        print("Adding 'Classification' column to 'Trips' table...")
        # Check if column exists first
        check_col = "SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Trips') AND name = 'Classification'"
        cursor.execute(check_col)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE Trips ADD Classification NVARCHAR(50);")
            conn.commit()
            print("Migration successful: 'Classification' column added.")
        else:
            print("Column 'Classification' already exists. Skipping.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
