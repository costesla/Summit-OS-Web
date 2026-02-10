import sys
import os
from dotenv import load_dotenv

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def calculate_daily_earnings():
    # Use MST date filter
    query = """
    SELECT 
        TripType, 
        SUM(Earnings_Driver) as TotalEarnings,
        COUNT(TripID) as TripCount
    FROM Trips 
    WHERE CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE) = '2026-01-30'
    GROUP BY TripType
    """
    
    results = db.execute_query_with_results(query)
    
    print("\n--- Final Earnings Audit: Jan 30, 2026 (MST) ---")
    grand_total = 0
    for row in results:
        t_type = row['TripType']
        earnings = float(row['TotalEarnings'] or 0)
        count = row['TripCount']
        print(f" > {t_type:8}: ${earnings:8.2f} ({count} entries)")
        grand_total += earnings
    
    print("-" * 45)
    print(f"TOTAL EARNINGS: ${grand_total:8.2f}")
    print("-" * 45)

if __name__ == "__main__":
    calculate_daily_earnings()
