import os
import logging
import pyodbc
import struct
import datetime
from azure.identity import DefaultAzureCredential

class DatabaseClient:
    def __init__(self):
        self.connection_string = os.environ.get("SQL_CONNECTION_STRING")

    def get_connection(self):
        server = os.environ.get("SQL_SERVER_NAME")
        database = os.environ.get("SQL_DATABASE_NAME")

        # 1. Prefer Managed Identity (Passwordless) if server/db configured
        if server and database:
            try:
                logging.info(f"Connecting to {database} on {server} via Managed Identity...")
                conn_str = (
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={server};"
                    f"DATABASE={database};"
                    "Authentication=ActiveDirectoryMsi;"
                    "Encrypt=yes;"
                    "TrustServerCertificate=no;" # Strict for production
                    "Connection Timeout=30;"
                )
                return pyodbc.connect(conn_str)
            except Exception as e:
                logging.warning(f"Managed Identity connection failed, checking legacy fallback: {e}")

        # 2. Legacy Fallback (Connection String)
        if not self.connection_string:
            logging.error("No SQL configuration found (Server/DB or ConnectionString).")
            return None
            
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logging.error(f"Failed to connect to SQL via legacy string: {e}")
            return None

    def execute_query_with_results(self, query):
        """Executes a SQL query and returns results as dynamic dictionaries."""
        conn = self.get_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            return []
        except Exception as e:
            logging.error(f"Error fetching query results: {e}")
            return []
        finally:
            conn.close()

    def execute_query(self, query):
        """Executes a raw SQL query (useful for creating views/tables)."""
        conn = self.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            conn.commit()
            logging.info("Query executed successfully.")
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            raise e
        finally:
            conn.close()

    def save_trip(self, trip_data):
        # 1. Determine Trip Type & ID
        is_uber = trip_data.get('classification') == 'Uber_Core'
        trip_type = 'Uber' if is_uber else 'Private'
        
        import hashlib
        source_url = trip_data.get('source_url', '')
        url_hash = hashlib.md5(source_url.encode()).hexdigest()[:8]
        trip_id = trip_data.get('trip_id') if trip_data.get('trip_id') and 'Unknown' not in trip_data.get('trip_id') else f"T{url_hash}"

        logging.info(f"Saving {trip_type} Trip: {trip_id}")
        
        conn = self.get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        
        # 2. Map Data to Schema
        rider_payment = trip_data.get('rider_payment', 0)
        driver_earnings = trip_data.get('driver_total', 0)
        uber_cut = trip_data.get('uber_cut', 0)
        platform_cut = uber_cut 
        
        platform_emoji = '🟨'
        if platform_cut > driver_earnings:
            platform_emoji = '🟥'
        elif driver_earnings > platform_cut:
            platform_emoji = '🟩'

        query = """
        MERGE INTO Trips AS target
        USING (SELECT ? AS TripID) AS source
        ON (target.TripID = source.TripID)
        WHEN MATCHED THEN
            UPDATE SET 
                BlockID = ?, TripType = ?, Timestamp_Offer = ?, Pickup_Place = ?, Dropoff_Place = ?,
                Distance_mi = ?, Duration_min = ?, Uber_Distance = ?, Uber_Duration = ?,
                Tessie_Distance = ?, Tessie_Duration = ?, Tessie_DriveID = ?,
                Rider_Payment = ?, Uber_ServiceFee = ?, Platform_Cut = ?, Platform_Emoji = ?,
                Earnings_Driver = ?, Fare = ?, Tip = ?, SourceURL = ?, Payment_Method = ?, 
                Classification = ?, Notes = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (
                TripID, BlockID, TripType, Timestamp_Offer, Pickup_Place, Dropoff_Place,
                Distance_mi, Duration_min, Uber_Distance, Uber_Duration,
                Tessie_Distance, Tessie_Duration, Tessie_DriveID,
                Rider_Payment, Uber_ServiceFee, Platform_Cut, Platform_Emoji,
                Earnings_Driver, Fare, Tip, SourceURL, Payment_Method, 
                Classification, Notes, CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        t_offer = trip_data.get('timestamp_epoch')
        if t_offer:
            t_offer = datetime.datetime.fromtimestamp(t_offer)

        # Logic:
        # 1. Private Trip (Source of Truth = Tessie)
        #    - Distance_mi = Tessie
        #    - Uber_Distance = NULL (To avoid confusion)
        
        # 2. Uber Trip (Source of Truth = Uber, but we compare)
        #    - Distance_mi = Uber ( What we got paid for )
        #    - Uber_Distance = Uber
        #    - Tessie_Distance = Tessie (Actual driven)
        
        tessie_dist = trip_data.get('tessie_distance', 0)
        tessie_dur = trip_data.get('tessie_duration', 0)
        
        uber_dist = trip_data.get('distance_miles', 0)
        uber_dur = trip_data.get('duration_minutes', 0)
        
        if not is_uber:
            # PRIVATE TRIP: Enforce Tessie as Source of Truth
            final_dist = tessie_dist
            final_dur = tessie_dur
            # Wipe Uber stats to prevent dashboard confusion
            uber_dist = None
            uber_dur = None
        else:
            # UBER TRIP: Enforce Uber as Source of Truth (for financials)
            final_dist = uber_dist
            final_dur = uber_dur
            
        core_params = (
            trip_data.get('block_name'), trip_type, t_offer, trip_data.get('start_location'), trip_data.get('end_location'),
            final_dist, final_dur,      # Primary Columns
            uber_dist, uber_dur,        # Uber Columns
            tessie_dist, tessie_dur,    # Tessie Columns
            trip_data.get('tessie_drive_id'),
            rider_payment, uber_cut, platform_cut, platform_emoji,
            driver_earnings, trip_data.get('fare', 0), trip_data.get('tip', 0),
            source_url, trip_data.get('payment_method'), trip_data.get('classification'),
            trip_data.get('raw_text')
        )
        
        params = (trip_id,) + core_params + (trip_id,) + core_params

        try:
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Successfully saved trip {trip_id} to database.")
        except Exception as e:
            logging.error(f"Error executing SQL for trip {trip_id}: {e}")
            raise
        finally:
            conn.close()

    def save_charge(self, charge_data):
        session_id = charge_data.get('session_id')
        if not session_id:
            logging.error("Missing session_id in charge_data")
            return

        logging.info(f"Saving Charging Session: {session_id}")
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        query = """
        MERGE INTO ChargingSessions AS target
        USING (SELECT ? AS SessionID) AS source
        ON (target.SessionID = source.SessionID)
        WHEN MATCHED THEN
            UPDATE SET Start_Time = ?, End_Time = ?, Location_Name = ?, Start_SOC = ?, 
            End_SOC = ?, Energy_Added_kWh = ?, Cost = ?, Duration_min = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (SessionID, Start_Time, End_Time, Location_Name, Start_SOC, End_SOC, 
            Energy_Added_kWh, Cost, Duration_min, LastUpdated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        p = (charge_data.get('start_time'), charge_data.get('end_time'), charge_data.get('location'),
             charge_data.get('start_soc'), charge_data.get('end_soc'), charge_data.get('energy_added'),
             charge_data.get('cost'), charge_data.get('duration'))
        params = (session_id,) + p + (session_id,) + p

        try:
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Successfully saved charging session {session_id}")
        except Exception as e:
            logging.error(f"Error saving charging session {session_id}: {e}")
        finally:
            conn.close()

    def save_weather(self, weather_data):
        logging.info("Saving Weather Context")
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        query = "INSERT INTO WeatherLog (Temperature_F, Condition, Location_Name, Source_Blob_URL, Timestamp) VALUES (?, ?, ?, ?, GETDATE());"
        params = (weather_data.get('temperature'), weather_data.get('condition'), weather_data.get('location'), weather_data.get('source_url'))
        try:
            cursor.execute(query, params)
            conn.commit()
            logging.info("Successfully saved weather record.")
        except Exception as e:
            logging.error(f"Error saving weather record: {e}")
        finally:
            conn.close()

    # =========================================================================
    # Copilot API Read-Only Methods
    # =========================================================================

    def get_recent_trips(self, days=7, trip_type=None):
        """Returns trips from the last N days for Copilot."""
        query = """
        SELECT TOP 50 
            TripID, TripType, Pickup_Place, Dropoff_Place, 
            Fare, Tip, Distance_mi, Duration_min, 
            Payment_Method, Format(Timestamp_Offer, 'yyyy-MM-dd HH:mm:ss') as Timestamp
        FROM Trips 
        WHERE Timestamp_Offer >= DATEADD(day, -?, GETDATE())
        """
        params = [days]
        
        if trip_type:
            query += " AND TripType = ?"
            params.append(trip_type)
            
        query += " ORDER BY Timestamp_Offer DESC"
        
        # Use execute_query_with_results which returns list of dicts
        conn = self.get_connection()
        if not conn: return []
        
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            return []
        except Exception as e:
            logging.error(f"Error fetching recent trips: {e}")
            return []
        finally:
            conn.close()

    def get_trip_by_id(self, trip_id):
        """Returns detailed trip information by ID."""
        query = """
        SELECT 
            TripID, TripType, Pickup_Place, Dropoff_Place, 
            Fare, Tip, Earnings_Driver, Distance_mi, Duration_min, 
            Payment_Method, Notes, Classification,
            Format(Timestamp_Offer, 'yyyy-MM-dd HH:mm:ss') as Timestamp
        FROM Trips 
        WHERE TripID = ?
        """
        results = self.execute_query_with_results_params(query, (trip_id,))
        return results[0] if results else None

    def get_daily_metrics(self, start_date, end_date):
        """Returns daily KPIs for date range."""
        query = """
        SELECT 
            Format([Date], 'yyyy-MM-dd') as DateStr,
            TotalEarnings, TotalTips, TripCount, 
            DriveTime_Hours, TotalMiles
        FROM v_DailyKPIs
        WHERE [Date] >= CAST(? AS DATE) AND [Date] <= CAST(? AS DATE)
        ORDER BY [Date] DESC
        """
        return self.execute_query_with_results_params(query, (start_date, end_date))

    def get_block_stats(self, block_name):
        """Returns stats for a specific block."""
        query = """
        SELECT 
            BlockID, 
            Count(*) as TripCount,
            Sum(Earnings_Driver) as TotalEarnings,
            Sum(Distance_mi) as TotalDistance
        FROM Trips
        WHERE BlockID = ?
        GROUP BY BlockID
        """
        return self.execute_query_with_results_params(query, (block_name,))

    def get_summary_metrics(self, days=30):
        """Returns aggregated statistics for last N days."""
        query = """
        SELECT 
            Count(*) as TotalTrips,
            Sum(Earnings_Driver) as TotalEarnings,
            Sum(Tip) as TotalTips,
            Sum(Distance_mi) as TotalDistance,
            Avg(Fare) as AvgFare
        FROM Trips
        WHERE Timestamp_Offer >= DATEADD(day, -?, GETDATE())
        """
        # Execute manually to support param
        conn = self.get_connection()
        if not conn: return None
        
        cursor = conn.cursor()
        try:
            cursor.execute(query, (days,))
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                row = cursor.fetchone()
                if row:
                    return dict(zip(columns, row))
            return None
        except Exception as e:
            logging.error(f"Error fetching summary metrics: {e}")
            return None
        finally:
            conn.close()

    def execute_query_with_results_params(self, query, params):
        """Helper for parametrized queries returning dicts."""
        conn = self.get_connection()
        if not conn: return []
        
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            return []
        except Exception as e:
            logging.error(f"Error fetching query results: {e}")
            return []
        finally:
            conn.close()
