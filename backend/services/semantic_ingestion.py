import logging
import hashlib
from datetime import datetime
from .vector_store import VectorStore

class SemanticIngestionService:
    def __init__(self):
        self.vector_store = VectorStore()

    def ingest_tessie_drive(self, drive_data):
        """
        Transforms a Tesla drive into a vectorized semantic summary.
        Drive data can be raw from API or processed from SQL.
        """
        try:
            # Normalize timestamp
            ts = drive_data.get('started_at') or drive_data.get('Timestamp_Start')
            if isinstance(ts, int):
                dt = datetime.fromtimestamp(ts)
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts)
                except ValueError:
                    dt = datetime.utcnow() # Fallback
            else:
                dt = datetime.utcnow()

            # Extract key details
            ride_id = drive_data.get('RideID') or f"TES-{drive_data.get('uid')}"
            start_loc = drive_data.get('starting_location') or drive_data.get('Pickup_Location', 'Unknown')
            end_loc = drive_data.get('ending_location') or drive_data.get('Dropoff_Location', 'Unknown')
            tag = drive_data.get('tag') or drive_data.get('Classification', 'None')
            dist = float(drive_data.get('distance_miles') or drive_data.get('Distance_mi', 0))
            
            # Create the "Metaword" Summary
            summary = (
                f"Tesla Drive Activity [{ride_id}]: Traveled {dist:.1f} miles from {start_loc} to {end_loc} "
                f"on {dt.strftime('%Y-%m-%d %I:%M %p')}. Mission Tag: {tag}. "
                f"This mobility event represents operational usage of the Tesla fleet."
            )
            
            raw_hash = hashlib.sha256(summary.encode()).hexdigest()
            
            vector_data = {
                "vector_id": f"V-{ride_id}",
                "source_type": "Trip",
                "timestamp_utc": dt,
                "raw_text_hash": raw_hash,
                "source_pointer": ride_id,
                "derivation_reason": summary
            }
            
            return self.vector_store.add_vector(vector_data)
        except Exception as e:
            logging.error(f"Semantic Ingestion Failure (Tessie): {e}")
            return False

    def ingest_teller_transaction(self, tx_data):
        """
        Transforms a bank transaction into a vectorized semantic summary.
        """
        try:
            tx_id = tx_data.get('id')
            date_str = tx_data.get('date')
            dt = datetime.fromisoformat(date_str) if date_str else datetime.utcnow()
            
            merchant = tx_data.get('description') or tx_data.get('counterparty')
            amount = float(tx_data.get('amount', 0))
            category = tx_data.get('category') or tx_data.get('details', {}).get('category', 'General')
            
            action = "paid to" if amount < 0 else "received from"
            
            # Create the "Metaword" Summary
            summary = (
                f"Financial Transaction [{tx_id}]: Total of ${abs(amount):.2f} {action} {merchant} "
                f"on {dt.strftime('%Y-%m-%d')}. Category: {category}. "
                f"This transaction represents a financial operational event potentially related to business overhead."
            )
            
            raw_hash = hashlib.sha256(summary.encode()).hexdigest()
            
            vector_data = {
                "vector_id": f"V-{tx_id}",
                "source_type": "Artifact",
                "timestamp_utc": dt,
                "raw_text_hash": raw_hash,
                "source_pointer": tx_id,
                "derivation_reason": summary
            }
            
            return self.vector_store.add_vector(vector_data)
        except Exception as e:
            logging.error(f"Semantic Ingestion Failure (Teller): {e}")
            return False
