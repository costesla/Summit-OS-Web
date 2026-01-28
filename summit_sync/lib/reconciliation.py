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
        """
        logging.info(f"Starting reconciliation search (last {days_back} days)...")
        
        # 1. Get Unlinked Trips
        # We look for trips created recently that are 'Private' and missing a drive link
        conn = self.db.get_connection()
        if not conn:
            logging.error("No DB connection.")
            return

        cursor = conn.cursor()
        
        # SQL Server syntax for date math
        query = """
        SELECT TripID, Timestamp_Offer, CreatedAt, Duration_min 
        FROM Trips 
        WHERE TripType = 'Private' 
          AND Tessie_DriveID IS NULL 
          AND CreatedAt >= DATEADD(day, ?, GETDATE())
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

        conn.commit()
        conn.close()
        logging.info("Reconciliation complete.")

    def _process_trip(self, trip, cursor):
        trip_id = trip.get('TripID')
        
        # Prefer Timestamp_Offer (Booking Time) else CreatedAt
        # Note: CreatedAt is when the row was made, usually immediately after booking.
        # Timestamp_Offer is the scheduled time? Or the time the quote was generated?
        # For a "Private" trip, the user books a specific time. 
        # We need the ACTUAL time the trip happened.
        # If the trip is in the future, we won't find a drive.
        # We should check if the booking time has passed.
        
        target_time = trip.get('Timestamp_Offer') or trip.get('CreatedAt')
        if isinstance(target_time, datetime.datetime):
            target_ts = target_time.timestamp()
        else:
            logging.warning(f"Trip {trip_id} has invalid timestamp.")
            return

        # Don't check future trips
        if target_ts > datetime.datetime.now().timestamp():
            logging.debug(f"Skipping future trip {trip_id}")
            return

        # VIN is needed. Currently we assume single car or env var. 
        # Ideally Trip has a 'VehicleID' column but we default to env.
        import os
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            logging.error("No TESSIE_VIN env var.")
            return

        # Attempt Match
        # We pass target_time. Match logic looks for drives ENDING near this time? 
        # Or STARTING? 
        # `match_drive_to_trip` logic in tessie.py compares drive_end_ts with trip_end_timestamp.
        # But `Timestamp_Offer` is likely the START time of the booking.
        # If we have duration, we can estimate end time.
        
        duration_min = trip.get('Duration_min') or 30
        estimated_end_ts = target_ts + (duration_min * 60)

        drive = self.tessie.match_drive_to_trip(vin, estimated_end_ts, is_private=True)
        
        if drive:
            self._link_drive(cursor, trip_id, drive)

    def _link_drive(self, cursor, trip_id, drive):
        drive_id = drive.get('id')
        distance = drive.get('odometer_distance', 0)
        duration = (drive.get('ended_at', 0) - drive.get('started_at', 0)) / 60
        energy_kwh = drive.get('energy_consumed', 0)
        efficiency = drive.get('drive_efficiency', 0) # Wh/mi
        
        logging.info(f"Linking Trip {trip_id} <-> Drive {drive_id} ({distance} mi)")

        update_sql = """
        UPDATE Trips SET 
            Tessie_DriveID = ?,
            Tessie_Distance = ?,
            Tessie_Duration = ?,
            LastUpdated = GETDATE()
        WHERE TripID = ?
        """
        
        # We could also add Energy/Efficiency columns if DB supported them, 
        # but for now we map to existing schema.
        
        try:
            cursor.execute(update_sql, (drive_id, distance, duration, trip_id))
            logging.info(f"Successfully linked {trip_id}")
        except Exception as e:
            logging.error(f"Failed to update trip {trip_id}: {e}")

