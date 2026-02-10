
import os
import sys
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def check_today():
    sql = """
    SELECT 
        TripID, 
        TripType, 
        CAST(CreatedAt AS datetime2) as TripTime, 
        Classification,
        Earnings_Driver
    FROM Trips 
    WHERE CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Mountain Standard Time' AS DATE)
    """
    res = db.execute_query_with_results(sql)
    print(f"Total Trips Found for Today in SQL query: {len(res)}")
    for r in res:
        print(f"  {r['TripID']} | {r['TripType']} | {r['TripTime']} | {r['Classification']} | ${r['Earnings_Driver']}")

    # Check the View directly
    view_sql = "SELECT * FROM v_DailyKPIs"
    v_res = db.execute_query_with_results(view_sql)
    print("\nCONTENT OF v_DailyKPIs:")
    for v in v_res:
        print(f"  {v['Date']} | Revenue: {v['TotalEarnings']} | Trips: {v['TripCount']}")

    # Check weather
    weather_sql = "SELECT TOP 1 * FROM WeatherLog ORDER BY timestamp DESC"
    w = db.execute_query_with_results(weather_sql)
    print(f"\nLatest Weather: {w[0] if w else 'None'}")

if __name__ == "__main__":
    check_today()
