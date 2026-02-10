-- Summit Mobility Intelligence Copilot: SQL Schema Update V2
-- Adds Energy Metrics and Copilot Views

-- 1. Alter Rides.Rides Table
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'Rides' AND COLUMN_NAME = 'Start_SOC')
BEGIN
    ALTER TABLE Rides.Rides ADD Start_SOC DECIMAL(5,2);
END

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'Rides' AND COLUMN_NAME = 'End_SOC')
BEGIN
    ALTER TABLE Rides.Rides ADD End_SOC DECIMAL(5,2);
END

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'Rides' AND COLUMN_NAME = 'Energy_Used_kWh')
BEGIN
    ALTER TABLE Rides.Rides ADD Energy_Used_kWh DECIMAL(10,2);
END

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'Rides' AND COLUMN_NAME = 'Efficiency_Wh_mi')
BEGIN
    ALTER TABLE Rides.Rides ADD Efficiency_Wh_mi DECIMAL(10,2);
END
GO

-- 2. Create View: Reports.MobilityEvents
-- Unifies Trips and Charging Sessions into a single timeline for the Copilot
CREATE OR ALTER VIEW Reports.MobilityEvents AS
SELECT 
    RideID AS EventID,
    Timestamp_Start AT TIME ZONE 'UTC' AT TIME ZONE 'Mountain Standard Time' AS EventTimestamp,
    Timestamp_Start AS EventTimestamp_UTC,
    'Trip' AS EventType,
    CASE 
        WHEN TripType = 'Uber' THEN 'Uber Trip: ' + Pickup_Location + ' to ' + Dropoff_Location
        WHEN TripType = 'Private' THEN 'Private Trip: ' + Pickup_Location + ' to ' + Dropoff_Location
        ELSE 'Trip: ' + Pickup_Location + ' to ' + Dropoff_Location
    END AS Description,
    Distance_mi AS Distance,
    Duration_min AS Duration,
    Driver_Earnings AS Earnings,
    Energy_Used_kWh AS EnergyUsed,
    Start_SOC,
    End_SOC,
    Efficiency_Wh_mi AS Efficiency,
    TripType AS SubType
FROM Rides.Rides

UNION ALL

SELECT 
    SessionID AS EventID,
    Start_Time AT TIME ZONE 'UTC' AT TIME ZONE 'Mountain Standard Time' AS EventTimestamp,
    Start_Time AS EventTimestamp_UTC,
    'Charge' AS EventType,
    'Charging Session at ' + Location_Name AS Description,
    NULL AS Distance,
    DATEDIFF(minute, Start_Time, End_Time) AS Duration,
    -Cost AS Earnings, -- Cost is negative earnings
    Energy_Added_kWh AS EnergyUsed,
    NULL AS Start_SOC,
    NULL AS End_SOC,
    NULL AS Efficiency,
    'Charge' AS SubType
FROM Rides.ChargingSessions;
GO

-- 3. Create View: Reports.TripAnalytics
-- Pre-calculates financial metrics for easier Copilot reasoning
CREATE OR ALTER VIEW Reports.TripAnalytics AS
SELECT 
    RideID,
    Timestamp_Start AT TIME ZONE 'UTC' AT TIME ZONE 'Mountain Standard Time' AS Timestamp_Start,
    Timestamp_Start AS Timestamp_Start_UTC,
    TripType,
    Driver_Earnings,
    Distance_mi,
    Duration_min,
    
    -- Derived Metrics
    CASE WHEN Distance_mi > 0 THEN Driver_Earnings / Distance_mi ELSE 0 END AS DollarPerMile,
    CASE WHEN Duration_min > 0 THEN Driver_Earnings / Duration_min ELSE 0 END AS DollarPerMinute,
    CASE WHEN Duration_min > 0 THEN (Driver_Earnings / Duration_min) * 60 ELSE 0 END AS HourlyRate,
    
    Energy_Used_kWh,
    Efficiency_Wh_mi
FROM Rides.Rides
WHERE Driver_Earnings IS NOT NULL;
GO
