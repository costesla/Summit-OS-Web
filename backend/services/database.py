import os
import logging
import pyodbc
import datetime
import json

class DatabaseClient:
    def __init__(self):
        self.connection_string = os.environ.get("SQL_CONNECTION_STRING")

    def get_connection(self):
        server = os.environ.get("SQL_SERVER_NAME")
        database = os.environ.get("SQL_DATABASE_NAME")

        if server and database:
            try:
                conn_str = (
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={server};"
                    f"DATABASE={database};"
                    "Authentication=ActiveDirectoryMsi;"
                    "Encrypt=yes;"
                    "TrustServerCertificate=no;"
                    "Connection Timeout=30;"
                )
                return pyodbc.connect(conn_str)
            except Exception as e:
                logging.warning(f"Managed Identity failed: {e}")

        if not self.connection_string:
            return None
            
        # Fix for Azure Linux (only has Driver 18)
        if os.name == 'posix' and 'ODBC Driver 17' in self.connection_string:
            self.connection_string = self.connection_string.replace('ODBC Driver 17', 'ODBC Driver 18')

        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logging.error(f"SQL Connection Error: {e}")
            return None

    def execute_query_with_results(self, query):
        conn = self.get_connection()
        if not conn: return []
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            return []
        except Exception as e:
            logging.error(f"Query Error: {e}")
            return []
        finally:
            conn.close()

    def save_trip(self, trip_data):
        import hashlib
        source_url = trip_data.get('source_url', '')
        url_hash = hashlib.md5(source_url.encode()).hexdigest()[:8]
        ride_id = str(trip_data.get('trip_id') or trip_data.get('RideID') or f"R-{url_hash}")

        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()

        query = """
        MERGE INTO Rides.Rides AS target
        USING (SELECT ? AS RideID) AS source
        ON (target.RideID = source.RideID)
        WHEN MATCHED THEN
            UPDATE SET 
                TripType = ?, Timestamp_Start = ?, Pickup_Location = ?, Dropoff_Location = ?,
                Distance_mi = ?, Duration_min = ?, Tessie_DriveID = ?, Tessie_Distance = ?,
                Fare = CASE WHEN ? > 0 THEN ? ELSE target.Fare END,
                Tip = CASE WHEN ? > 0 THEN ? ELSE target.Tip END,
                Driver_Earnings = CASE WHEN ? > 0 THEN ? ELSE target.Driver_Earnings END,
                Platform_Cut = CASE WHEN ? <> 0 THEN ? ELSE target.Platform_Cut END,
                Start_SOC = ?, End_SOC = ?, Energy_Used_kWh = ?, Efficiency_Wh_mi = ?,
                Source_URL = ?, Classification = ?, Sidecar_Artifact_JSON = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (
                RideID, TripType, Timestamp_Start, Pickup_Location, Dropoff_Location,
                Distance_mi, Duration_min, Tessie_DriveID, Tessie_Distance,
                Fare, Tip, Driver_Earnings, Platform_Cut,
                Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi,
                Source_URL, Classification, Sidecar_Artifact_JSON, CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        t_start = trip_data.get('timestamp_epoch') or trip_data.get('started_at')
        if t_start: 
            if isinstance(t_start, (int, float)):
                t_start = datetime.datetime.fromtimestamp(t_start)
            # If it's already a string or datetime, we'll let pyodbc handle it or it's handled in params
        
        # Check for pre-formatted fields from TessieSyncService
        t_start = t_start or trip_data.get('Timestamp_Start')

        fare = float(trip_data.get('fare') or 0)
        tip = float(trip_data.get('tip') or 0)
        earnings = float(trip_data.get('driver_total') or 0)
        cut = float(trip_data.get('uber_cut') or 0)

        params = (
            ride_id,
            trip_data.get('trip_type') or trip_data.get('TripType') or ('Uber' if trip_data.get('classification') == 'Uber_Core' else 'Private'),
            t_start,
            trip_data.get('start_location') or trip_data.get('pickup_place') or trip_data.get('Pickup_Location'),
            trip_data.get('end_location') or trip_data.get('dropoff_place') or trip_data.get('Dropoff_Location'),
            float(trip_data.get('distance_miles') or trip_data.get('Distance_mi') or 0),
            float(trip_data.get('duration_minutes') or trip_data.get('Duration_min') or 0),
            trip_data.get('tessie_drive_id') or trip_data.get('Tessie_DriveID'),
            float(trip_data.get('tessie_distance') or trip_data.get('Tessie_Distance') or 0),
            fare, fare,
            tip, tip,
            earnings, earnings,
            cut, cut,
            trip_data.get('start_soc') or trip_data.get('Start_SOC'),
            trip_data.get('end_soc') or trip_data.get('End_SOC'),
            trip_data.get('energy_used') or trip_data.get('Energy_Used_kWh'),
            trip_data.get('efficiency_wh_mi') or trip_data.get('Efficiency_Wh_mi'),
            source_url,
            trip_data.get('classification') or trip_data.get('Classification'),
            json.dumps(trip_data) if trip_data else None,
            # For INSERT:
            ride_id,
            trip_data.get('trip_type') or trip_data.get('TripType') or ('Uber' if trip_data.get('classification') == 'Uber_Core' else 'Private'),
            t_start,
            trip_data.get('start_location') or trip_data.get('pickup_place') or trip_data.get('Pickup_Location'),
            trip_data.get('end_location') or trip_data.get('dropoff_place') or trip_data.get('Dropoff_Location'),
            float(trip_data.get('distance_miles') or trip_data.get('Distance_mi') or 0),
            float(trip_data.get('duration_minutes') or trip_data.get('Duration_min') or 0),
            trip_data.get('tessie_drive_id') or trip_data.get('Tessie_DriveID'),
            float(trip_data.get('tessie_distance') or trip_data.get('Tessie_Distance') or 0),
            float(trip_data.get('fare') or 0),
            float(trip_data.get('tip') or 0),
            float(trip_data.get('driver_total') or 0),
            float(trip_data.get('uber_cut') or 0),
            trip_data.get('start_soc') or trip_data.get('Start_SOC'),
            trip_data.get('end_soc') or trip_data.get('End_SOC'),
            trip_data.get('energy_used') or trip_data.get('Energy_Used_kWh'),
            trip_data.get('efficiency_wh_mi') or trip_data.get('Efficiency_Wh_mi'),
            source_url,
            trip_data.get('classification') or trip_data.get('Classification'),
            json.dumps(trip_data) if trip_data else None
        )

        try:
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Saved ride {ride_id}")
        except Exception as e:
            logging.error(f"SQL Save Trip Error: {e}")
        finally:
            conn.close()

    def save_charge(self, charge_data):
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        query = """
        MERGE INTO Rides.ChargingSessions AS target
        USING (SELECT ? AS SessionID) AS source
        ON (target.SessionID = source.SessionID)
        WHEN MATCHED THEN
            UPDATE SET Start_Time = ?, End_Time = ?, Location_Name = ?, Energy_Added_kWh = ?, 
            Cost = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (SessionID, Start_Time, End_Time, Location_Name, Energy_Added_kWh, Cost, LastUpdated)
            VALUES (?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        sid = str(charge_data.get('session_id'))
        p = (charge_data.get('start_time'), charge_data.get('end_time'), charge_data.get('location'),
             float(charge_data.get('energy_added') or 0), float(charge_data.get('cost') or 0))
        params = (sid,) + p + (sid,) + p

        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            logging.error(f"SQL Save Charge Error: {e}")
        finally:
            conn.close()

    def save_manual_expense(self, expense_data):
        """Saves a manual expense (Fast Food, etc.) to the cloud."""
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        try:
            # Idempotent table creation
            cursor.execute("""
                IF OBJECT_ID('Rides.ManualExpenses', 'U') IS NULL
                CREATE TABLE Rides.ManualExpenses (
                    ExpenseID NVARCHAR(100) PRIMARY KEY,
                    Category NVARCHAR(50),
                    Amount DECIMAL(10,2),
                    Note NVARCHAR(500),
                    Timestamp DATETIME DEFAULT GETDATE(),
                    LastUpdated DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()

            query = """
            MERGE INTO Rides.ManualExpenses AS target
            USING (SELECT ? AS ExpenseID) AS source
            ON (target.ExpenseID = source.ExpenseID)
            WHEN MATCHED THEN
                UPDATE SET Category = ?, Amount = ?, Note = ?, Timestamp = ?, LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (ExpenseID, Category, Amount, Note, Timestamp, LastUpdated)
                VALUES (?, ?, ?, ?, ?, GETDATE());
            """
            
            eid = str(expense_data.get('id'))
            cat = expense_data.get('category')
            amt = float(expense_data.get('amount') or 0)
            note = expense_data.get('note')
            ts = expense_data.get('timestamp') or datetime.datetime.now()
            
            p = (cat, amt, note, ts)
            params = (eid,) + p + (eid,) + p
            
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Saved manual expense {eid}")
        except Exception as e:
            logging.error(f"SQL Save Manual Expense Error: {e}")
        finally:
            conn.close()

    def save_weather(self, weather_data):
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        query = "INSERT INTO Rides.WeatherLog (Temperature_F, Condition, Location_Name) VALUES (?, ?, ?);"
        params = (weather_data.get('temperature'), weather_data.get('condition'), weather_data.get('location'))
        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            logging.error(f"SQL Save Weather Error: {e}")
        finally:
            conn.close()

    # Copilot Methods
    def get_recent_trips(self, days=7, trip_type=None):
        query = """
        SELECT TOP 50 
            RideID AS TripID, TripType, Pickup_Location AS Pickup_Place, Dropoff_Location AS Dropoff_Place, 
            Fare, Tip, Distance_mi, Duration_min, 
            Format(Timestamp_Start, 'yyyy-MM-dd HH:mm:ss') as Timestamp
        FROM Rides.Rides 
        WHERE Timestamp_Start >= DATEADD(day, -?, GETDATE())
        """
        params = [days]
        if trip_type:
            query += " AND TripType = ?"
            params.append(trip_type)
        query += " ORDER BY Timestamp_Start DESC"
        return self.execute_query_params(query, params)

    def get_trips_by_date(self, date_str):
        """Fetches all trips for a specific date (YYYY-MM-DD)."""
        query = """
        SELECT 
            RideID AS id, TripType AS type, Fare AS fare, Tip AS tip, 
            Platform_Cut AS fees, 
            0 AS insurance, 0 AS otherFees,
            Tessie_DriveID AS tessie_drive_id, 
            Distance_mi AS distance_miles, Format(Timestamp_Start, 'yyyy-MM-ddTHH:mm:ss') as timestamp
        FROM Rides.Rides 
        WHERE CAST(Timestamp_Start AS DATE) = CAST(? AS DATE)
          AND (Fare > 0 OR Classification = 'Manual_Entry' OR Classification = 'Uber_Matched')
        ORDER BY Timestamp_Start DESC
        """
        return self.execute_query_params(query, (date_str,))

    def get_expenses_by_date(self, date_str):
        """Fetches manual expenses and charging for a specific date."""
        # 1. Manual Expenses (including all categories like dining, fuel, etc.)
        manual_query = """
        SELECT 
            ExpenseID AS id, Category AS category, Amount AS amount, Note AS note, 
            Format(Timestamp, 'yyyy-MM-ddTHH:mm:ss') as timestamp
        FROM Rides.ManualExpenses
        WHERE CAST(Timestamp AS DATE) = CAST(? AS DATE)
        """
        manual = self.execute_query_params(manual_query, (date_str,))
        
        # 2. Charging Sessions
        charge_query = """
        SELECT 
            SessionID AS id, 'charging' AS category, Cost AS amount, Location_Name AS note, 
            Format(Start_Time, 'yyyy-MM-ddTHH:mm:ss') as timestamp
        FROM Rides.ChargingSessions
        WHERE CAST(Start_Time AS DATE) = CAST(? AS DATE)
        """
        charging = self.execute_query_params(charge_query, (date_str,))
        
        return {
            "fastfood": manual, # Return all manual/banking expenses to the UI
            "charging": charging
        }

    def get_trip_by_id(self, ride_id):
        query = """
        SELECT 
            RideID AS TripID, TripType, Pickup_Location AS Pickup_Place, Dropoff_Location AS Dropoff_Place, 
            Fare, Tip, Driver_Earnings AS Earnings_Driver, Distance_mi, Duration_min, 
            Classification, Format(Timestamp_Start, 'yyyy-MM-dd HH:mm:ss') as Timestamp
        FROM Rides.Rides 
        WHERE RideID = ?
        """
        results = self.execute_query_params(query, (ride_id,))
        return results[0] if results else None

    def get_daily_metrics(self, start_date, end_date):
        query = """
        SELECT 
            Format([Date], 'yyyy-MM-dd') as DateStr,
            TotalEarnings, TotalTips, RideCount AS TripCount
        FROM Reports.DailyKPIs
        WHERE [Date] >= CAST(? AS DATE) AND [Date] <= CAST(? AS DATE)
        ORDER BY [Date] DESC
        """
        return self.execute_query_params(query, (start_date, end_date))

    def get_summary_metrics(self, days=30):
        query = """
        SELECT 
            Count(*) as TotalTrips,
            Sum(Driver_Earnings) as TotalEarnings,
            Sum(Tip) as TotalTips,
            Sum(Distance_mi) as TotalDistance,
            Avg(Fare) as AvgFare
        FROM Rides.Rides
        WHERE Timestamp_Start >= DATEADD(day, -?, GETDATE())
        """
        results = self.execute_query_params(query, (days,))
        return results[0] if results else None

    def create_cabin_token(self, booking_id: str, valid_hours: int = 24, expires_at=None) -> str:
        """Generate a 6-digit cabin access code for a booking, store it in DB."""
        import secrets
        # Generate a 6-digit code (100000-999999) for easier manual entry
        token = str(secrets.randbelow(900000) + 100000)
        
        conn = self.get_connection()
        if not conn:
            return token  # still return code even if DB unavailable (graceful degradation)
        cursor = conn.cursor()
        try:
            # Create table if it doesn't exist yet (idempotent)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE s.name = 'Rides' AND t.name = 'CabinTokens')
                CREATE TABLE Rides.CabinTokens (
                    Token NVARCHAR(64) PRIMARY KEY,
                    BookingID NVARCHAR(64) NOT NULL,
                    ExpiresAt DATETIME2 NOT NULL,
                    CreatedAt DATETIME2 DEFAULT GETDATE()
                )
            """)
            
            if expires_at:
                # Use provided expiry time
                cursor.execute(
                    "INSERT INTO Rides.CabinTokens (Token, BookingID, ExpiresAt) VALUES (?, ?, ?)",
                    (token, booking_id, expires_at)
                )
            else:
                # Default to current time + hours
                cursor.execute(
                    "INSERT INTO Rides.CabinTokens (Token, BookingID, ExpiresAt) VALUES (?, ?, DATEADD(hour, ?, GETDATE()))",
                    (token, booking_id, valid_hours)
                )
            conn.commit()
            logging.info(f"Cabin code {token} created for booking {booking_id}")
        except Exception as e:
            logging.error(f"create_cabin_token error: {e}")
        finally:
            conn.close()
        return token

    def validate_cabin_token(self, token: str) -> bool:
        """Return True if the token exists in DB and has not expired."""
        if not token:
            return False
        
        conn = self.get_connection()
        if not conn:
            # Return None to signal a connection error rather than "Not Found"
            return None
            
        try:
            cursor = conn.cursor()
            query = "SELECT Token FROM Rides.CabinTokens WHERE Token = ? AND ExpiresAt > GETDATE()"
            cursor.execute(query, (token,))
            results = cursor.fetchall()
            return len(results) > 0
        except Exception as e:
            logging.error(f"validate_cabin_token error: {e}")
            return None # Signal error
        finally:
            conn.close()

    def execute_query_params(self, query, params):
        conn = self.get_connection()
        if not conn: return []
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            return []
        except Exception as e:
            logging.error(f"SQL Query Params Error: {e}")
            return []
        finally:
            conn.close()

    def save_drive_telemetry(self, drive_id, telemetry_data):
        import json
        logging.info(f"Saving Raw Telemetry for Drive: {drive_id}")
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        query = """
        MERGE INTO Drive_Telemetry AS target
        USING (SELECT ? AS DriveID) AS source
        ON (target.DriveID = source.DriveID)
        WHEN MATCHED THEN
            UPDATE SET RawJSONPayload = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (DriveID, RawJSONPayload, LastUpdated)
            VALUES (?, ?, GETDATE());
        """
        try:
            json_payload = json.dumps(telemetry_data)
            params = (drive_id, json_payload, drive_id, json_payload)
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Successfully archived telemetry payload for {drive_id}.")
        except Exception as e:
            logging.error(f"Error saving telemetry payload for {drive_id}: {e}")
        finally:
            conn.close()
