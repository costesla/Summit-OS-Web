"""
Diagnostic: simulate scan_and_number_trips for 2026-05-29
Prints every log line so we can see exactly what OCR found/skipped.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from services.cloud_watcher import CloudWatcherService

svc = CloudWatcherService()
result = svc.scan_and_number_trips("2026-05-29")

print(f"\n{'='*60}")
print(f"SUCCESS: {result.get('success')}")
print(f"TRIPS FOUND: {len(result.get('trips', []))}")
print(f"{'='*60}\n")

print("=== ALL LOGS ===")
for line in result.get("logs", []):
    print(line)

print("\n=== TRIPS ===")
for t in result.get("trips", []):
    print(f"  {t.get('trip_id')} | ${t.get('driver_earnings',0):.2f} | {t.get('timestamp')} | {t.get('classification')}")
