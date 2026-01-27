-- SummitOS System Blueprint: SQL Schema Modernization
-- Version 1.0

-- 1. Create Schemas
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Pricing') EXEC('CREATE SCHEMA Pricing');
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Rides') EXEC('CREATE SCHEMA Rides');
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Customers') EXEC('CREATE SCHEMA Customers');
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Reports') EXEC('CREATE SCHEMA Reports');

-- 2. Schema: Pricing
IF OBJECT_ID('Pricing.Tiers', 'U') IS NULL
CREATE TABLE Pricing.Tiers (
    TierID INT PRIMARY KEY IDENTITY(1,1),
    Name NVARCHAR(50),
    BaseFare DECIMAL(10,2),
    MileRate DECIMAL(10,2),
    EffectiveDate DATETIME DEFAULT GETDATE()
);

-- 3. Schema: Rides
-- Migration of dbo.Trips to Rides.Rides
IF OBJECT_ID('Rides.Rides', 'U') IS NULL
CREATE TABLE Rides.Rides (
    RideID NVARCHAR(100) PRIMARY KEY,
    TripType NVARCHAR(20), -- Uber/Private
    Timestamp_Start DATETIME,
    Pickup_Location NVARCHAR(255),
    Dropoff_Location NVARCHAR(255),
    Distance_mi DECIMAL(10,2),
    Duration_min INT,
    
    -- Telemetry Link
    Tessie_DriveID NVARCHAR(100),
    Tessie_Distance DECIMAL(10,2),
    
    -- Financials
    Fare DECIMAL(10,2),
    Tip DECIMAL(10,2),
    Driver_Earnings DECIMAL(10,2),
    Platform_Cut DECIMAL(10,2),
    
    -- Metadata
    Source_URL NVARCHAR(MAX),
    Classification NVARCHAR(50),
    Sidecar_Artifact_JSON NVARCHAR(MAX), -- Aligns with SummitOS sidecar model
    CreatedAt DATETIME DEFAULT GETDATE(),
    LastUpdated DATETIME DEFAULT GETDATE()
);

-- 4. Schema: Rides Extras
IF OBJECT_ID('Rides.ChargingSessions', 'U') IS NULL
CREATE TABLE Rides.ChargingSessions (
    SessionID NVARCHAR(100) PRIMARY KEY,
    Start_Time DATETIME,
    End_Time DATETIME,
    Location_Name NVARCHAR(200),
    Energy_Added_kWh DECIMAL(10,2),
    Cost DECIMAL(10,2),
    LastUpdated DATETIME DEFAULT GETDATE()
);

IF OBJECT_ID('Rides.WeatherLog', 'U') IS NULL
CREATE TABLE Rides.WeatherLog (
    WeatherID INT PRIMARY KEY IDENTITY(1,1),
    Temperature_F INT,
    Condition NVARCHAR(50),
    Location_Name NVARCHAR(100),
    Timestamp DATETIME DEFAULT GETDATE()
);

-- 5. Schema: Customers
IF OBJECT_ID('Customers.Profiles', 'U') IS NULL
CREATE TABLE Customers.Profiles (
    CustomerID INT PRIMARY KEY IDENTITY(1,1),
    FullName NVARCHAR(100),
    Email NVARCHAR(255) UNIQUE,
    Phone NVARCHAR(20),
    CreatedAt DATETIME DEFAULT GETDATE()
);

-- 6. Schema: Reports (Views)
GO
CREATE OR ALTER VIEW Reports.DailyKPIs AS
SELECT 
    CAST(Timestamp_Start AS DATE) AS [Date],
    SUM(Driver_Earnings) AS TotalEarnings,
    SUM(Tip) AS TotalTips,
    COUNT(*) AS RideCount
FROM Rides.Rides
GROUP BY CAST(Timestamp_Start AS DATE);
GO
