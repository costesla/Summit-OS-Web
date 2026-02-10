import sys
import os
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def debug_and_calculate():
    # 1. Broadest possible check for today
    query = "SELECT TripType, Earnings_Driver, CreatedAt FROM Trips"
    results = db.execute_query_with_results(query)
    
    print(f"Total entries in database: {len(results)}")
    
    uber_total = 0
    private_total = 0
    uber_count = 0
    private_count = 0
    
    # Python-side filtering to avoid SQL syntax issues during debug
    from datetime import datetime
    today = "2026-01-30"
    
    for row in results:
        # Check if CreatedAt exists and matches today
        created = str(row.get('CreatedAt', ''))
        if today in created:
            earnings = float(row.get('Earnings_Driver') or 0)
            t_type = row.get('TripType', '')
            
            if t_type == 'Uber':
                uber_total += earnings
                uber_count += 1
            else:
                private_total += earnings
                private_count += 1
                
    print("\n--- Final Earnings Audit: Jan 30, 2026 ---")
    print(f" > Uber Trips   ({uber_count}): ${uber_total:.2f}")
    print(f" > Private Trips ({private_count}): ${private_total:.2f}")
    print("-" * 35)
    print(f"TOTAL EARNINGS Today: ${(uber_total + private_total):.2f}")
    print("-" * 35)

if __name__ == "__main__":
    debug_and_calculate()
