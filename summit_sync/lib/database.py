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
        if not self.connection_string:
            logging.error("SQL_CONNECTION_STRING not set.")
            return None
        try:
            # Check if we should use Managed Identity (if no password in conn string)
            # Use case-insensitive check for password
            conn_str_lower = self.connection_string.lower()
            if "password=" not in conn_str_lower and "pwd=" not in conn_str_lower:
                logging.info("Attempting Managed Identity connection to SQL...")
                credential = DefaultAzureCredential()
                token = credential.get_token("https://database.windows.net/.default")
                
                # SQL Server requires the token to be packed in a specific way for pyodbc
                token_bytes = token.token.encode("UTF-16-LE")
                token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
                
                # Attribute 1254 in pyodbc is used for the database token
                SQL_COPT_SS_ACCESS_TOKEN = 1254
                return pyodbc.connect(self.connection_string, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
            
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logging.error(f"Failed to connect to SQL: {e}")
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

    def execute_non_query(self, query, params=None):
        """Executes a SQL statement (UPDATE/INSERT/DELETE) with optional parameters."""
        conn = self.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            logging.info("Non-query executed successfully.")
        except Exception as e:
            logging.error(f"Error executing non-query: {e}")
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
                BlockID = ?, TripType = ?, Timestamp_Offer = ?, Timestamp_Pickup = ?, Timestamp_Dropoff = ?,
                Pickup_Place = ?, Dropoff_Place = ?,
                Distance_mi = ?, Duration_min = ?, Uber_Distance = ?, Uber_Duration = ?,
                Tessie_Distance = ?, Tessie_Duration = ?, Tessie_DriveID = ?,
                Rider_Payment = ?, Uber_ServiceFee = ?, Platform_Cut = ?, Platform_Emoji = ?,
                Earnings_Driver = ?, Fare = ?, Tip = ?, SourceURL = ?, Payment_Method = ?, 
                Classification = ?, Notes = ?,
                Is_CDOT_Reportable = ?, Passenger_FirstName = ?, Pickup_Address_Full = ?, Dropoff_Address_Full = ?,
                Tessie_Distance_Mi = ?, Insurance_Fees = ?,
                LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (
                TripID, BlockID, TripType, Timestamp_Offer, Timestamp_Pickup, Timestamp_Dropoff,
                Pickup_Place, Dropoff_Place,
                Distance_mi, Duration_min, Uber_Distance, Uber_Duration,
                Tessie_Distance, Tessie_Duration, Tessie_DriveID,
                Rider_Payment, Uber_ServiceFee, Platform_Cut, Platform_Emoji,
                Earnings_Driver, Fare, Tip, SourceURL, Payment_Method, 
                Classification, Notes,
                Is_CDOT_Reportable, Passenger_FirstName, Pickup_Address_Full, Dropoff_Address_Full,
                Tessie_Distance_Mi, Insurance_Fees,
                CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        # Convert timestamps
        t_offer = trip_data.get('timestamp_epoch')
        t_pickup = trip_data.get('timestamp_pickup_epoch')
        t_dropoff = trip_data.get('timestamp_dropoff_epoch')
        
        if t_offer:
            t_offer = datetime.datetime.fromtimestamp(t_offer)
        if t_pickup:
            t_pickup = datetime.datetime.fromtimestamp(t_pickup)
        if t_dropoff:
            t_dropoff = datetime.datetime.fromtimestamp(t_dropoff)

        core_params = (
            trip_data.get('block_name'), trip_type, t_offer, t_pickup, t_dropoff,
            trip_data.get('start_location'), trip_data.get('end_location'),
            trip_data.get('tessie_distance', 0) or trip_data.get('distance_miles', 0), 
            trip_data.get('tessie_duration', 0) or trip_data.get('duration_minutes', 0),
            trip_data.get('distance_miles', 0), trip_data.get('duration_minutes', 0),
            trip_data.get('tessie_distance', 0), trip_data.get('tessie_duration', 0),
            trip_data.get('tessie_drive_id'),
            rider_payment, uber_cut, platform_cut, platform_emoji,
            driver_earnings, trip_data.get('fare', 0), trip_data.get('tip', 0),
            source_url, trip_data.get('payment_method'), trip_data.get('classification'),
            trip_data.get('raw_text'),
            # Compliance Params
            1 if trip_data.get('is_cdot_reportable') else 0,
            trip_data.get('passenger_firstname'),
            trip_data.get('pickup_address_full'),
            trip_data.get('dropoff_address_full'),
            trip_data.get('tessie_distance_mi'),
            trip_data.get('insurance_fees')
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
