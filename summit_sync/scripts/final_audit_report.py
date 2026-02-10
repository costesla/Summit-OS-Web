import sys
import os
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def final_audit():
    # Fetch all to see what's actually in there
    query = "SELECT TripID, TripType, Passenger_FirstName, Earnings_Driver, CreatedAt FROM Trips"
    results = db.execute_query_with_results(query)
    
    print(f"Total Database Rows: {len(results)}")
    
    # Include Feb 1st since manual rebuild happened today
    dates = ["2026-01-30", "2026-01-31", "2026-02-01"]
    
    grand_total = 0
    breakdown = {"Uber": 0, "Private": 0}
    counts = {"Uber": 0, "Private": 0}
    
    for row in results:
        created = str(row.get('CreatedAt', ''))
        # Check if it matches any date
        if any(d in created for d in dates):
            t_type = row.get('TripType', 'Unknown')
            earnings = float(row.get('Earnings_Driver') or 0)
            
            if t_type == 'Uber':
                breakdown["Uber"] += earnings
                counts["Uber"] += 1
            else:
                breakdown["Private"] += earnings
                counts["Private"] += 1
            
            grand_total += earnings

    print("\n--- SUMMIT MISSION REPORT: JAN 30-31 ---")
    print(f" > UBER REVENUE   ({counts['Uber']:2} Trips): ${breakdown['Uber']:8.2f}")
    print(f" > PRIVATE REVENUE ({counts['Private']:2} Trips): ${breakdown['Private']:8.2f}")
    print("-" * 40)
    print(f"   GRAND TOTAL EARNED:    ${grand_total:8.2f}")
    print("-" * 40)
    
    if grand_total == 0:
        print("\nDEBUG: Recent timestamps in DB:")
        sorted_results = sorted(results, key=lambda x: str(x.get('CreatedAt', '')), reverse=True)
        for r in sorted_results[:10]:
            print(f"ID: {r.get('TripID')} | Type: {r.get('TripType')} | Created: {r.get('CreatedAt')} | Earnings: {r.get('Earnings_Driver')}")

if __name__ == "__main__":
    final_audit()
