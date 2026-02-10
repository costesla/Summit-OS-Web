import sys
import os
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def final_cleanup():
    # 1. Price Milda at $24.00 Total (User said $24, so we average across the 4 entries found)
    # or just set one to $24 and others to $0. I'll distribute it to keep total at $24.
    ids = ['T32553a7e', 'T3a5bd444', 'T88524432', 'Tbbb44947']
    print(f"Distributing Milda's $24 across {len(ids)} segments...")
    for i, tid in enumerate(ids):
        val = 24.00 if i == 0 else 0.00
        db.execute_non_query("UPDATE Trips SET Earnings_Driver = ?, Rider_Payment = ? WHERE TripID = ?", (val, val, tid))

    # 2. Add Jackie's manual entry since OCR missed her name context
    # Create a clean entry for the bundle
    jackie_data = {
        "trip_id": "M_JACKIE_JAN30",
        "classification": "Private_Trip",
        "fare": 70.00,
        "tip": 0.00,
        "rider_payment": 70.00,
        "driver_total": 68.57,
        "uber_cut": 1.43,
        "payment_method": "Venmo",
        "start_location": "Manual Entry",
        "end_location": "Manual Entry",
        "timestamp_epoch": datetime.now().timestamp(),
        "raw_text": "Jackie Bundle: $70 Gross, $68.57 Net (Venmo Fee)",
        "passenger_firstname": "Jacuelyn",
        "is_cdot_reportable": True
    }
    print("Adding Jackie's $70.00 Bundle...")
    db.save_trip(jackie_data)
    
    print("✅ Final financial polish complete.")

if __name__ == "__main__":
    final_cleanup()
