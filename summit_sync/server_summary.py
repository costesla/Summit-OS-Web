
import os
import pyodbc
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)
conn_str = os.environ.get("SQL_CONNECTION_STRING")

def summary_report():
    if not conn_str:
        print("SQL_CONNECTION_STRING not found.")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # 1. Total Counts
        cursor.execute("SELECT COUNT(*) FROM Trips")
        total_trips = cursor.fetchone()[0]
        
        cursor.execute("SELECT TripType, COUNT(*) FROM Trips GROUP BY TripType")
        type_counts = cursor.fetchall()
        
        # 2. Cross-Validation Stats
        cursor.execute("SELECT COUNT(*) FROM Trips WHERE Uber_Distance > 0 AND Tessie_Distance > 0")
        validated_trips = cursor.fetchone()[0]
        
        print("\n=== SERVER DATA SUMMARY (Azure SQL) ===")
        print(f"Total Records: {total_trips}")
        print("-" * 40)
        for ttype, count in type_counts:
            print(f"- {ttype:<12}: {count}")
        print("-" * 40)
        print(f"Cross-Validated (Uber+Tesla): {validated_trips}")
        
        print("\nLatest 5 Entries:")
        cursor.execute("SELECT TOP 5 TripID, TripType, CreatedAt FROM Trips ORDER BY CreatedAt DESC")
        for row in cursor.fetchall():
            print(f"  [{row.CreatedAt}] {row.TripID} ({row.TripType})")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    summary_report()
