
from lib.database import DatabaseClient
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logging.basicConfig(level=logging.INFO)

def setup_views():
    db = DatabaseClient()
    
    # View 1: Trips with Weather (matches the closest weather record prior to the trip)
    view_trips_weather = """
    CREATE OR ALTER VIEW v_MasterTripStory AS
    SELECT 
        t.TripID,
        t.CreatedAt as TripTime,
        t.Earnings_Driver,
        t.Tip,
        t.Uber_Distance,
        t.Pickup_Place,
        w.Temperature_F,
        w.Condition as WeatherCondition,
        w.timestamp as WeatherTime
    FROM Trips t
    OUTER APPLY (
        SELECT TOP 1 Temperature_F, Condition, timestamp
        FROM WeatherLog w
        WHERE w.timestamp <= t.CreatedAt
        ORDER BY w.timestamp DESC
    ) w
    """

    # View 2: Daily Summary (Perfect for big KPI cards)
    view_daily_summary = """
    CREATE OR ALTER VIEW v_DailyKPIs AS
    SELECT 
        CAST(CreatedAt AS DATE) as Date,
        SUM(Earnings_Driver) as TotalEarnings,
        SUM(Tip) as TotalTips,
        COUNT(TripID) as TripCount,
        MAX(Earnings_Driver) as HighestFare
    FROM Trips
    GROUP BY CAST(CreatedAt AS DATE)
    """

    try:
        logging.info("Creating v_MasterTripStory view...")
        db.execute_query(view_trips_weather)
        
        logging.info("Creating v_DailyKPIs view...")
        db.execute_query(view_daily_summary)
        
        logging.info("Successfully created database views!")
    except Exception as e:
        logging.error(f"Failed to create views: {e}")

if __name__ == "__main__":
    setup_views()
