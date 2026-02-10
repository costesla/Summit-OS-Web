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
        ride_id = trip_data.get('trip_id') or f"R-{url_hash}"

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
                Fare = ?, Tip = ?, Driver_Earnings = ?, Platform_Cut = ?,
                Source_URL = ?, Classification = ?, Sidecar_Artifact_JSON = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (
                RideID, TripType, Timestamp_Start, Pickup_Location, Dropoff_Location,
                Distance_mi, Duration_min, Tessie_DriveID, Tessie_Distance,
                Fare, Tip, Driver_Earnings, Platform_Cut,
                Source_URL, Classification, Sidecar_Artifact_JSON, CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        t_start = trip_data.get('timestamp_epoch')
        if t_start: t_start = datetime.datetime.fromtimestamp(t_start)

        params = (
            ride_id,
            trip_data.get('trip_type', 'Uber' if trip_data.get('classification') == 'Uber_Core' else 'Private'),
            t_start,
            trip_data.get('start_location') or trip_data.get('pickup_place'),
            trip_data.get('end_location') or trip_data.get('dropoff_place'),
            trip_data.get('distance_miles', 0),
            trip_data.get('duration_minutes', 0),
            trip_data.get('tessie_drive_id'),
            trip_data.get('tessie_distance', 0),
            trip_data.get('fare', 0),
            trip_data.get('tip', 0),
            trip_data.get('driver_total', 0),
            trip_data.get('uber_cut', 0),
            source_url,
            trip_data.get('classification'),
            json.dumps(trip_data) if trip_data else None,
            # For INSERT:
            ride_id,
            trip_data.get('trip_type', 'Uber' if trip_data.get('classification') == 'Uber_Core' else 'Private'),
            t_start,
            trip_data.get('start_location') or trip_data.get('pickup_place'),
            trip_data.get('end_location') or trip_data.get('dropoff_place'),
            trip_data.get('distance_miles', 0),
            trip_data.get('duration_minutes', 0),
            trip_data.get('tessie_drive_id'),
            trip_data.get('tessie_distance', 0),
            trip_data.get('fare', 0),
            trip_data.get('tip', 0),
            trip_data.get('driver_total', 0),
            trip_data.get('uber_cut', 0),
            source_url,
            trip_data.get('classification'),
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
        
        p = (charge_data.get('start_time'), charge_data.get('end_time'), charge_data.get('location'),
             charge_data.get('energy_added'), charge_data.get('cost'))
        params = (charge_data.get('session_id'),) + p + (charge_data.get('session_id'),) + p

        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            logging.error(f"SQL Save Charge Error: {e}")
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
