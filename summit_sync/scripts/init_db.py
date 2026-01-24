
import os
import pyodbc

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

if __name__ == "__main__":
    load_env()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found.")
        exit(1)

    print(f"Connecting to SQL to Apply Schema v2026-01-22...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # 1. Trips Table (Unified Uber + Private)
        # Includes fields for both. 'TripType' distinguishes them.
        trips_ddl = """
        IF OBJECT_ID('dbo.Trips', 'U') IS NOT NULL DROP TABLE dbo.Trips;
        CREATE TABLE Trips (
            TripID NVARCHAR(100) PRIMARY KEY, -- e.g. YYYYMMDD-Uber-01 or Private-01
            BlockID NVARCHAR(100),            -- e.g. 2026-01-22-B1
            TripType NVARCHAR(20),            -- 'Uber' or 'Private'
            
            -- Timestamps & Locations
            Timestamp_Offer DATETIME,
            Timestamp_Pickup DATETIME,
            Timestamp_Dropoff DATETIME,
            Pickup_Place NVARCHAR(200),
            Dropoff_Place NVARCHAR(200),
            Pickup_Elevation INT,
            Dropoff_Elevation INT,
            Elevation_Change INT,
            
            -- Metrics (Cross-Validation)
            Distance_mi DECIMAL(10,2),      -- Primary (preferred)
            Duration_min DECIMAL(10,2),     -- Primary (preferred)
            
            Uber_Distance DECIMAL(10,2),    -- From OCR Source of Truth
            Uber_Duration DECIMAL(10,2),    -- From OCR Source of Truth
            Tessie_Distance DECIMAL(10,2),  -- From Tesla Source of Truth
            Tessie_Duration DECIMAL(10,2),  -- From Tesla Source of Truth
            Tessie_DriveID NVARCHAR(100),   -- Correlation ID
            
            SOC_Start INT,
            SOC_End INT,
            Energy_kWh DECIMAL(10,2),
            Efficiency_WhMi DECIMAL(10,2),
            
            -- Financials (Uber)
            Offer_Upfront DECIMAL(10,2),
            Offer_Dist DECIMAL(10,2),
            Offer_Dur DECIMAL(10,2),
            Rider_Payment DECIMAL(10,2),
            Uber_ServiceFee DECIMAL(10,2),
            Uber_OtherFees DECIMAL(10,2),
            Platform_Cut DECIMAL(10,2),
            Platform_Emoji NVARCHAR(10), -- 🟩 / 🟥 / 🟨
            
            -- Financials (Private/Driver)
            Earnings_Driver DECIMAL(10,2),
            Fare DECIMAL(10,2),
            Tip DECIMAL(10,2),
            Payment_Method NVARCHAR(50),
            
            -- Metadata
            SourceURL NVARCHAR(500),
            Notes NVARCHAR(MAX),
            CreatedAt DATETIME DEFAULT GETDATE(),
            LastUpdated DATETIME DEFAULT GETDATE()
        );
        """
        
        # 2. Blocks Table (SOC)
        blocks_ddl = """
        IF OBJECT_ID('dbo.Blocks', 'U') IS NOT NULL DROP TABLE dbo.Blocks;
        CREATE TABLE Blocks (
            BlockID NVARCHAR(100) PRIMARY KEY,
            Begin_Time DATETIME,
            End_Time DATETIME,
            Begin_SOC INT,
            End_SOC INT,
            Begin_Odometer DECIMAL(10,1),
            End_Odometer DECIMAL(10,1),
            Block_Distance DECIMAL(10,1),
            Block_Energy DECIMAL(10,1),
            Block_Efficiency DECIMAL(10,1),
            Initialized BIT DEFAULT 0,
            LastUpdated DATETIME DEFAULT GETDATE()
        );
        """

        # 3. ChargingSessions Table
        charging_ddl = """
        IF OBJECT_ID('dbo.ChargingSessions', 'U') IS NOT NULL DROP TABLE dbo.ChargingSessions;
        CREATE TABLE ChargingSessions (
            SessionID NVARCHAR(100) PRIMARY KEY,
            Start_Time DATETIME,
            End_Time DATETIME,
            Location_Name NVARCHAR(200),
            Stall_Label NVARCHAR(50),
            Start_SOC INT,
            End_SOC INT,
            Energy_Added_kWh DECIMAL(10,2),
            Cost DECIMAL(10,2),
            Duration_min DECIMAL(10,2),
            Rate_Applied DECIMAL(10,4),
            SourceURL NVARCHAR(500),
            LastUpdated DATETIME DEFAULT GETDATE()
        );
        """

        # 4. Expenses Table
        expenses_ddl = """
        IF OBJECT_ID('dbo.Expenses', 'U') IS NOT NULL DROP TABLE dbo.Expenses;
        CREATE TABLE Expenses (
            ExpenseID NVARCHAR(100) PRIMARY KEY,
            DateTime DATETIME,
            Category NVARCHAR(50), -- e.g. 'Charging'
            Amount DECIMAL(10,2),
            Source NVARCHAR(200),
            Notes NVARCHAR(MAX),
            LastUpdated DATETIME DEFAULT GETDATE()
        );
        """
        
        # Execute DDL
        print("Creating Trips Table...")
        cursor.execute(trips_ddl)
        print("Creating Blocks Table...")
        cursor.execute(blocks_ddl)
        print("Creating ChargingSessions Table...")
        cursor.execute(charging_ddl)
        print("Creating Expenses Table...")
        cursor.execute(expenses_ddl)
        
        conn.commit()
        print("Schema v2026-01-22 Applied Successfully.")
        
    except Exception as e:
        print(f"Failed to apply schema: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
