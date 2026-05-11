"""
fix_may4_matching.py
Matches May 4th UBER- records (created from May 5th screenshots of May 4th trips)
against unmatched Tessie Uber_Dropoff drives using timestamp proximity.
Then migrates the earnings data over and cleans up the orphaned UBER- records.
"""
import pyodbc
import datetime
import json
from datetime import timezone, timedelta

MDT = timezone(timedelta(hours=-6))

conn = pyodbc.connect(
    'Driver={ODBC Driver 18 for SQL Server};'
    'Server=tcp:summitsqlus23436.database.windows.net,1433;'
    'Database=SummitMediaDB;'
    'Uid=summitadmin;Pwd=Summ1tSync2026!Azure;'
    'Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)
cur = conn.cursor()

# ── 1. Get all UBER- records for May 4th trips (in-text date = May 4) ─────────
# These were filed under May 5th timestamps (filename) but contain May 4th trips
print("=== UBER- records with May 4th in-text dates ===")
cur.execute("""
    SELECT RideID, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut, Sidecar_Artifact_JSON
    FROM Rides.Rides
    WHERE RideID LIKE 'UBER-%'
      AND Sidecar_Artifact_JSON LIKE '%May 4, 2026%'
    ORDER BY Timestamp_Start
""")
uber_records = cur.fetchall()
print(f"Found {len(uber_records)} UBER- records referencing May 4 trips")

# ── 2. Get all unmatched Tessie Uber_Dropoff drives on May 4th ────────────────
cur.execute("""
    SELECT RideID, Timestamp_Start
    FROM Rides.Rides
    WHERE Classification IN ('Uber_Dropoff', 'Uber_DropOff')
      AND (Fare IS NULL OR Fare = 0)
      AND Timestamp_Start >= '2026-05-04 00:00:00'
      AND Timestamp_Start < '2026-05-05 00:00:00'
    ORDER BY Timestamp_Start
""")
tessie_drives = cur.fetchall()
print(f"Found {len(tessie_drives)} unmatched Tessie Uber_Dropoff drives on May 4th")
for t in tessie_drives:
    print(f"  {t[0]} | {str(t[1])[:16]}")

# ── 3. For each UBER- record, extract the in-text trip timestamp ──────────────
import re

def parse_intext_timestamp(sidecar_json_str):
    """Extract trip timestamp from OCR text embedded in sidecar JSON."""
    try:
        sidecar = json.loads(sidecar_json_str)
        raw_text = sidecar.get('raw_text', '')
        # Match: May 4, 2026 . 9:54 AM  or  May 4, 2026 · 9:54 AM
        m = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*[\.·]\s*(\d{1,2}:\d{2} [APM]{2})', raw_text)
        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            for fmt in ['%b %d, %Y %I:%M %p', '%B %d, %Y %I:%M %p']:
                try:
                    dt = datetime.datetime.strptime(f"{date_str} {time_str}", fmt)
                    return dt.replace(tzinfo=MDT)
                except:
                    continue
    except:
        pass
    return None

# ── 4. Match and migrate ───────────────────────────────────────────────────────
print("\n=== Matching UBER- records to Tessie drives ===")
matched_pairs = []
used_tessie_ids = set()

for uber_row in uber_records:
    uber_id, uber_ts, fare, earnings, tip, cut, sidecar_json = uber_row
    trip_dt = parse_intext_timestamp(str(sidecar_json))
    if not trip_dt:
        print(f"  SKIP {uber_id} — could not parse in-text timestamp")
        continue

    # Find closest unmatched Tessie drive within 90 minutes
    best_tessie = None
    best_diff = None
    for t in tessie_drives:
        if t[0] in used_tessie_ids:
            continue
        tessie_ts = t[1]
        if tessie_ts.tzinfo is None:
            tessie_ts = tessie_ts.replace(tzinfo=timezone.utc)
        diff = abs((trip_dt - tessie_ts.astimezone(MDT)).total_seconds())
        if diff < 90 * 60:  # within 90 minutes
            if best_diff is None or diff < best_diff:
                best_tessie = t
                best_diff = diff

    if best_tessie:
        used_tessie_ids.add(best_tessie[0])
        matched_pairs.append((uber_id, best_tessie[0], fare, earnings, tip, cut, sidecar_json, trip_dt, best_diff))
        print(f"  MATCH: {uber_id} (trip {str(trip_dt)[:16]}) -> {best_tessie[0]} ({str(best_tessie[1])[:16]}) diff={int(best_diff/60)}min")
    else:
        print(f"  NO MATCH for {uber_id} (trip {str(trip_dt)[:16]})")

print(f"\nTotal matches: {len(matched_pairs)}")

# ── 5. Apply migrations ───────────────────────────────────────────────────────
print("\n=== Applying migrations ===")
for uber_id, tessie_id, fare, earnings, tip, cut, sidecar_json, trip_dt, diff in matched_pairs:
    # Update the Tessie record with the earnings data
    cur.execute("""
        UPDATE Rides.Rides
        SET Fare = ?, Driver_Earnings = ?, Tip = ?, Platform_Cut = ?,
            Classification = 'Uber_Matched',
            Sidecar_Artifact_JSON = ?,
            LastUpdated = GETUTCDATE()
        WHERE RideID = ?
    """, (fare, earnings, tip, cut, sidecar_json, tessie_id))
    print(f"  Updated Tessie {tessie_id}: Earnings={earnings}, Fare={fare}")

# Delete the orphaned UBER- records
uber_ids_to_delete = [p[0] for p in matched_pairs]
if uber_ids_to_delete:
    placeholders = ','.join(['?' for _ in uber_ids_to_delete])
    cur.execute(f"DELETE FROM Rides.Rides WHERE RideID IN ({placeholders})", uber_ids_to_delete)
    print(f"\nDeleted {cur.rowcount} orphaned UBER- records")

conn.commit()

# ── 6. Final verification ─────────────────────────────────────────────────────
print("\n=== FINAL May 4th Summary ===")
cur.execute("""
    SELECT Classification, COUNT(*) as cnt, SUM(ISNULL(Driver_Earnings,0)) as total_earn
    FROM Rides.Rides
    WHERE Timestamp_Start >= '2026-05-04 00:00:00' AND Timestamp_Start < '2026-05-05 00:00:00'
    GROUP BY Classification
    ORDER BY Classification
""")
grand = 0.0
for r in cur.fetchall():
    earn = float(r[2])
    grand += earn
    print(f"  {r[0]}: {r[1]} rides | Earnings: ${round(earn,2)}")
print(f"Grand Total Driver Earnings: ${round(grand, 2)}")

cur.execute("""
    SELECT COUNT(*) FROM Rides.Rides
    WHERE Classification IN ('Uber_Dropoff', 'Uber_DropOff')
      AND (Fare IS NULL OR Fare = 0)
      AND Timestamp_Start >= '2026-05-04 00:00:00' AND Timestamp_Start < '2026-05-05 00:00:00'
""")
print(f"Still-unmatched Uber_Dropoff drives: {cur.fetchone()[0]}")
conn.close()
