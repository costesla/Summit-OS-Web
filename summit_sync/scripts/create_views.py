
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
    # UNIONs historical dbo.Trips and new Rides.Rides table
    view_trip_reporting = """
    CREATE OR ALTER VIEW v_TripReporting AS
    SELECT 
        t.TripID,
        t.CreatedAt as TripTimestamp,
        CAST(t.CreatedAt AT TIME ZONE 'Mountain Standard Time' as DATE) as TripDateMST,
        DATEPART(hour, t.CreatedAt AT TIME ZONE 'Mountain Standard Time') as TripHourMST,
        t.TripType,
        t.Classification,
        t.Is_CDOT_Reportable,
        t.Earnings_Driver,
        t.Tip,
        t.Fare as TotalCustomerFare,
        t.Platform_Cut,
        t.Platform_Emoji,
        t.Payment_Method,
        t.Passenger_FirstName,
        t.Notes as Tessie_Tags,
        t.Pickup_Address_Full as Pickup,
        t.Dropoff_Address_Full as Dropoff,
        t.SourceURL,
        COALESCE(t.Tessie_Distance_Mi, t.Distance_mi, 0) as Distance_Miles,
        COALESCE(t.Tessie_Duration, t.Duration_min, 0) as Duration_Minutes,
        w.Temperature_F,
        w.Condition as WeatherCondition
    FROM Trips t
    OUTER APPLY (
        SELECT TOP 1 Temperature_F, Condition
        FROM WeatherLog w
        WHERE w.timestamp <= t.CreatedAt
        ORDER BY w.timestamp DESC
    ) w

    UNION ALL

    SELECT 
        r.RideID as TripID,
        r.Timestamp_Start as TripTimestamp,
        CAST(r.Timestamp_Start AT TIME ZONE 'Mountain Standard Time' as DATE) as TripDateMST,
        DATEPART(hour, r.Timestamp_Start AT TIME ZONE 'Mountain Standard Time') as TripHourMST,
        r.TripType,
        r.Classification,
        CASE WHEN r.TripType = 'Private' THEN 1 ELSE 0 END as Is_CDOT_Reportable,
        r.Driver_Earnings as Earnings_Driver,
        r.Tip,
        r.Fare as TotalCustomerFare,
        r.Platform_Cut,
        CASE 
            WHEN r.Platform_Cut > r.Driver_Earnings THEN '🟥'
            WHEN r.Driver_Earnings > r.Platform_Cut THEN '🟩'
            ELSE '🟨'
        END as Platform_Emoji,
        'Pending' as Payment_Method,
        COALESCE(JSON_VALUE(r.Sidecar_Artifact_JSON, '$.passenger_name'), 'Guest') as Passenger_FirstName,
        r.Sidecar_Artifact_JSON as Tessie_Tags,
        r.Pickup_Location as Pickup,
        r.Dropoff_Location as Dropoff,
        r.Source_URL as SourceURL,
        r.Distance_mi as Distance_Miles,
        r.Duration_min as Duration_Minutes,
        w.Temperature_F,
        w.Condition as WeatherCondition
    FROM Rides.Rides r
    OUTER APPLY (
        SELECT TOP 1 Temperature_F, Condition
        FROM Rides.WeatherLog w
        WHERE w.timestamp <= r.Timestamp_Start
        ORDER BY w.timestamp DESC
    ) w
    WHERE r.RideID LIKE 'TRIP-%' OR r.RideID LIKE 'INV-%'
    """

    # View 2: Daily Summary (Perfect for big KPI cards)
    # UNIONs historical dbo.Trips and new Rides.Rides table
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
        0 as TotalServiceFees,
        0 as TotalInsuranceFees
    FROM Trips
    GROUP BY CAST(CreatedAt AT TIME ZONE 'Mountain Standard Time' AS DATE)

    UNION ALL

    SELECT 
        CAST(Timestamp_Start AT TIME ZONE 'Mountain Standard Time' AS DATE) as [Date],
        SUM(CASE WHEN TripType != 'Expense' THEN COALESCE(Driver_Earnings, 0) ELSE 0 END) as TotalEarnings,
        SUM(COALESCE(Tip, 0)) as TotalTips,
        COUNT(CASE WHEN TripType != 'Expense' THEN RideID ELSE NULL END) as TripCount,
        MAX(CASE WHEN TripType != 'Expense' THEN Driver_Earnings ELSE NULL END) as HighestFare,
        0 as TotalExpenses,
        -- Compliance Metrics
        SUM(CASE WHEN TripType = 'Uber' THEN COALESCE(Platform_Cut, 0) ELSE 0 END) as TotalPlatformCut,
        0 as TotalServiceFees,
        0 as TotalInsuranceFees
    FROM Rides.Rides
    WHERE (RideID LIKE 'TRIP-%' OR RideID LIKE 'INV-%')
      -- Suppress duplicating days that are already present in legacy Trips (May 23rd and earlier)
      AND CAST(Timestamp_Start AS DATE) > '2026-05-23'
    GROUP BY CAST(Timestamp_Start AT TIME ZONE 'Mountain Standard Time' AS DATE)
    """

    # View 3: Master Trip Story with Weather
    view_master_trip_story = """
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

    UNION ALL

    SELECT 
        r.RideID as TripID,
        r.Timestamp_Start as TripTime,
        r.Driver_Earnings as Earnings_Driver,
        r.Tip,
        r.Distance_mi as Uber_Distance,
        r.Pickup_Location as Pickup_Place,
        w.Temperature_F,
        w.Condition as WeatherCondition,
        w.timestamp as WeatherTime
    FROM Rides.Rides r
    OUTER APPLY (
        SELECT TOP 1 Temperature_F, Condition, timestamp
        FROM Rides.WeatherLog w
        WHERE w.timestamp <= r.Timestamp_Start
        ORDER BY r.Timestamp_Start DESC
    ) w
    WHERE (r.RideID LIKE 'TRIP-%' OR r.RideID LIKE 'INV-%')
      AND CAST(r.Timestamp_Start AS DATE) > '2026-05-23'
    """

    try:
        logging.info("Creating v_TripReporting view...")
        db.execute_query(view_trip_reporting)
        
        logging.info("Creating v_DailyKPIs view...")
        db.execute_query(view_daily_summary)

        logging.info("Creating v_MasterTripStory view...")
        db.execute_query(view_master_trip_story)
        
        logging.info("Successfully created database views!")
    except Exception as e:
        logging.error(f"Failed to create views: {e}")

if __name__ == "__main__":
    setup_views()
