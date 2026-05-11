"""
fix_may4_earnings.py
Re-parses the sidecar_artifact_json for all May 4th Uber_Matched rides
where Driver_Earnings is still $0 but Fare > 0, and corrects the earnings
by re-extracting from the raw OCR text.
"""
import pyodbc
import json
import re
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

def parse_earnings_from_text(raw_text):
    """Robust earnings extraction from OCR text."""
    if not raw_text:
        return 0.0, 0.0, 0.0  # driver, rider, tip

    driver_total = 0.0
    rider_payment = 0.0
    tip = 0.0

    # Try inline: "Your earnings $10.22"
    m = re.search(r'Your earnings\s*\$?\s*([0-9]+\.[0-9]{2})', raw_text, re.IGNORECASE)
    if m:
        driver_total = float(m.group(1))

    # Try inline: "Rider payment $12.78"
    m = re.search(r'Rider payment\s*\$?\s*([0-9]+\.[0-9]{2})', raw_text, re.IGNORECASE)
    if m:
        rider_payment = float(m.group(1))

    # Stacked layout fallback: "Your earnings\nRider payment\n$X.XX\n$Y.YY"
    if driver_total == 0.0:
        earnings_pos = re.search(r'Your earnings', raw_text, re.IGNORECASE)
        if earnings_pos:
            after = raw_text[earnings_pos.end():]
            amounts = re.findall(r'\$\s*([0-9]+\.[0-9]{2})', after)
            if amounts:
                if 'Rider payment' in after[:80] and len(amounts) >= 2:
                    driver_total = float(amounts[0])
                    rider_payment = float(amounts[1])
                else:
                    driver_total = float(amounts[0])

    # Tip: "Added tip $5.06"
    m = re.search(r'(?:Added tip|Tip)\s*\$?\s*([0-9]+\.[0-9]{2})', raw_text, re.IGNORECASE)
    if m:
        tip = float(m.group(1))

    # If rider_payment still 0, try upfront fare
    if rider_payment == 0.0:
        m = re.search(r'Upfront fare:\s*\$?\s*([0-9]+\.[0-9]{2})', raw_text, re.IGNORECASE)
        if m:
            rider_payment = float(m.group(1))
            if driver_total == 0.0:
                driver_total = rider_payment

    return driver_total, rider_payment, tip


# ── Fix rides where Driver_Earnings = 0 but they should have data ─────────────
print("=== Finding rides with zero Driver_Earnings but valid sidecar data ===")
cur.execute("""
    SELECT RideID, Driver_Earnings, Fare, Sidecar_Artifact_JSON
    FROM Rides.Rides
    WHERE Classification IN ('Uber_Matched')
      AND (Driver_Earnings IS NULL OR Driver_Earnings = 0)
      AND Fare > 0
      AND Timestamp_Start >= '2026-05-03 00:00:00'
      AND Timestamp_Start < '2026-05-06 00:00:00'
    ORDER BY Timestamp_Start
""")
rows = cur.fetchall()
print(f"Found {len(rows)} rides to fix")

fixed = 0
for r in rows:
    ride_id, curr_earnings, curr_fare, sidecar_json = r
    try:
        sidecar = json.loads(str(sidecar_json))
        raw_text = sidecar.get('raw_text', '')
        driver_total, rider_payment, tip = parse_earnings_from_text(raw_text)

        if driver_total > 0 or rider_payment > 0:
            platform_cut = round(rider_payment - driver_total, 2)
            # Update sidecar card_data too
            sidecar['card_data'] = {
                'fare': rider_payment,
                'driver_earnings': driver_total,
                'tip': tip,
                'rider_payment': rider_payment
            }
            cur.execute("""
                UPDATE Rides.Rides
                SET Driver_Earnings = ?, Fare = ?, Tip = ?, Platform_Cut = ?,
                    Sidecar_Artifact_JSON = ?, LastUpdated = GETUTCDATE()
                WHERE RideID = ?
            """, (driver_total, rider_payment, tip, platform_cut, json.dumps(sidecar), ride_id))
            print(f"  Fixed {ride_id}: Driver={driver_total}, Rider={rider_payment}, Tip={tip}, Cut={platform_cut}")
            fixed += 1
        else:
            print(f"  SKIP {ride_id} — could not extract earnings from OCR (raw: {raw_text[:100]})")
    except Exception as e:
        print(f"  ERROR on {ride_id}: {e}")

conn.commit()
print(f"\nFixed {fixed} rides")

# ── Final summary ─────────────────────────────────────────────────────────────
print("\n=== May 3-5 Final Earnings Summary ===")
for day_start, day_end, label in [
    ('2026-05-03 00:00:00', '2026-05-04 00:00:00', 'May 3rd'),
    ('2026-05-04 00:00:00', '2026-05-05 00:00:00', 'May 4th'),
    ('2026-05-05 00:00:00', '2026-05-06 00:00:00', 'May 5th'),
]:
    cur.execute("""
        SELECT SUM(ISNULL(Driver_Earnings, 0)), COUNT(*)
        FROM Rides.Rides
        WHERE Classification = 'Uber_Matched'
          AND Timestamp_Start >= ? AND Timestamp_Start < ?
    """, (day_start, day_end))
    row = cur.fetchone()
    print(f"  {label}: {row[1]} matched rides | ${round(float(row[0] or 0), 2)} driver earnings")

conn.close()
