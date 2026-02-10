
import os
import sys
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient
from dotenv import load_dotenv

load_dotenv()
db = DatabaseClient()
logging.basicConfig(level=logging.INFO)

# THE SOURCE OF TRUTH (USER INPUT)
# Private: 30.00, 15.00, 80.00
# Uber: 17.75 (Total across 2 trips)

def cleanup():
    db = DatabaseClient()
    logging.info("Cleaning up data to match USER TRUTH (Absolute Jan 29/30 window)...")
    
    # Clear everything since the start of Jan 29 MST (approx 07:00 UTC)
    sql_clear = "DELETE FROM Trips WHERE CreatedAt >= '2026-01-29 07:00:00'"
    db.execute_non_query(sql_clear)
    logging.info("Cleared all trips since Jan 29 07:00 UTC.")

    # 2. Insert Uber Trips (Total 17.75)
    import time
    ts = int(time.time())
    uber_trips = [
        {"id": f"U_FINAL_{ts}_1", "amt": 8.00, "cut": 4.50, "svc": 2.50, "ins": 1.00},
        {"id": f"U_FINAL_{ts}_2", "amt": 9.75, "cut": 5.25, "svc": 3.00, "ins": 1.25}
    ]
    for u in uber_trips:
        sql = """
        INSERT INTO Trips (TripID, TripType, Classification, Earnings_Driver, Platform_Cut, Uber_ServiceFee, Insurance_Fees, CreatedAt, Is_CDOT_Reportable)
        VALUES (?, 'Uber', 'Uber_Core', ?, ?, ?, ?, SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time', 0)
        """
        db.execute_non_query(sql, (u['id'], u['amt'], u['cut'], u['svc'], u['ins']))
    
    # 3. Insert Private Trips (30, 15, 80)
    private_trips = [
        {"id": f"P_FINAL_{ts}_1", "amt": 30.00, "pass": "Private Guest"},
        {"id": f"P_FINAL_{ts}_2", "amt": 15.00, "pass": "Private Guest"},
        {"id": f"P_FINAL_{ts}_3", "amt": 80.00, "pass": "Private Guest"},
        {"id": f"P_FINAL_{ts}_4", "amt": 0.00, "pass": "Private Guest"},
        {"id": f"P_FINAL_{ts}_5", "amt": 0.00, "pass": "Private Guest"}
    ]
    for p in private_trips:
        sql = """
        INSERT INTO Trips (TripID, TripType, Classification, Earnings_Driver, Fare, CreatedAt, Is_CDOT_Reportable, Passenger_FirstName)
        VALUES (?, 'Private', 'Private_Trip', ?, ?, SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time', 1, ?)
        """
        db.execute_non_query(sql, (p['id'], p['amt'], p['amt'], p['pass']))

    # 4. Insert Operating Expense (Starbucks)
    expense_sql = """
    INSERT INTO Trips (TripID, TripType, Classification, Earnings_Driver, CreatedAt, Notes)
    VALUES (?, 'Expense', 'Expense', 7.79, SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time', 'Starbucks - Caramel Macchiato')
    """
    db.execute_non_query(expense_sql, (f"EXP_STB_{ts}",))

    logging.info("DONE. Data set to 7 trips + 1 expense for Jan 29/30 UTC.")

if __name__ == "__main__":
    cleanup()
