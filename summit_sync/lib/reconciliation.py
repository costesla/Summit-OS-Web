import logging
import datetime
from lib.database import DatabaseClient
from lib.tessie import TessieClient

class ReconciliationEngine:
    def __init__(self):
        self.db = DatabaseClient()
        self.tessie = TessieClient()

    def reconcile_private_trips(self, days_back=7):
        """
        Finds private trips without a Tessie Drive ID and attempts to link them.
        Enforces daily chronological sequence integrity.
        """
        logging.info(f"Starting self-healing reconciliation search (last {days_back} days)...")
        
        conn = self.db.get_connection()
        if not conn:
            logging.error("No DB connection.")
            return

        cursor = conn.cursor()
        
        # 0. Standardize & Extract Passenger Names for all private trips within lookback window
        passenger_query = """
        SELECT TripID, Passenger_FirstName, Notes 
        FROM Trips 
        WHERE TripType = 'Private' 
          AND COALESCE(Timestamp_Offer, CreatedAt) >= DATEADD(day, ?, GETDATE())
        """
        try:
            cursor.execute(passenger_query, (-days_back,))
            trips_to_check = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
            for t in trips_to_check:
                current_p = t.get('Passenger_FirstName')
                if not current_p or not current_p.strip():
                    notes = t.get('Notes') or ''
                    import re
                    extracted_p = None
                    # Priority 2: Extract from Notes ("Booking for X")
                    match = re.search(r"Booking for\s+([A-Za-z0-9]+)", notes, re.IGNORECASE)
                    if match:
                        extracted_p = match.group(1).strip()
                    else:
                        match2 = re.search(r"Private Booking:\s+([A-Za-z0-9]+)", notes, re.IGNORECASE)
                        if match2:
                            extracted_p = match2.group(1).strip()
                    
                    # Priority 3: Fallback "Private"
                    if not extracted_p:
                        extracted_p = "Private"
                    
                    # Update DB
                    cursor.execute("UPDATE Trips SET Passenger_FirstName = ? WHERE TripID = ?", (extracted_p, t['TripID']))
            conn.commit()
        except Exception as pe_err:
            logging.error(f"Error standardizing passenger names: {pe_err}")
        
        # 1. Get Unlinked Trips
        query = """
        SELECT TripID, Timestamp_Offer, CreatedAt, Duration_min, Passenger_FirstName, Notes, Distance_mi
        FROM Trips 
        WHERE TripType = 'Private' 
          AND Tessie_DriveID IS NULL 
          AND COALESCE(Timestamp_Offer, CreatedAt) >= DATEADD(day, ?, GETDATE())
        """
        
        results = []
        try:
            cursor.execute(query, (-days_back,))
            columns = [column[0] for column in cursor.description]
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
        except Exception as e:
            logging.error(f"Error fetching unlinked trips: {e}")
            conn.close()
            return

        logging.info(f"Found {len(results)} unlinked private trips.")

        for trip in results:
            self._process_trip(trip, cursor)

        # 2. Daily Sequence Integrity Enforcement
        # Re-check all active passengers' chronological tags for the lookback period
        passengers_query = """
        SELECT DISTINCT Passenger_FirstName 
        FROM Trips 
        WHERE TripType = 'Private'
          AND Passenger_FirstName IS NOT NULL
          AND COALESCE(Timestamp_Offer, CreatedAt) >= DATEADD(day, ?, GETDATE())
        """
        try:
            cursor.execute(passengers_query, (-days_back,))
            passengers = [row[0] for row in cursor.fetchall() if row[0]]
        except Exception as pe:
            logging.error(f"Error fetching active passengers: {pe}")
            passengers = []

        import os
        vin = os.environ.get("TESSIE_VIN")

        for passenger in passengers:
            # Query all daily groups for this passenger in the lookback range
            days_query = """
            SELECT DISTINCT CAST(Timestamp_Offer AS DATE) as TripDate
            FROM Trips
            WHERE Passenger_FirstName = ?
              AND Timestamp_Offer >= DATEADD(day, ?, GETDATE())
            """
            try:
                cursor.execute(days_query, (passenger, -days_back))
                trip_dates = [row[0] for row in cursor.fetchall() if row[0]]
            except Exception as de:
                logging.error(f"Error fetching dates for {passenger}: {de}")
                trip_dates = []

            for t_date in trip_dates:
                self._enforce_sequence_integrity(cursor, passenger, t_date, vin)

        conn.commit()
        conn.close()
        logging.info("Reconciliation complete.")

    def _process_trip(self, trip, cursor):
        trip_id = trip.get('TripID')
        
        # Prefer Timestamp_Offer (Scheduled Time) else CreatedAt
        target_time = trip.get('Timestamp_Offer') or trip.get('CreatedAt')
        if isinstance(target_time, datetime.datetime):
            target_ts = target_time.timestamp()
        else:
            logging.warning(f"Trip {trip_id} has invalid timestamp.")
            return

        # 1. Skip future trips
        if target_ts > datetime.datetime.now().timestamp():
            logging.info(f"FUTURE_TRIP_SKIPPED: Trip {trip_id} scheduled for {target_time} is in the future.")
            return

        import os
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            logging.error("No TESSIE_VIN env var.")
            return

        duration_min = float(trip.get('Duration_min') or 30)
        estimated_end_ts = target_ts + (duration_min * 60)

        # 2. Candidate Matching Logic with Fallback and expanded search window
        # Primary window: ±4 hours
        ts_start_4h = int(estimated_end_ts - (3600 * 4))
        ts_end_4h = int(estimated_end_ts + (3600 * 4))
        drives = self.tessie.get_drives(vin, ts_start_4h, ts_end_4h)

        if not drives:
            # Fallback expanded window: ±6 hours
            logging.info(f"No match in primary ±4h window. Retrying with expanded ±6h window for Trip {trip_id}.")
            ts_start_6h = int(estimated_end_ts - (3600 * 6))
            ts_end_6h = int(estimated_end_ts + (3600 * 6))
            drives = self.tessie.get_drives(vin, ts_start_6h, ts_end_6h)

        if not drives:
            logging.info(f"NO_MATCH: No candidate Tessie drives found within ±6h for Trip {trip_id}.")
            return

        # 3. Candidate Drive Scoring & Ranking
        scored_candidates = []
        for d in drives:
            d_end_ts = d.get('ending_time') or d.get('ended_at')
            d_start_ts = d.get('started_at')
            if not d_end_ts or not d_start_ts:
                continue
                
            score = 100
            
            # (A) Ending time proximity: Deduct 1 point for every 2 minutes of difference
            time_diff_min = abs((d_end_ts - estimated_end_ts) / 60)
            score -= (time_diff_min / 2)
            
            # (B) Duration similarity: Deduct 1 point for every 1 minute of difference
            d_duration_min = (d_end_ts - d_start_ts) / 60
            dur_diff_min = abs(d_duration_min - duration_min)
            score -= dur_diff_min
            
            # (C) Distance similarity: Deduct 10 points for every 1 mile of difference (if booking has distance)
            d_distance_mi = d.get('distance') or d.get('distance_miles') or d.get('odometer_distance') or 0
            trip_distance_mi = float(trip.get('Distance_mi') or 0)
            if trip_distance_mi > 0:
                dist_diff_mi = abs(float(d_distance_mi) - trip_distance_mi)
                score -= (dist_diff_mi * 10)
                
            # Timezone drift check: log if difference matches common offset hour intervals (e.g. 1h, 2h, 6h, 7h)
            hours_diff = time_diff_min / 60.0
            if 0.9 <= hours_diff <= 1.1 or 1.9 <= hours_diff <= 2.1 or 5.9 <= hours_diff <= 6.1 or 6.9 <= hours_diff <= 7.1:
                logging.warning(f"TIMEZONE_DRIFT_DETECTED: Drive {d.get('id')} ends {hours_diff:.2f} hours from estimated end. Check UTC vs Local timezone offsets.")

            scored_candidates.append((score, d))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        if not scored_candidates:
            logging.info(f"NO_MATCH: Candidate drives failed basic validation for Trip {trip_id}.")
            return

        best_score, best_drive = scored_candidates[0]
        
        # Require minimum confidence score >= 60 before linking
        if best_score < 60:
            logging.info(f"LOW_CONFIDENCE_MATCH: Highest candidate drive {best_drive.get('id')} has score {best_score:.2f} (< 60 threshold) for Trip {trip_id}. Skipping.")
            return

        # 4. Success Match Link
        drive_id = best_drive.get('id')
        logging.info(f"MATCH: Selected Drive {drive_id} for Trip {trip_id} with score {best_score:.2f}.")
        
        self._link_drive(cursor, trip_id, best_drive)

    def _enforce_sequence_integrity(self, cursor, passenger, trip_date, vin):
        """
        Queries all daily trips for a passenger, verifies sequence order, and self-heals mismatch tags.
        """
        # Date string formatting for CAST check
        date_str = trip_date.strftime('%Y-%m-%d') if isinstance(trip_date, datetime.date) else str(trip_date)[:10]

        # Get all trips strictly ordered by Timestamp_Offer ASC, TripID ASC
        seq_query = """
        SELECT TripID, Tessie_DriveID, Classification, TripType FROM Trips
        WHERE (Passenger_FirstName = ? OR Notes LIKE ?)
          AND CAST(Timestamp_Offer AS DATE) = CAST(? AS DATE)
        ORDER BY Timestamp_Offer ASC, TripID ASC
        """
        try:
            cursor.execute(seq_query, (passenger, f"%{passenger}%", date_str))
            day_trips = [
                {
                    "trip_id": row[0],
                    "drive_id": row[1],
                    "classification": row[2],
                    "trip_type": row[3]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logging.error(f"Error fetching daily sequence for integrity check: {e}")
            return

        NUM_WORDS = {
            1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 
            6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"
        }

        for idx, t in enumerate(day_trips):
            trip_number = idx + 1
            trip_word = NUM_WORDS.get(trip_number, str(trip_number))
            expected_tag = f"{passenger} trip {trip_word}"
            
            drive_id = t["drive_id"]
            if not drive_id:
                # Trip exists but hasn't been matched to a drive yet
                continue
                
            current_tag = t["classification"]
            
            # Idempotency Rules: 
            # - If existing tag matches expected tag -> SKIP
            # - If differs, overwrite ONLY if TripType is Private. Otherwise SKIP.
            if current_tag == expected_tag:
                continue

            if t["trip_type"] != "Private":
                logging.debug(f"Idempotency: Skipped re-tagging Trip {t['trip_id']} (Expected '{expected_tag}', Actual '{current_tag}') because TripType is '{t['trip_type']}' (not Private).")
                continue

            # Inconsistency found -> Re-tag drive and update DB!
            logging.info(f"SEQUENCE_REBUILT: Re-tagging Trip {t['trip_id']} from '{current_tag}' to '{expected_tag}' to maintain chronological sequence.")
            
            # 1. Update Database
            try:
                cursor.execute(
                    "UPDATE Trips SET Classification = ?, LastUpdated = GETDATE() WHERE TripID = ?",
                    (expected_tag, t["trip_id"])
                )
                cursor.connection.commit()
            except Exception as db_err:
                logging.error(f"Failed to update sequence tag in DB: {db_err}")
                continue
                
            # 2. Tag drive in Tessie (fail-safe & non-blocking)
            if vin and drive_id:
                try:
                    tag_result = self.tessie.set_drive_tag(vin, drive_id, expected_tag)
                    if not tag_result:
                        logging.warning(f"TAG_FAILED: Tessie tagging API call failed for drive {drive_id} (tag: '{expected_tag}')")
                    else:
                        logging.info(f"TAG_SUCCESS: Tessie tag set to '{expected_tag}' for drive {drive_id}")
                except Exception as te:
                    logging.error(f"TAG_FAILED: Tessie tag request error: {te}")

    def _link_drive(self, cursor, trip_id, drive):
        drive_id = drive.get('id')
        distance = drive.get('odometer_distance', 0)
        duration = (drive.get('ended_at', 0) - drive.get('started_at', 0)) / 60
        
        logging.info(f"Linking Trip {trip_id} <-> Drive {drive_id} ({distance} mi)")

        update_sql = """
        UPDATE Trips SET 
            Tessie_DriveID = ?,
            Tessie_Distance = ?,
            Tessie_Duration = ?,
            LastUpdated = GETDATE()
        WHERE TripID = ?
        """
        
        try:
            cursor.execute(update_sql, (drive_id, distance, duration, trip_id))
            cursor.connection.commit()
            logging.info(f"Successfully linked & committed {trip_id}")
        except Exception as e:
            logging.error(f"Failed to update trip {trip_id}: {e}")
