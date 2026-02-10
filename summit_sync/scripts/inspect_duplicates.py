import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def inspect_duplicates():
    query = "SELECT TripID, TripType, Classification, Earnings_Driver, SourceURL, CreatedAt FROM Trips WHERE CAST(CreatedAt AS DATE) >= '2026-01-30'"
    results = db.execute_query_with_results(query)
    
    print(f"--- Duplicate Audit: {len(results)} entries found ---")
    for r in results:
        url = r.get('SourceURL', '')
        filename = url.split('/')[-1] if url else 'N/A'
        print(f"ID: {r['TripID']} | Type: {r['TripType']} | Earn: ${r['Earnings_Driver']:.2f} | File: {filename}")

if __name__ == "__main__":
    inspect_duplicates()
