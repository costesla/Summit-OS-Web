import os
import hashlib
from datetime import datetime, timedelta, timezone
from services.config_loader import config_loader; config_loader.load()
from services.tessie import TessieClient
from services.database import DatabaseClient
from services.vector_store import VectorStore
import logging

logging.basicConfig(level=logging.WARNING)

def main():
    client = TessieClient()
    db = DatabaseClient()
    vs = VectorStore()
    
    vin = os.environ.get('TESSIE_VIN')
    tz = timezone(timedelta(hours=-7))
    # Scope to Feb 23, 2026 local time
    start_dt = datetime(2026, 2, 23, 0, 0, 0, tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    
    charges = client.get_charges(vin, int(start_dt.timestamp()), int(end_dt.timestamp()))
    print(f'Found {len(charges)} charging sessions on Feb 23, 2026.')
    
    for c in charges:
        session_id = c.get('id')
        start_time = datetime.fromtimestamp(c.get('started_at')) if c.get('started_at') else None
        end_time = datetime.fromtimestamp(c.get('ended_at')) if c.get('ended_at') else None
        loc = c.get('saved_location') or c.get('location') or 'Unknown'
        
        charge_data = {
            'session_id': session_id,
            'start_time': start_time,
            'end_time': end_time,
            'location': loc,
            'energy_added': c.get('energy_added'),
            'cost': c.get('cost')
        }
        
        try:
            db.save_charge(charge_data)
            print(f'SUCCESS: Logged charge session {session_id} at {loc} ({c.get("energy_added")} kWh, ${c.get("cost")})')
        except Exception as e:
            print(f'ERROR: Failed to log charge session {session_id}: {e}')
            
        # Check for metawords
        tags = c.get('tags', [])
        notes = c.get('notes', '')
        metawords = set()
        
        if isinstance(tags, list):
            for t in tags: metawords.add(str(t).strip())
        elif tags:
            metawords.add(str(tags).strip())
            
        if notes:
            metawords.add(str(notes).strip())
            
        for mw in metawords:
            if not mw: continue
            
            content = f"Tessie Charging Custom Telemetry Metadata Word: '{mw}'"
            h = hashlib.sha256(mw.encode("utf-8")).hexdigest()[:16]
            artifact_id = f"TESSIE-CHARGE-META-{h}"
            metadata = {
                "artifact_id": artifact_id,
                "classification": "Charging_Session_Metadata",
                "timestamp_epoch": int(start_dt.timestamp()),
                "source": "tessie.get_charges",
                "vin": vin,
            }

            try:
                success = vs.add_document(
                    filename=f"tessie_charge_tags_20260223.txt",
                    content=content,
                    metadata=metadata,
                )
                status = "SUCCESS" if success else "FAILED"
                print(f"VECTORIZED Charge Metaword: '{mw}' -> {status}")
            except Exception as e:
                print(f"ERROR: Failed to vectorize '{mw}': {e}")
                
if __name__ == '__main__':
    main()
