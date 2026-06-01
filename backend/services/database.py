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
            conn_str = self.connection_string
            # Ensure a generous connection timeout for Azure SQL cold-start
            if "Connection Timeout" not in conn_str:
                conn_str = conn_str.rstrip(";") + ";Connection Timeout=25;"
            return pyodbc.connect(conn_str)
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

        # Resolve initial classification & trip type
        incoming_classification = trip_data.get('classification') or trip_data.get('Classification')
        incoming_triptype = trip_data.get('trip_type') or trip_data.get('TripType') or ('Uber' if incoming_classification == 'Uber_Core' else 'Private')

        # Check existing row in DB for Ingestion Guardrails
        existing_classification = None
        existing_triptype = None
        try:
            cursor.execute("SELECT Classification, TripType FROM Rides.Rides WHERE RideID = ?", (ride_id,))
            row = cursor.fetchone()
            if row:
                existing_classification = row[0]
                existing_triptype = row[1]
        except Exception as query_err:
            logging.warning(f"Failed to query existing ride {ride_id} classification: {query_err}")

        # Ingestion Guardrails: Database classification takes precedence over incoming updates for non-Uber/Private drives
        is_existing_private = (
            existing_triptype == 'Private' or 
            (existing_classification and (
                existing_classification.startswith('Private:') or 
                existing_classification in ('Jackie', 'Esmeralda')
            ))
        )
        is_incoming_private = (
            incoming_triptype == 'Private' or 
            (incoming_classification and (
                incoming_classification.startswith('Private:') or 
                incoming_classification in ('Jackie', 'Esmeralda')
            ))
        )

        if is_existing_private and not is_incoming_private:
            logging.info(f"Ingestion Guardrail: Preserving database classification '{existing_classification}' for {ride_id} (Blocked incoming update '{incoming_classification}')")
            incoming_classification = existing_classification
            incoming_triptype = 'Private'

        params = (
            ride_id,
            incoming_triptype,
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
            incoming_classification,
            json.dumps(trip_data) if trip_data else None,
            # For INSERT:
            ride_id,
            incoming_triptype,
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
            incoming_classification,
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
            # Idempotent table creation with strict check constraint
            cursor.execute("""
                IF OBJECT_ID('Rides.ManualExpenses', 'U') IS NULL
                CREATE TABLE Rides.ManualExpenses (
                    ExpenseID NVARCHAR(100) PRIMARY KEY,
                    Category NVARCHAR(50),
                    Amount DECIMAL(10,2),
                    Note NVARCHAR(500),
                    Timestamp DATETIME DEFAULT GETDATE(),
                    LastUpdated DATETIME DEFAULT GETDATE(),
                    IncludedInKPI BIT NOT NULL DEFAULT 1,
                    CONSTRAINT CK_ManualExpenses_KPI_Isolation CHECK (
                        (Category IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 0)
                        OR
                        (Category NOT IN ('Maintenance', 'General_Expense') AND IncludedInKPI = 1)
                    )
                )
            """)
            conn.commit()

            query = """
            MERGE INTO Rides.ManualExpenses AS target
            USING (SELECT ? AS ExpenseID) AS source
            ON (target.ExpenseID = source.ExpenseID)
            WHEN MATCHED THEN
                UPDATE SET Category = ?, Amount = ?, Note = ?, Timestamp = ?, IncludedInKPI = ?, LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (ExpenseID, Category, Amount, Note, Timestamp, IncludedInKPI, LastUpdated)
                VALUES (?, ?, ?, ?, ?, ?, GETDATE());
            """
            
            eid = str(expense_data.get('id'))
            cat = expense_data.get('category')
            amt = float(expense_data.get('amount') or 0)
            note = expense_data.get('note')
            ts = expense_data.get('timestamp') or datetime.datetime.now()
            
            # Strict Fail-Fast Validation
            kpi_passed = expense_data.get('included_in_kpi')
            expected_kpi = 0 if cat in ["Maintenance", "General_Expense"] else 1
            if kpi_passed is not None and int(kpi_passed) != expected_kpi:
                raise ValueError(
                    f"FAIL-FAST KPI CONTAMINATION DETECTED: Expense category '{cat}' cannot have "
                    f"included_in_kpi = {kpi_passed} (expected {expected_kpi}). Fail-fast triggered!"
                )
            kpi = expected_kpi
            
            p = (cat, amt, note, ts, kpi)
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
        """Fetches all trips for a specific date (YYYY-MM-DD).
        
        Only returns trips that have meaningful data:
        - Fare > 0 (any trip with earnings)
        - Manual_Entry (manually logged by operator)
        - Uber_Matched (screenshot matched to a Tessie drive)
        
        Uber_Dropoff records are intentionally hidden until a screenshot
        is matched to them to prevent ghost duplicates when manual entries exist.
        Jackie and Esmeralda private drives are shown regardless of fare.
        """
        query = """
        SELECT 
            RideID AS id, TripType AS type, Fare AS fare, Tip AS tip, 
            Platform_Cut AS fees, 
            0 AS insurance, 0 AS otherFees,
            Tessie_DriveID AS tessie_drive_id, 
            Distance_mi AS distance_miles,
            Format(Timestamp_Start, 'yyyy-MM-ddTHH:mm:ss') as timestamp,
            Classification AS classification,
            Pickup_Location AS pickup_location,
            Dropoff_Location AS dropoff_location
        FROM Rides.Rides 
        WHERE Timestamp_Start >= DATEADD(hour, 4, CAST(? AS DATETIME2))
          AND Timestamp_Start < DATEADD(hour, 28, CAST(? AS DATETIME2))
          AND (
            Fare > 0
            OR Classification = 'Manual_Entry'
            OR Classification = 'Uber_Matched'
            OR Classification = 'Jackie'
            OR Classification = 'Esmeralda'
          )
        ORDER BY Timestamp_Start DESC
        """
        return self.execute_query_params(query, (date_str, date_str))

    def get_expenses_by_date(self, date_str):
        """Fetches manual expenses and charging for a specific date."""
        # 1. Manual Expenses (including all categories like dining, fuel, etc.)
        manual_query = """
        SELECT 
            ExpenseID AS id, Category AS category, Amount AS amount, Note AS note, 
            Format(Timestamp, 'yyyy-MM-ddTHH:mm:ss') as timestamp, IncludedInKPI as included_in_kpi
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
        
        # Ensure every charging session has included_in_kpi = 1
        for ch in charging:
            ch["included_in_kpi"] = 1
        
        fastfood = []
        capital_maintenance = []
        for exp in manual:
            # Ensure included_in_kpi is present as a standard integer (1 or 0)
            exp["included_in_kpi"] = 1 if exp.get("included_in_kpi") else 0
            cat = exp.get("category")
            if cat in ["Maintenance", "General_Expense"]:
                capital_maintenance.append(exp)
            elif cat == "Charging_Session":
                charging.append(exp)
            else:
                fastfood.append(exp)
        
        return {
            "fastfood": fastfood,
            "charging": charging,
            "capital_maintenance": capital_maintenance
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
        # Deduplication rule:
        #   - Days WITH TRIP-* records  → count TRIP-* only (canonical OCR trips)
        #   - Days WITHOUT TRIP-* records → count non-TESSIE/non-UBER records
        #     (pre-OCR manual entries from before the pipeline existed)
        # TESSIE-* and UBER-* are always excluded — they are drive cross-references
        # that duplicate earnings already on TRIP-* rows.
        query = """
        SELECT
            CONVERT(varchar(10), CAST(Timestamp_Start AS DATE), 23) AS DateStr,
            ISNULL(SUM(Driver_Earnings), 0)       AS TotalEarnings,
            ISNULL(SUM(Tip), 0)                   AS TotalTips,
            COUNT(*)                               AS TripCount,
            ISNULL(SUM(Distance_mi), 0.0)         AS TotalMiles,
            ISNULL(SUM(Duration_min) / 60.0, 0.0) AS DriveTime_Hours
        FROM Rides.Rides r
        WHERE Timestamp_Start >= CAST(? AS DATE)
          AND Timestamp_Start <  DATEADD(day, 1, CAST(? AS DATE))
          AND Driver_Earnings > 0
          AND (
              RideID LIKE 'TRIP-%'
              OR (
                  RideID NOT LIKE 'TRIP-%'
                  AND RideID NOT LIKE 'TESSIE-%'
                  AND RideID NOT LIKE 'UBER-%'
                  AND NOT EXISTS (
                      SELECT 1 FROM Rides.Rides t2
                      WHERE t2.RideID LIKE 'TRIP-%'
                        AND t2.Driver_Earnings > 0
                        AND CAST(t2.Timestamp_Start AS DATE) = CAST(r.Timestamp_Start AS DATE)
                  )
              )
          )
        GROUP BY CAST(Timestamp_Start AS DATE)
        ORDER BY CAST(Timestamp_Start AS DATE) DESC
        """
        return self.execute_query_params(query, (start_date, end_date))


    def get_summary_metrics(self, days=30):
        query = """
        SELECT
            COUNT(*)                AS TotalTrips,
            SUM(Driver_Earnings)    AS TotalEarnings,
            SUM(Tip)                AS TotalTips,
            SUM(Distance_mi)        AS TotalDistance,
            AVG(Fare)               AS AvgFare
        FROM Rides.Rides
        WHERE Timestamp_Start >= DATEADD(day, -?, GETDATE())
          AND RideID LIKE 'TRIP-%'
        """
        results = self.execute_query_params(query, (days,))
        return results[0] if results else None

    def dedup_earnings(self, lookback_days: int = 7) -> dict:
        """
        Zero out Driver_Earnings on TESSIE-* and UBER-* rows that duplicate a
        canonical TRIP-* record within ±30 minutes on the same day.
        Run nightly so new syncs don't re-inflate totals.
        Returns a dict with rows_zeroed and amount_zeroed for logging.
        """
        conn = self.get_connection()
        if not conn:
            return {"rows_zeroed": 0, "amount_zeroed": 0.0, "error": "no connection"}
        cur = conn.cursor()
        try:
            cutoff = f"DATEADD(day, -{lookback_days}, GETDATE())"
            total_rows = 0
            total_amount = 0.0

            for prefix in ("TESSIE-%", "UBER-%"):
                # Measure before
                cur.execute(f"""
                    SELECT COUNT(*), ISNULL(SUM(Driver_Earnings), 0)
                    FROM Rides.Rides r
                    WHERE r.RideID LIKE ?
                      AND r.Driver_Earnings > 0
                      AND r.Timestamp_Start >= {cutoff}
                      AND EXISTS (
                          SELECT 1 FROM Rides.Rides t
                          WHERE t.RideID LIKE 'TRIP-%'
                            AND t.Driver_Earnings > 0
                            AND CAST(t.Timestamp_Start AS DATE) = CAST(r.Timestamp_Start AS DATE)
                            AND ABS(DATEDIFF(minute, t.Timestamp_Start, r.Timestamp_Start)) <= 30
                      )
                """, (prefix,))
                row = cur.fetchone()
                rows, amount = int(row[0] or 0), float(row[1] or 0)

                if rows > 0:
                    cur.execute(f"""
                        UPDATE Rides.Rides
                        SET Driver_Earnings = 0, Tip = 0, LastUpdated = GETDATE()
                        WHERE RideID LIKE ?
                          AND Driver_Earnings > 0
                          AND Timestamp_Start >= {cutoff}
                          AND EXISTS (
                              SELECT 1 FROM Rides.Rides t
                              WHERE t.RideID LIKE 'TRIP-%'
                                AND t.Driver_Earnings > 0
                                AND CAST(t.Timestamp_Start AS DATE) = CAST(Rides.Timestamp_Start AS DATE)
                                AND ABS(DATEDIFF(minute, t.Timestamp_Start, Rides.Timestamp_Start)) <= 30
                          )
                    """, (prefix,))
                    total_rows += rows
                    total_amount += amount

            conn.commit()
            return {"rows_zeroed": total_rows, "amount_zeroed": round(total_amount, 2)}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"rows_zeroed": 0, "amount_zeroed": 0.0, "error": str(e)}
        finally:
            cur.close()
            conn.close()

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
