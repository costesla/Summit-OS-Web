import os
import datetime
from lib.database import DatabaseClient
from dotenv import load_dotenv

def verify_data_detailed():
    load_dotenv()
    db = DatabaseClient()
    
    query = """
    SELECT TripID, Timestamp_Offer, TripType, Classification, Fare, Earnings_Driver, SourceURL
    FROM Trips 
    WHERE Timestamp_Offer >= '2026-02-06 00:00:00' AND Timestamp_Offer < '2026-02-07 00:00:00'
    ORDER BY Timestamp_Offer
    """
    
    print("--- Detailed Trip Data (Feb 6) ---")
    results = db.execute_query_with_results(query)
    
    if results:
        print(f"{'TripID':<15} | {'Time':<20} | {'Type':<10} | {'Class':<15} | {'Fare':<8} | {'Earn':<8} | {'Source':<30}")
        print("-" * 120)
        for row in results:
            src = row.get('SourceURL', '')
            # Truncate source for display
            if len(src) > 30: src = "..." + src[-27:]
            
            print(f"{str(row.get('TripID'))[:15]:<15} | {str(row.get('Timestamp_Offer')):<20} | {str(row.get('TripType')):<10} | {str(row.get('Classification')):<15} | {row.get('Fare'):<8} | {row.get('Earnings_Driver'):<8} | {src:<30}")
    else:
        print("No trips found.")

if __name__ == "__main__":
    verify_data_detailed()
