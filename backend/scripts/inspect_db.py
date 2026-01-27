
import os
import pyodbc
from dotenv import load_dotenv

# Setup
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)
conn_str = os.environ.get("SQL_CONNECTION_STRING")

def inspect_db():
    if not conn_str:
        print("SQL_CONNECTION_STRING not found.")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 10 
            TripID, TripType, Uber_Distance, Tessie_Distance, Rider_Payment, Earnings_Driver, CreatedAt, Tessie_DriveID
        FROM Trips 
        ORDER BY CreatedAt DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'TripID':<15} | {'Type':<8} | {'UberDist':<10} | {'TesDist':<10} | {'Pay':<8} | {'Earn':<8} | {'CreatedAt':<20} | {'DriveID'}")
        print("-" * 110)
        
        for row in rows:
            created_at = row.CreatedAt.strftime('%Y-%m-%d %H:%M:%S') if row.CreatedAt else "None"
            print(f"{str(row.TripID)[:15]:<15} | {str(row.TripType):<8} | {str(row.Uber_Distance):<10} | {str(row.Tessie_Distance):<10} | {str(row.Rider_Payment):<8} | {str(row.Earnings_Driver):<8} | {created_at:<20} | {row.Tessie_DriveID}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    inspect_db()
