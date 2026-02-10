import sys
import os
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def rebuild_ledger():
    print("🧹 Nuclear Reset: Clearing Jan 30th ledger...")
    # Delete all trips for Jan 30/31 (to handle UTC spillover)
    db.execute_non_query("DELETE FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'")
    
    # 1. ACTUAL UBER TRIPS (7)
    uber_trips = [
        {"id": "UB_1", "earn": 15.17, "note": "Uber Trip 1"},
        {"id": "UB_2", "earn": 14.79, "note": "Uber Trip 2"},
        {"id": "UB_3", "earn": 17.30, "note": "Uber Trip 3"},
        {"id": "UB_4", "earn": 10.13, "note": "Uber Trip 4"},
        {"id": "UB_5", "earn": 7.80,  "note": "Uber Trip 5"},
        {"id": "UB_6", "earn": 5.27,  "note": "Uber Trip 6"},
        {"id": "UB_7", "earn": 9.98,  "note": "Upfront @ 11:58 AM - Cave of the Winds", "ts": "2026-01-30 11:58:00"}
    ]
    
    for u in uber_trips:
        data = {
            "trip_id": u["id"],
            "classification": "Uber_Core",
            "driver_total": u["earn"],
            "rider_payment": u["earn"] * 1.6, # Estimating gross for metrics
            "timestamp_epoch": datetime.strptime(u.get("ts", "2026-01-30 12:00:00"), "%Y-%m-%d %H:%M:%S").timestamp(),
            "raw_text": u["note"],
            "is_cdot_reportable": False
        }
        db.save_trip(data)
        print(f" ✅ Saved Uber: ${u['earn']}")

    # 2. ACTUAL PRIVATE TRIPS (5)
    # Milda ($24) and Jackie ($68.57) are confirmed. I'll add them first.
    private_trips = [
        {"id": "PV_MILDA", "pass": "Esmeralda", "gross": 24.00, "net": 24.00, "fee": 0, "note": "Milda Payout"},
        {"id": "PV_JACKIE", "pass": "Jacuelyn", "gross": 70.00, "net": 68.57, "fee": 1.43, "note": "Jackie Bundle"},
    ]
    
    for p in private_trips:
        data = {
            "trip_id": p["id"],
            "classification": "Private_Trip",
            "driver_total": p["net"],
            "rider_payment": p["gross"],
            "uber_cut": p["fee"], # Using cut field for fees
            "passenger_firstname": p["pass"],
            "payment_method": "Venmo",
            "is_cdot_reportable": True,
            "raw_text": p["note"],
            "timestamp_epoch": datetime.now().timestamp()
        }
        db.save_trip(data)
        print(f" ✅ Saved Private: {p['pass']} (${p['net']})")

    print("\n⚠️ NOTE: 3 Private Trips are currently missing details. Total of 9 trips logged.")

if __name__ == "__main__":
    rebuild_ledger()
