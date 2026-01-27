
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv(dotenv_path='summit_sync/.env')
conn_str = os.environ.get("SQL_CONNECTION_STRING")

def verify():
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    print("--- CLASSIFICATION DISTRIBUTION (Today) ---")
    query = "SELECT Classification, COUNT(*) FROM Trips WHERE CAST(CreatedAt AS DATE) = '2026-01-23' GROUP BY Classification"
    cursor.execute(query)
    for row in cursor.fetchall():
        print(f"Class: {row[0]} | Count: {row[1]}")

    print("\n--- SAMPLE TRIPS (Today) ---")
    query = """
    SELECT TOP 5 TripID, Classification, CreatedAt, Notes
    FROM Trips
    WHERE CAST(CreatedAt AS DATE) = '2026-01-23'
    ORDER BY CreatedAt DESC
    """
    cursor.execute(query)
    for row in cursor.fetchall():
        print(f"ID: {row.TripID} | Class: {row.Classification} | Created: {row.CreatedAt} | Snippet: {str(row.Notes)[:30]}")

    print("\n--- CHARGING SESSIONS (Today) ---")
    query = """
    SELECT TOP 5 SessionID, Location_Name, Energy_Added_kWh, Start_SOC, End_SOC, LastUpdated
    FROM ChargingSessions
    ORDER BY LastUpdated DESC
    """
    cursor.execute(query)
    for row in cursor.fetchall():
        print(f"ID: {row.SessionID} | Location: {row.Location_Name} | Energy: {row.Energy_Added_kWh} kWh | SOC: {row.Start_SOC}% -> {row.End_SOC}%")

    conn.close()

if __name__ == "__main__":
    verify()
