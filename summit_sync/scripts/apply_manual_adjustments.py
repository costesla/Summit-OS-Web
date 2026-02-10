import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def update_private_earnings():
    # 1. Update Esmeralda (Milda)
    # The user said $24.00
    print("Updating Milda (Esmeralda) to $24.00...")
    query_milda = """
    UPDATE Trips 
    SET Earnings_Driver = 24.00, Rider_Payment = 24.00, Classification = 'Private_Trip', TripType = 'Private'
    WHERE (Passenger_FirstName LIKE '%Esmeralda%' OR Notes LIKE '%Esmeralda%')
    AND CAST(CreatedAt AS DATE) = '2026-01-30'
    """
    db.execute_non_query(query_milda)

    # 2. Update Jacuelyn (Jackie)
    # Gross: $70.00, Net: $68.57 (Venmo fee)
    print("Updating Jackie (Jacuelyn) to Gross: $70.00, Net: $68.57...")
    
    # Check if Jackie exists, if not we'll need to find the "Unknown" trip that might be her
    # or look for any trip matching the value if it was already close.
    # Given the user says "Jackie bundle", I'll look for her name first.
    
    query_jackie = """
    UPDATE Trips 
    SET Rider_Payment = 70.00, Earnings_Driver = 68.57, Uber_ServiceFee = 1.43, 
        Classification = 'Private_Trip', TripType = 'Private', Passenger_FirstName = 'Jacuelyn'
    WHERE (Passenger_FirstName LIKE '%Jacuelyn%' OR Passenger_FirstName LIKE '%Jackie%' OR Notes LIKE '%Jackie%')
    AND CAST(CreatedAt AS DATE) = '2026-01-30'
    """
    db.execute_non_query(query_jackie)
    
    print("✅ Financial adjustments applied for Jan 30th.")

if __name__ == "__main__":
    update_private_earnings()
