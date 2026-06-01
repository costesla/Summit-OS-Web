import logging
import hashlib
from datetime import datetime
from .vector_store import VectorStore

class SemanticIngestionService:
    def __init__(self):
        self.vector_store = VectorStore()

    def ingest_tessie_drive(self, drive_data, telemetry_summary=""):
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
            ride_id = drive_data.get('RideID') or f"TES-{drive_data.get('id')}"
            start_loc = drive_data.get('starting_location') or drive_data.get('Pickup_Location', 'Unknown')
            end_loc = drive_data.get('ending_location') or drive_data.get('Dropoff_Location', 'Unknown')
            tag = drive_data.get('tag') or drive_data.get('Classification', 'None')
            dist = float(drive_data.get('distance_miles') or drive_data.get('Distance_mi', 0))
            
            # Create the "Metaword" Summary
            summary = (
                f"Tesla Drive Activity [{ride_id}]: Traveled {dist:.1f} miles from {start_loc} to {end_loc} "
                f"on {dt.strftime('%Y-%m-%d %I:%M %p')}. Mission Tag: {tag}. "
                f"{telemetry_summary} "
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

    def ingest_private_payment(self, payment: dict) -> bool:
        """
        Vectorizes a private cash/charter payment so the Copilot can answer
        semantic queries about Jackie, Daniel, Esmeralda, etc.
        """
        try:
            pid    = str(payment.get('id', ''))
            client = payment.get('client', 'Private')
            amount = float(payment.get('amount', 0))
            note   = payment.get('note', '') or ''
            date   = payment.get('date', '')
            ts_str = payment.get('timestamp', '')

            try:
                dt = datetime.fromisoformat(ts_str.replace('T', ' ')) if ts_str else datetime.utcnow()
            except ValueError:
                dt = datetime.utcnow()

            summary = (
                f"Private charter payment [{pid}]: ${amount:.2f} received from {client} "
                f"on {date}."
                + (f" Note: {note}." if note else "")
                + f" This is a direct booking cash payment outside of the Uber platform."
            )

            raw_hash = hashlib.sha256(summary.encode()).hexdigest()

            vector_data = {
                "vector_id":        f"V-PP-{pid}",
                "source_type":      "Trip",
                "timestamp_utc":    dt,
                "raw_text_hash":    raw_hash,
                "source_pointer":   f"PrivatePayments/{pid}",
                "derivation_reason": summary,
            }

            return self.vector_store.add_vector(vector_data)
        except Exception as e:
            logging.error(f"Semantic Ingestion Failure (PrivatePayment): {e}")
            return False

    def ingest_manual_expense(self, expense: dict, category: str) -> bool:
        """
        Vectorizes a manually entered expense (food, charging, maintenance) so
        the Copilot can answer spending queries across all expense types.
        """
        try:
            exp_id  = str(expense.get('id', ''))
            amount  = float(expense.get('amount') or expense.get('Amount') or 0)
            note    = str(expense.get('note') or expense.get('Note') or '').strip()
            ts      = str(expense.get('timestamp') or expense.get('Timestamp') or '')

            try:
                dt = datetime.fromisoformat(ts.replace('T', ' ')) if ts else datetime.utcnow()
            except ValueError:
                dt = datetime.utcnow()

            category_labels = {
                'FastFood':    'food and drink',
                'Charging':    'EV charging session',
                'Maintenance': 'capital / maintenance',
            }
            label = category_labels.get(category, category.lower())

            summary = (
                f"Manual expense [{exp_id}]: ${amount:.2f} for {label}"
                + (f' — {note}' if note else '')
                + f'. Logged on {dt.strftime("%Y-%m-%d")}.'
            )

            vector_data = {
                'vector_id':        f'V-EXP-{exp_id}',
                'source_type':      'Ops',
                'timestamp_utc':    dt,
                'raw_text_hash':    hashlib.sha256(summary.encode()).hexdigest(),
                'source_pointer':   f'ManualExpenses/{exp_id}',
                'derivation_reason': summary,
            }

            return self.vector_store.add_vector(vector_data)
        except Exception as e:
            logging.error(f'Semantic Ingestion Failure (ManualExpense): {e}')
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

