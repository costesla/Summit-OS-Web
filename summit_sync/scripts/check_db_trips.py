import logging
import sys
import os
from datetime import datetime, date
# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient
from dotenv import load_dotenv

def check_today_trips():
    load_dotenv()
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        print("No DB connection.")
        return

    cursor = conn.cursor()
    
    # Query for today's trips
    today_str = date.today().strftime('%Y-%m-%d')
    query = f"""
    SELECT TripID, TripType, CustomerName, Fare, Tip, DriveID, CreatedAt, StartLocation, EndLocation
    FROM Trips 
    WHERE CreatedAt >= '{today_str}'
    ORDER BY CreatedAt DESC
    """
    
    try:
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        
        print(f"Found {len(rows)} trips created today:")
        print("--------------------------------------------------")
        for row in rows:
            data = dict(zip(columns, row))
            print(f"ID: {data['TripID']} | Type: {data['TripType']} | Fare: ${data['Fare']} | Tip: ${data['Tip']} | Cust: {data['CustomerName']}")
            print(f"  Created: {data['CreatedAt']} | Route: {data['StartLocation']} -> {data['EndLocation']}")
        print("--------------------------------------------------")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_today_trips()
