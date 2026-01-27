
import os
import sys
import logging
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def log_cash_trip():
    print("--- Summit Sync: Manual Cash Trip Entry ---")
    
    fare = float(input("Enter Fare Amount (e.g. 25.00): ") or 0)
    tip = float(input("Enter Tip Amount (e.g. 5.00): ") or 0)
    pickup = input("Enter Pickup Location (Optional): ") or "Manual Entry"
    dropoff = input("Enter Dropoff Location (Optional): ") or "Manual Entry"
    notes = input("Enter any notes: ") or "Cash Payment"
    
    # Generate a unique Trip ID
    trip_id = f"CASH-{uuid.uuid4().hex[:8].upper()}"
    
    trip_data = {
        "trip_id": trip_id,
        "classification": "Private_Trip",
        "fare": fare,
        "tip": tip,
        "rider_payment": fare + tip,
        "driver_total": fare + tip,
        "uber_cut": 0.0,
        "payment_method": "Cash",
        "start_location": pickup,
        "end_location": dropoff,
        "timestamp_epoch": datetime.now().timestamp(),
        "raw_text": notes
    }
    
    logging.info(f"Logging cash trip {trip_id} for ${fare + tip:.2f}...")
    
    db = DatabaseClient()
    try:
        db.save_trip(trip_data)
        print(f"\n✅ Successfully logged cash trip: {trip_id}")
    except Exception as e:
        logging.error(f"Failed to log cash trip: {e}")

if __name__ == "__main__":
    try:
        log_cash_trip()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except ValueError:
        print("\nInvalid input. Please enter numbers for Fare and Tip.")
