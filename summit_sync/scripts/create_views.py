
import logging
import os
import sys
# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logging.basicConfig(level=logging.INFO)

def setup_views():
    db = DatabaseClient()
    
    # View 1: Trips with Weather (matches the closest weather record prior to the trip)
    view_trip_reporting = """
    CREATE OR ALTER VIEW v_TripReporting AS
    SELECT 
        -- Core IDs and Time
        t.TripID,
        t.CreatedAt as TripTimestamp,
        CAST(t.CreatedAt AT TIME ZONE 'Mountain Standard Time' as DATE) as TripDateMST,
        DATEPART(hour, t.CreatedAt AT TIME ZONE 'Mountain Standard Time') as TripHourMST,

        -- Classification
        t.TripType,      -- 'Uber' or 'Private'
        t.Classification, -- 'Uber_Core', 'Private_Trip', etc.
        t.Is_CDOT_Reportable,

        -- Financials
        t.Earnings_Driver,
        t.Tip,
        t.Fare as TotalCustomerFare,
        t.Platform_Cut,
        t.Platform_Emoji,
        t.Payment_Method, -- 'Venmo', 'Cash', etc.

        -- Context
        t.Passenger_FirstName,
        t.Notes as Tessie_Tags,
        t.Pickup_Address_Full as Pickup,
        t.Dropoff_Address_Full as Dropoff,
        t.SourceURL,

        -- Telemetry (Prioritize Tessie, fallback to Uber)
        COALESCE(t.Tessie_Distance_Mi, t.Distance_mi, 0) as Distance_Miles,
        COALESCE(t.Tessie_Duration, t.Duration_min, 0) as Duration_Minutes,

        -- Weather Context (correlated closest record)
        w.Temperature_F,
        w.Condition as WeatherCondition

    FROM Trips t
    OUTER APPLY (
        SELECT TOP 1 Temperature_F, Condition
        FROM WeatherLog w
        WHERE w.timestamp <= t.CreatedAt
        ORDER BY w.timestamp DESC
    ) w
    """

    # View 2: Daily Summary (Perfect for big KPI cards)
    view_daily_summary = """
    CREATE OR ALTER VIEW v_DailyKPIs AS
    SELECT 
        CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE) as [Date],
        SUM(CASE WHEN TripType != 'Expense' THEN COALESCE(Earnings_Driver, 0) ELSE 0 END) as TotalEarnings,
        SUM(COALESCE(Tip, 0)) as TotalTips,
        COUNT(CASE WHEN TripType != 'Expense' THEN TripID ELSE NULL END) as TripCount,
        MAX(CASE WHEN TripType != 'Expense' THEN Earnings_Driver ELSE NULL END) as HighestFare,
        SUM(CASE WHEN TripType = 'Expense' THEN COALESCE(Earnings_Driver, 0) ELSE 0 END) as TotalExpenses,
        -- Compliance Metrics
        SUM(CASE WHEN TripType = 'Uber' THEN COALESCE(Platform_Cut, 0) ELSE 0 END) as TotalPlatformCut,
        SUM(CASE WHEN TripType = 'Uber' THEN COALESCE(Uber_ServiceFee, 0) ELSE 0 END) as TotalServiceFees,
        SUM(CASE WHEN TripType = 'Uber' THEN COALESCE(Insurance_Fees, 0) ELSE 0 END) as TotalInsuranceFees
    FROM Trips
    GROUP BY CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE)
    """

    try:
        logging.info("Creating v_TripReporting view...")
        db.execute_query(view_trip_reporting)
        
        logging.info("Creating v_DailyKPIs view...")
        db.execute_query(view_daily_summary)
        
        logging.info("Successfully created database views!")
    except Exception as e:
        logging.error(f"Failed to create views: {e}")

if __name__ == "__main__":
    setup_views()
