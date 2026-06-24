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

    def _ensure_payment_status_column(self, cursor):
        cursor.execute(
            "IF COL_LENGTH('Rides.Rides', 'PaymentStatus') IS NULL "
            "ALTER TABLE Rides.Rides ADD PaymentStatus NVARCHAR(20) NULL"
        )

    def set_payment_status(self, ride_id: str, status: str) -> bool:
        """Set PaymentStatus ('Pending', 'Paid', ...) on a ride. Auto-creates the column."""
        conn = self.get_connection()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            self._ensure_payment_status_column(cursor)
            cursor.execute(
                "UPDATE Rides.Rides SET PaymentStatus = ?, LastUpdated = GETUTCDATE() WHERE RideID = ?",
                (status, ride_id),
            )
            updated = cursor.rowcount
            conn.commit()
            return updated > 0
        except Exception as e:
            logging.error(f"set_payment_status failed for {ride_id}: {e}")
            return False
        finally:
            conn.close()

    def get_unpaid_trips(self):
        """All bookings still awaiting payment, oldest first."""
        conn = self.get_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            self._ensure_payment_status_column(cursor)
            conn.commit()
            cursor.execute("""
                SELECT RideID, Timestamp_Start, Fare, Classification,
                       Pickup_Location, Dropoff_Location, Sidecar_Artifact_JSON
                FROM Rides.Rides
                WHERE PaymentStatus = 'Pending'
                  AND Timestamp_Start <= GETUTCDATE()
                  AND DeletedAt IS NULL
                ORDER BY Timestamp_Start ASC
            """)
            trips = []
            for row in cursor.fetchall():
                sidecar = {}
                try:
                    sidecar = json.loads(str(row[6])) if row[6] else {}
                except Exception:
                    pass
                trips.append({
                    "rideId": row[0],
                    "start": row[1].isoformat() if row[1] else None,
                    "fare": float(row[2] or 0),
                    "classification": row[3],
                    "pickup": row[4],
                    "dropoff": row[5],
                    "customerName": sidecar.get("customerName") or sidecar.get("name"),
                    "paymentMethod": sidecar.get("paymentMethod"),
                })
            return trips
        except Exception as e:
            logging.error(f"get_unpaid_trips failed: {e}")
            return []
        finally:
            conn.close()

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
                Source_URL = ?, Classification = ?, Tessie_Label = COALESCE(target.Tessie_Label, ?), Sidecar_Artifact_JSON = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (
                RideID, TripType, Timestamp_Start, Pickup_Location, Dropoff_Location,
                Distance_mi, Duration_min, Tessie_DriveID, Tessie_Distance,
                Fare, Tip, Driver_Earnings, Platform_Cut,
                Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi,
                Source_URL, Classification, Tessie_Label, Sidecar_Artifact_JSON, CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
        """
        
        t_start = trip_data.get('timestamp_epoch') or trip_data.get('started_at')
        if t_start: 
            if isinstance(t_start, (int, float)):
                from services.datetime_utils import utc_to_local
                dt_utc = datetime.datetime.fromtimestamp(t_start, tz=datetime.timezone.utc)
                t_start = utc_to_local(dt_utc).replace(tzinfo=None)
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
        existing_sidecar = None
        try:
            cursor.execute("SELECT Classification, TripType, Sidecar_Artifact_JSON FROM Rides.Rides WHERE RideID = ?", (ride_id,))
            row = cursor.fetchone()
            if row:
                existing_classification = row[0]
                existing_triptype = row[1]
                existing_sidecar = row[2]
        except Exception as query_err:
            logging.warning(f"Failed to query existing ride {ride_id} classification: {query_err}")

        # Bypass guardrail if the Tessie tag itself was explicitly changed in the Tessie app
        tessie_tag_changed = False
        if existing_sidecar and ride_id.startswith("TESSIE-"):
            try:
                old_sc = json.loads(existing_sidecar)
                old_tag = old_sc.get("tag")
                if not old_tag and "Sidecar_Artifact_JSON" in old_sc:
                    try:
                        nested = json.loads(old_sc["Sidecar_Artifact_JSON"])
                        old_tag = nested.get("tag")
                    except:
                        pass
                
                new_tag = trip_data.get("tag")
                if not new_tag and "Sidecar_Artifact_JSON" in trip_data:
                    try:
                        nested = json.loads(trip_data["Sidecar_Artifact_JSON"])
                        new_tag = nested.get("tag")
                    except:
                        pass
                        
                if (old_tag or "").strip().lower() != (new_tag or "").strip().lower():
                    tessie_tag_changed = True
                    logging.info(f"Tessie Tag Change Detected for {ride_id}: '{old_tag}' -> '{new_tag}'. Bypassing Ingestion Guardrail.")
            except Exception as sc_err:
                logging.warning(f"Failed to parse existing sidecar for {ride_id} tag comparison: {sc_err}")

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

        if is_existing_private and not is_incoming_private and not tessie_tag_changed:
            logging.info(f"Ingestion Guardrail: Preserving database classification '{existing_classification}' for {ride_id} (Blocked incoming update '{incoming_classification}')")
            incoming_classification = existing_classification
            incoming_triptype = 'Private'

        tessie_label = trip_data.get('Tessie_Label') or trip_data.get('tessie_label') or trip_data.get('tag')

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
            tessie_label,
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
            tessie_label,
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

    def upsert_location_intelligence(self, label: str, lat: float, lon: float, address: str, derived_type: str, timestamp_str: str) -> None:
        """
        Upserts a record in dbo.Location_Intelligence.
        Matches exactly by label + coordinates rounded to 5 decimal places.
        Increments frequency and updates confidence score for all locations with same label.
        """
        if not label or lat is None or lon is None:
            return
            
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        lat_rounded = round(float(lat), 6)
        lon_rounded = round(float(lon), 6)
        
        import datetime
        if not timestamp_str:
            timestamp_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
        try:
            # Check if record exists matching label and coordinates
            cursor.execute("""
                SELECT LocationID, Frequency FROM dbo.Location_Intelligence
                WHERE Tessie_Label = ? 
                  AND ABS(Latitude - ?) < 0.0001
                  AND ABS(Longitude - ?) < 0.0001
            """, (label, lat_rounded, lon_rounded))
            row = cursor.fetchone()
            
            if row:
                loc_id, freq = row
                new_freq = freq + 1
                
                # Get total occurrences of this label
                cursor.execute("SELECT SUM(Frequency) FROM dbo.Location_Intelligence WHERE Tessie_Label = ?", (label,))
                sum_row = cursor.fetchone()
                total_occurrences = (sum_row[0] or 0) + 1
                
                # Update existing record
                cursor.execute("""
                    UPDATE dbo.Location_Intelligence
                    SET Frequency = ?,
                        Last_Seen = ?,
                        Confidence_Score = CAST((? * 100.0) / ? AS DECIMAL(5,2))
                    WHERE LocationID = ?
                """, (new_freq, timestamp_str, new_freq, total_occurrences, loc_id))
                
                # Update other locations with same label
                cursor.execute("""
                    SELECT LocationID, Frequency FROM dbo.Location_Intelligence
                    WHERE Tessie_Label = ? AND LocationID <> ?
                """, (label, loc_id))
                other_rows = cursor.fetchall()
                for o_row in other_rows:
                    o_id, o_freq = o_row
                    cursor.execute("""
                        UPDATE dbo.Location_Intelligence
                        SET Confidence_Score = CAST((? * 100.0) / ? AS DECIMAL(5,2))
                        WHERE LocationID = ?
                    """, (o_freq, total_occurrences, o_id))
            else:
                cursor.execute("SELECT SUM(Frequency) FROM dbo.Location_Intelligence WHERE Tessie_Label = ?", (label,))
                sum_row = cursor.fetchone()
                total_occurrences = (sum_row[0] or 0) + 1
                
                confidence_score = float((1.0 / total_occurrences) * 100.0)
                
                # Insert new record
                cursor.execute("""
                    INSERT INTO dbo.Location_Intelligence (
                        Tessie_Label, Address, Latitude, Longitude, Derived_Type, First_Seen, Last_Seen, Frequency, Confidence_Score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (label, address, lat_rounded, lon_rounded, derived_type, timestamp_str, timestamp_str, confidence_score))
                
                # Update other locations with same label
                if total_occurrences > 1:
                    cursor.execute("""
                        SELECT LocationID, Frequency FROM dbo.Location_Intelligence
                        WHERE Tessie_Label = ?
                    """, (label,))
                    all_rows = cursor.fetchall()
                    for a_row in all_rows:
                        a_id, a_freq = a_row
                        cursor.execute("""
                            UPDATE dbo.Location_Intelligence
                            SET Confidence_Score = CAST((? * 100.0) / ? AS DECIMAL(5,2))
                            WHERE LocationID = ?
                        """, (a_freq, total_occurrences, a_id))
            
            conn.commit()
        except Exception as e:
            logging.error(f"Error upserting location intelligence: {e}")
            conn.rollback()
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
        - Unmatched/orphan private TESSIE- drives (surfaced explicitly)
        
        Uber_Dropoff records are intentionally hidden until a screenshot
        is matched to them to prevent ghost duplicates when manual entries exist.
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
          AND DeletedAt IS NULL
          AND (IsTest IS NULL OR IsTest = 0)
          AND (
            Fare > 0
            OR Classification = 'Manual_Entry'
            OR Classification = 'Uber_Matched'
            OR (
              RideID LIKE 'TESSIE-%'
              AND Classification NOT IN ('Uber_Dropoff', 'Uber_Matched', 'Manual_Entry')
              AND RideID NOT IN (
                SELECT DISTINCT Tessie_DriveID 
                FROM Rides.Rides 
                WHERE RideID LIKE 'INV-%' 
                  AND Tessie_DriveID IS NOT NULL
                  AND DeletedAt IS NULL
                  AND (IsTest IS NULL OR IsTest = 0)
              )
            )
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
        # Combined Uber + Private earnings per day.
        # UberEarnings dedup rule:
        #   days WITH TRIP-*  → only TRIP-* (canonical OCR)
        #   days WITHOUT TRIP-* → non-TESSIE/UBER legacy records (pre-OCR)
        # PrivateEarnings comes from Rides.PrivatePayments (Jackie/Daniel etc.)
        query = """
        WITH UberEarnings AS (
            SELECT
                CAST(Timestamp_Start AS DATE)          AS EarningDate,
                ISNULL(SUM(Driver_Earnings), 0)        AS TotalEarnings,
                ISNULL(SUM(Tip), 0)                    AS TotalTips,
                COUNT(*)                               AS TripCount,
                ISNULL(SUM(Distance_mi), 0.0)          AS TotalMiles,
                ISNULL(SUM(Duration_min) / 60.0, 0.0)  AS DriveTime_Hours
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
        ),
        PrivateEarnings AS (
            SELECT
                PaymentDate             AS EarningDate,
                ISNULL(SUM(Amount), 0)  AS TotalEarnings,
                0.0                     AS TotalTips,
                COUNT(*)                AS TripCount,
                0.0                     AS TotalMiles,
                0.0                     AS DriveTime_Hours
            FROM Rides.PrivatePayments
            WHERE PaymentDate >= CAST(? AS DATE)
              AND PaymentDate <= CAST(? AS DATE)
              AND DeletedAt IS NULL
            GROUP BY PaymentDate
        ),
        Combined AS (
            SELECT EarningDate,
                   ISNULL(SUM(TotalEarnings),   0)   AS TotalEarnings,
                   ISNULL(SUM(TotalTips),        0)   AS TotalTips,
                   ISNULL(SUM(TripCount),        0)   AS TripCount,
                   ISNULL(SUM(TotalMiles),       0.0) AS TotalMiles,
                   ISNULL(SUM(DriveTime_Hours),  0.0) AS DriveTime_Hours
            FROM (
                SELECT * FROM UberEarnings
                UNION ALL
                SELECT * FROM PrivateEarnings
            ) AS AllEarnings
            GROUP BY EarningDate
        )
        SELECT
            CONVERT(varchar(10), EarningDate, 23) AS DateStr,
            TotalEarnings, TotalTips, TripCount, TotalMiles, DriveTime_Hours
        FROM Combined
        ORDER BY EarningDate DESC
        """
        return self.execute_query_params(query, (start_date, end_date, start_date, end_date))


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

    # ── Private Payments ──────────────────────────────────────────────────────

    def get_private_payments(self, start_date: str, end_date: str) -> list:
        query = """
        SELECT
            PaymentID,
            Client,
            CAST(Amount AS FLOAT)                    AS Amount,
            ISNULL(Note, '')                         AS Note,
            CONVERT(varchar(10), PaymentDate, 23)    AS PaymentDate,
            CONVERT(varchar(19), Timestamp,   120)   AS Timestamp
        FROM Rides.PrivatePayments
        WHERE PaymentDate >= CAST(? AS DATE)
          AND PaymentDate <= CAST(? AS DATE)
          AND DeletedAt IS NULL
        ORDER BY Timestamp DESC
        """
        return self.execute_query_params(query, (start_date, end_date))

    def upsert_private_payments(self, payments: list) -> None:
        if not payments:
            return
        conn = self.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        query = """
        MERGE INTO Rides.PrivatePayments AS target
        USING (SELECT ? AS PaymentID) AS source
        ON (target.PaymentID = source.PaymentID)
        WHEN MATCHED AND target.DeletedAt IS NULL THEN
            UPDATE SET Client = ?, Amount = ?, Note = ?,
                       PaymentDate = CAST(? AS DATE),
                       Timestamp   = CAST(? AS DATETIME2)
        WHEN NOT MATCHED THEN
            INSERT (PaymentID, Client, Amount, Note, PaymentDate, Timestamp)
            VALUES (?, ?, ?, ?, CAST(? AS DATE), CAST(? AS DATETIME2));
        """
        try:
            for p in payments:
                pid    = str(p.get('id', ''))
                client = str(p.get('client', 'Private'))[:100]
                amount = float(p.get('amount', 0))
                note   = str(p.get('note', '') or '')[:500]
                date   = str(p.get('date', ''))
                ts     = str(p.get('timestamp', ''))
                if not pid or not date:
                    continue
                cursor.execute(query, (
                    pid,
                    client, amount, note, date, ts,
                    pid, client, amount, note, date, ts
                ))
            conn.commit()
        except Exception as e:
            logging.error(f"upsert_private_payments error: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            cursor.close()
            conn.close()

    def soft_delete_private_payment(self, payment_id: str) -> None:
        conn = self.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE Rides.PrivatePayments SET DeletedAt = GETDATE() WHERE PaymentID = ?",
                (str(payment_id),)
            )
            conn.commit()
        except Exception as e:
            logging.error(f"soft_delete_private_payment error: {e}")
        finally:
            cursor.close()
            conn.close()

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

    def get_known_client_names(self):
        import re
        conn = self.get_connection()
        if not conn:
            return ["jackie", "jacquelyn", "jacquelyn heslep", "esmeralda", "daniel", "ryan", "lauren", "terrance", "lorynne", "nancy", "adrienne", "david", "emerson"]
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT DISTINCT RideID 
                FROM Rides.Rides 
                WHERE RideID LIKE 'INV-%'
            """)
            names = {"jackie", "jacquelyn", "jacquelyn heslep", "esmeralda", "daniel", "ryan", "lauren", "terrance", "lorynne", "nancy", "adrienne", "david", "emerson"}
            for row in cursor.fetchall():
                if row[0]:
                    parts = row[0].split('-')
                    if len(parts) >= 2:
                        name = parts[1].lower()
                        name = re.sub(r'[^a-z]', '', name)
                        if name:
                            names.add(name)
            return list(names)
        except Exception as e:
            logging.error(f"Error getting known client names: {e}")
            return ["jackie", "jacquelyn", "jacquelyn heslep", "esmeralda", "daniel", "ryan", "lauren", "terrance", "lorynne", "nancy", "adrienne", "david", "emerson"]
        finally:
            conn.close()

