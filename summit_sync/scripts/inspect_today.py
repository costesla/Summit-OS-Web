import logging
import os
import sys
import json
from datetime import date

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def inspect_today_details():
    load_dotenv()
    db = DatabaseClient()
    
    print("--- Inspecting Trips for Today ---")
    try:
        # Get all columns for today's trips to see what's going on
        query = """
        SELECT TripID, TripType, CreatedAt, Fare, Tip, Earnings_Driver, Rider_Payment 
        FROM Trips 
        WHERE CAST(CreatedAt AS DATE) = CAST(GETDATE() AS DATE)
        ORDER BY CreatedAt DESC
        """
        results = db.execute_query_with_results(query)
        
        if results:
            print(f"Found {len(results)} trips.")
            for row in results:
                print(f"ID: {row['TripID']} | Type: {row['TripType']} | Earn: ${row['Earnings_Driver']} | Tip: ${row['Tip']} | Date: {row['CreatedAt']}")
        else:
            print("No trips found for today.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_today_details()
