
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()
conn_str = os.environ.get("SQL_CONNECTION_STRING")

def check_db():
    if not conn_str:
        print("SQL_CONNECTION_STRING not found.")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        print("Checking _probe table...")
        try:
            cursor.execute("SELECT COUNT(*) FROM _probe")
            count = cursor.fetchone()[0]
            print(f"Records in _probe: {count}")
            if count > 0:
                cursor.execute("SELECT TOP 5 * FROM _probe ORDER BY id DESC")
                for row in cursor.fetchall():
                    print(row)
        except Exception as e:
            print(f"Error checking _probe: {e}")

        print("\nChecking Trips table...")
        try:
            cursor.execute("SELECT COUNT(*) FROM Trips")
            count = cursor.fetchone()[0]
            print(f"Records in Trips: {count}")
            
            cursor.execute("SELECT TOP 5 TripID, CreatedAt, Distance_mi FROM Trips ORDER BY CreatedAt DESC")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
        except Exception as e:
            print(f"Error checking Trips: {e}")

    except Exception as e:
        print(f"Error connecting to DB: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_db()
