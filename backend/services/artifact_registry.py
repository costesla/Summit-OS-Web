"""
ArtifactRegistry — single source of truth for artifact lifecycle tracking.

Every ingested item (OCR trip, expense, drive, private payment, receipt, etc.)
gets a deterministic UUID v5 generated from its type + entity ID. This GUID is:
  - Stored in the Artifacts manifest table
  - Written as artifact_guid on the System_Vectors row
  - Used as the source_pointer URI: artifact://{guid}

UUID v5 is deterministic: re-ingesting the same entity always produces the
same GUID, so the registry is safe to call on every write without creating
duplicate artifacts.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional


# Fixed namespace for all SummitOS artifact GUIDs
_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def make_artifact_guid(artifact_type: str, entity_id: str) -> str:
    """
    Deterministic UUID v5 from artifact_type + entity_id.
    Identical inputs always produce the same GUID.
    """
    return str(uuid.uuid5(_NS, f"{artifact_type}:{entity_id}"))


def artifact_pointer(guid: str) -> str:
    """Standardised source_pointer URI for a given artifact GUID."""
    return f"artifact://{guid}"


class ArtifactRegistry:
    """
    Registers artifacts in the Artifacts manifest table and returns stable GUIDs.
    All DB operations are non-fatal — if the connection is unavailable the GUID
    is still computed and returned so downstream vectorisation is never blocked.
    """

    def __init__(self):
        # Lazy import to avoid circular deps
        from services.database import DatabaseClient
        self._db = DatabaseClient()

    def register(
        self,
        artifact_type: str,
        entity_id: str,
        entity_table: Optional[str] = None,
        source_path: Optional[str] = None,
        content_hash: Optional[str] = None,
        ingestion_path: Optional[str] = None,
    ) -> str:
        """
        Upsert an artifact record and return its stable GUID.

        Args:
            artifact_type:  'Trip' | 'Drive' | 'Expense' | 'Charge' |
                            'PrivatePayment' | 'Receipt' | 'Reconciliation'
            entity_id:      Primary key of the canonical record (e.g. 'TRIP-20260531-03')
            entity_table:   SQL table that owns the record (e.g. 'Rides.Rides')
            source_path:    Original file location (e.g. OneDrive path or 'manual://dashboard')
            content_hash:   SHA-256 of raw content (for dedup / integrity)
            ingestion_path: Which pipeline created it: 'OCR' | 'Tessie' | 'Manual' |
                            'CloudWatcher' | 'Reconciliation' | 'PrivatePayment'

        Returns:
            GUID string (always — even when DB write fails)
        """
        guid = make_artifact_guid(artifact_type, entity_id)

        conn = None
        try:
            conn = self._db.get_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    MERGE INTO Artifacts AS target
                    USING (SELECT ? AS artifact_guid) AS source
                    ON target.artifact_guid = source.artifact_guid
                    WHEN MATCHED THEN
                        UPDATE SET
                            source_path    = COALESCE(?, target.source_path),
                            content_hash   = COALESCE(?, target.content_hash),
                            status         = 'Active'
                    WHEN NOT MATCHED THEN
                        INSERT (artifact_guid, artifact_type, entity_table, entity_id,
                                source_path, content_hash, ingestion_path, ingested_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, GETUTCDATE(), 'Active');
                """, (
                    guid,
                    source_path, content_hash,          # UPDATE branch
                    guid, artifact_type, entity_table,   # INSERT branch
                    entity_id, source_path, content_hash, ingestion_path,
                ))
                conn.commit()
                cur.close()
        except Exception as e:
            logging.warning(f"[ArtifactRegistry] register failed (non-fatal): {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return guid

    def pointer(self, guid: str) -> str:
        """Return the standardised source_pointer URI for a GUID."""
        return artifact_pointer(guid)
