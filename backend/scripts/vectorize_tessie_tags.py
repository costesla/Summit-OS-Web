import os
import re
import hashlib
from datetime import datetime, timedelta, timezone

from services.config_loader import config_loader
from services.tessie import TessieClient
from services.vector_store import VectorStore


def normalize_text(s: str) -> str:
    # Trim + collapse whitespace
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def day_window_epoch(year: int, month: int, day: int):
    tz = timezone(timedelta(hours=-7))
    start_dt = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    return int(start_dt.timestamp()), int(end_dt.timestamp()), start_dt


def main():
    config_loader.load()

    client = TessieClient()
    vs = VectorStore()

    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        raise RuntimeError("TESSIE_VIN is not set in environment")

    start, end, start_dt = day_window_epoch(2026, 2, 23)
    drives = client.get_drives(vin, start, end) or []

    unique_terms = set()
    for d in drives:
        tag = d.get("tag")
        notes = d.get("notes")

        if tag:
            unique_terms.add(normalize_text(tag))
        if notes:
            unique_terms.add(normalize_text(notes))

    unique_terms = {t for t in unique_terms if t}  # drop empties after normalize

    print(f"Found {len(unique_terms)} unique metawords from Tessie.")

    day_key = start_dt.strftime("%Y%m%d")
    base_filename = f"tessie_tags_{day_key}.txt"

    successes = 0
    failures = 0

    for term in sorted(unique_terms):
        # Safer ID: SHA-256 truncated to 16 hex chars (~64 bits)
        h = hashlib.sha256(term.encode("utf-8")).hexdigest()[:16]
        artifact_id = f"TESSIE-META-{h}"

        content = f"Tessie Trip Custom Telemetry Metadata Word: '{term}'"
        metadata = {
            "artifact_id": artifact_id,
            "classification": "Private_Trip_Metadata",
            "timestamp_epoch": start,
            "day_key": day_key,
            "source": "tessie.get_drives",
            "vin": vin,
        }

        try:
            success = vs.add_document(
                filename=base_filename,
                content=content,
                metadata=metadata,
            )
            if success:
                successes += 1
                status = "SUCCESS"
            else:
                failures += 1
                status = "FAILED"
            print(f"Vectorized: '{term}' -> {status}")
        except Exception as e:
            failures += 1
            print(f"Failed to vectorize '{term}': {e}")

    print(f"Done. Successes: {successes}, Failures: {failures}")


if __name__ == "__main__":
    main()
