import logging
import datetime
import re
import json
from zoneinfo import ZoneInfo
from typing import Optional

def _calendar_week_of_month(dt: datetime.datetime) -> int:
    """Calendar week within the month, Mon-Sun. Week 1 covers the first Monday
    of the month; any days before that first Monday are also Week 1."""
    first = dt.replace(day=1)
    days_to_monday = (7 - first.weekday()) % 7
    first_monday = first + datetime.timedelta(days=days_to_monday)
    if dt.date() < first_monday.date():
        return 1
    return (dt.day - first_monday.day) // 7 + 1

from services.graph import GraphClient
from services.uber_matcher import UberMatcherService
from services.database import DatabaseClient

log = logging.getLogger(__name__)

MDT = ZoneInfo("America/Denver")


class CloudWatcherService:
    def __init__(self):
        self.graph = GraphClient()
        self.uber = UberMatcherService()
        self.db = DatabaseClient()
        self.camera_roll_path = "Pictures/Camera Roll"
        self.target_root = "Uber Driver"

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC: Original route-based scan (used by trigger-cloud-scan endpoint)
    # ─────────────────────────────────────────────────────────────────────────
    def scan_and_route(self, target_date: str = None, explicit_path: str = None) -> dict:
        """
        Scans OneDrive for new Uber screenshots and routes matched files.
        """
        scan_paths = []

        if explicit_path:
            scan_paths = [explicit_path]
        else:
            scan_paths = [self.camera_roll_path, "Pictures/Screenshots"]

            if target_date:
                try:
                    dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
                    year = dt.strftime("%Y")
                    month = dt.strftime("%B")
                    week_num = _calendar_week_of_month(dt)
                    week = f"Week {week_num}"
                    day = dt.strftime("%d")
                    target_folder = f"{self.target_root}/{year}/{month}/{week}/{day}"
                    if target_folder not in scan_paths:
                        scan_paths.append(target_folder)
                except Exception as e:
                    log.error(f"Error parsing target_date {target_date}: {e}")

        all_results = {
            "success": True,
            "scanned": 0,
            "processed": 0,
            "matched": 0,
            "errors": 0,
            "logs": []
        }

        all_results["logs"].append(f"START: Cloud Scan (Path: {explicit_path or scan_paths})")

        for path in scan_paths:
            all_results["logs"].append(f"SCAN: Checking OneDrive path '{path}'...")
            try:
                files = self.graph.list_folder_files(path)
                if not files:
                    all_results["logs"].append(f"INFO: Folder '{path}' is empty or not found.")
                    continue

                all_results["logs"].append(f"INFO: Found {len(files)} items in '{path}'.")
                all_results["scanned"] += len(files)
                self._process_files(files, path, all_results, target_date)
            except Exception as e:
                log.warning(f"Could not list folder {path}: {e}")
                all_results["logs"].append(f"WARN: Could not access '{path}': {str(e)}")

        return all_results

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC: Ordered trip numbering scan (used by scan-day-trips endpoint)
    # ─────────────────────────────────────────────────────────────────────────
    def scan_and_number_trips(self, date_str: str, explicit_path: str = None) -> dict:
        """
        Scans an Uber Driver OneDrive folder, OCRs every screenshot,
        sorts by the in-text trip timestamp, and writes numbered
        TRIP-{YYYYMMDD}-{N} records to Rides.Rides.

        Returns a summary dict with trips list for frontend display.
        """
        # Build the OneDrive path
        if not explicit_path:
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                year = dt.strftime("%Y")
                month = dt.strftime("%B")
                week_num = _calendar_week_of_month(dt)
                week = f"Week {week_num}"
                day = dt.strftime("%d")
                explicit_path = f"{self.target_root}/{year}/{month}/{week}/{day}"
            except Exception as e:
                return {"success": False, "error": f"Invalid date format: {e}", "trips": []}

        logs = [f"START: Ordered trip scan for {date_str} in '{explicit_path}'"]

        # 1. List the folder
        try:
            files = self.graph.list_folder_files(explicit_path)
        except Exception as e:
            return {"success": False, "error": str(e), "trips": [], "logs": [f"ERROR: {e}"]}

        if not files:
            return {"success": True, "trips": [], "logs": [f"INFO: Folder '{explicit_path}' is empty."]}

        all_images = [f for f in files if f.get("name", "").lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif'))]
        # Only OCR files that look like Uber Driver screenshots — exclude Starbucks receipts, scan files, etc.
        _EXCLUDE_KEYWORDS = ('starbucks', 'scan_', 'receipt', 'gas', 'circle k', 'mcdonald')
        image_files = [
            f for f in all_images
            if not any(kw in f.get("name", "").lower() for kw in _EXCLUDE_KEYWORDS)
        ]
        skipped = len(all_images) - len(image_files)
        logs.append(f"INFO: Found {len(all_images)} images; {len(image_files)} are Uber screenshots ({skipped} non-Uber files skipped).")

        # 2. OCR each file in parallel — drastically reduces wait time for large day folders
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _ocr_one(file):
            name = file.get("name", "")
            item_id = file.get("id")
            try:
                content = self.graph.get_file_content(item_id)
                
                # ── Step B: Azure Vision for literal text (timestamps, routes) ──
                text_for_stats = ""
                try:
                    text_for_stats = self.uber.ocr.analyze_image_bytes(content) or ""
                except Exception as ae:
                    log.warning(f"Azure OCR failed for {name}: {ae}")

                # ── Step A: GPT-4o Vision — accurate financial extraction ──────────
                import base64
                from openai import OpenAI
                import os, json as _json

                card = {"driver_earnings": 0.0, "fare": 0.0, "tip": 0.0, "rider_payment": 0.0}
                pickup = ""
                dropoff = ""
                trip_dt = None

                try:
                    _oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                    b64 = base64.b64encode(content).decode("utf-8")
                    vision_resp = _oai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "This is a screenshot from the Uber Driver app showing a completed trip receipt. "
                                        "Extract the financial data and return ONLY a JSON object with these keys:\n"
                                        "  you_earned: the large dollar amount at the very TOP of the screen (Total Driver Payout)\n"
                                        "  your_earnings: the dollar amount in the breakdown next to 'Your earnings' (Base Pay before tip)\n"
                                        "  tip: the dollar amount next to 'Tip' or 'Added tip' (0 if none)\n"
                                        "  rider_payment: the dollar amount next to 'Rider payment'\n"
                                        "  trip_time: the date and time exactly as shown (e.g. 'May 8, 2026 · 5:40 AM')\n"
                                        "  is_uber_receipt: true if this is an Uber Driver trip receipt\n"
                                        "Return ONLY valid JSON, no markdown."
                                    )
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}",
                                        "detail": "auto"
                                    }
                                }
                            ]
                        }],
                        max_tokens=300,
                        temperature=0
                    )
                    raw = vision_resp.choices[0].message.content.strip()
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                    vdata = _json.loads(raw)

                    if not vdata.get("is_uber_receipt", True):
                        return None, f"SKIP: '{name}' — GPT-4o says not an Uber receipt"

                    def _to_float(val):
                        if not val: return 0.0
                        if isinstance(val, (int, float)): return float(val)
                        # Remove $, commas, whitespace; keep digits and decimal point
                        cleaned = re.sub(r"[^\d.]", "", str(val))
                        try:
                            return float(cleaned)
                        except:
                            return 0.0

                    # Robust Earnings Extraction
                    you_earned = _to_float(vdata.get("you_earned"))
                    your_earnings = _to_float(vdata.get("your_earnings"))
                    tip_val = _to_float(vdata.get("tip"))
                    rider_pay = _to_float(vdata.get("rider_payment"))

                    # Final driver payout
                    final_earnings = max(you_earned, round(your_earnings + tip_val, 2))

                    card = {
                        "driver_earnings": final_earnings,
                        "fare": rider_pay,
                        "tip": tip_val,
                        "rider_payment": rider_pay,
                    }

                    # Prefer Azure for timestamp, fallback to GPT
                    trip_dt = self.uber._parse_timestamp_from_text(text_for_stats)
                    if not trip_dt and vdata.get("trip_time"):
                        trip_dt = self.uber._parse_timestamp_from_text(vdata["trip_time"])

                    pickup  = vdata.get("pickup", "") or ""
                    dropoff = vdata.get("dropoff", "") or ""

                    log.info(f"PROCESSED: {name} → earned=${card['driver_earnings']}, time={trip_dt}")

                except Exception as e:
                    log.error(f"Failed processing {name}: {e}")
                    # Final fallback to pure Azure if GPT dies
                    if not text_for_stats:
                        return None, f"ERROR: '{name}' — both GPT and Azure failed ({str(e)})"
                    
                    card_raw = self.uber._parse_uber_card(text_for_stats)
                    card = {
                        "driver_earnings": round((card_raw.get("driver_earnings") or 0) + (card_raw.get("tip") or 0), 2),
                        "fare": card_raw.get("fare", 0),
                        "tip": card_raw.get("tip", 0),
                        "rider_payment": card_raw.get("rider_payment", 0),
                    }
                    trip_dt = self.uber._parse_timestamp_from_text(text_for_stats)
                    pickup, dropoff = self._extract_route(text_for_stats)


                if card.get("driver_earnings", 0) == 0:
                    return None, f"SKIP: '{name}' — no earnings found"

                duration_min = self._extract_duration(text_for_stats)
                distance_mi  = self._extract_distance(text_for_stats)
                service_type = self._extract_service_type(text_for_stats) or "UberX"

                entry = {
                    "filename": name,
                    "text": text_for_stats,
                    "card": card,
                    "trip_dt": trip_dt,
                    "pickup": pickup,
                    "dropoff": dropoff,
                    "duration_min": duration_min,
                    "distance_mi": distance_mi,
                    "service_type": service_type,
                }
                msg = f"PARSED: '{name}' — ${card.get('driver_earnings', 0):.2f} earned @ {str(trip_dt)[:16] if trip_dt else 'no timestamp'}"
                return entry, msg
            except Exception as e:
                log.error(f"Error processing {name}: {e}")
                return None, f"ERROR: '{name}' — {e}"


        raw_cards = []
        logs.append(f"INFO: Starting parallel OCR on {len(image_files)} images (4 workers)...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_ocr_one, f): f for f in image_files}
            for future in as_completed(futures):
                entry, msg = future.result()
                logs.append(msg)
                if entry:
                    raw_cards.append(entry)


        if not raw_cards:
            return {"success": True, "trips": [], "logs": logs + ["INFO: No parseable trip cards found."]}

        # 3. Use all cards found in the folder for this dashboard day
        # (Be less strict with date check since it's already in the targeted day folder)
        dated_cards = raw_cards
        logs.append(f"INFO: Processing {len(dated_cards)} cards from folder for {date_str}.")

        # 4. Sort chronologically by trip_dt (None last) — use tz-aware sentinel to avoid
        #    "can't compare offset-naive and offset-aware datetimes" crash
        _tz_aware_max = datetime.datetime.max.replace(tzinfo=MDT)
        dated_cards.sort(key=lambda c: c["trip_dt"] if c["trip_dt"] else _tz_aware_max)

        # 5. Delete any existing TRIP-{YYYYMMDD}-* records so re-scan is idempotent
        date_compact = date_str.replace("-", "")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Rides.Rides WHERE RideID LIKE ?", (f"TRIP-{date_compact}-%",))
        deleted = cursor.rowcount
        if deleted:
            logs.append(f"INFO: Cleared {deleted} existing TRIP records for {date_str}.")

        # 6. Write numbered TRIP records & try to link to Tessie
        trips_out = []
        for i, c in enumerate(dated_cards, start=1):
            trip_id = f"TRIP-{date_compact}-{i:02d}"
            card = c["card"]
            trip_dt = c["trip_dt"]
            uber_cut = round((card.get("rider_payment") or 0) - (card.get("driver_earnings") or 0), 2)

            # --- Proximity Matching to Tessie ---
            tessie_drive_id = None
            if trip_dt:
                match = self.uber._find_match(trip_dt, tolerance_hours=2)
                if match:
                    tessie_drive_id = match["RideID"]
                    trip_dt_naive = trip_dt.replace(tzinfo=None) if trip_dt.tzinfo else trip_dt
                    logs.append(f"LINK: {trip_id} matched to {tessie_drive_id} (diff: {abs((match['Timestamp_Start'] - trip_dt_naive).total_seconds())/60:.1f}m)")
                    
                    # Update the matched Tessie drive with earnings data (this "labels" it in the UI)
                    try:
                        cursor.execute("""
                            UPDATE Rides.Rides
                            SET Fare = ?, Tip = ?, Driver_Earnings = ?, Platform_Cut = ?,
                                Classification = 'Uber_Matched', LastUpdated = GETUTCDATE()
                            WHERE RideID = ?
                        """, (
                            card.get("rider_payment") or 0,
                            card.get("tip") or 0,
                            card.get("driver_earnings") or 0,
                            uber_cut,
                            tessie_drive_id
                        ))

                        # --- NEW: Auto-tag the preceding 'Pickup' drive ---
                        # Look for a drive that ended within 30 mins before this one started
                        cursor.execute("""
                            SELECT TOP 1 RideID 
                            FROM Rides.Rides 
                            WHERE Timestamp_Start < ? 
                              AND Timestamp_Start > DATEADD(minute, -60, ?)
                              AND (Classification IS NULL OR Classification = 'Untagged')
                            ORDER BY Timestamp_Start DESC
                        """, (match['Timestamp_Start'], match['Timestamp_Start']))
                        pickup_row = cursor.fetchone()
                        if pickup_row:
                            pickup_id = pickup_row[0]
                            cursor.execute("""
                                UPDATE Rides.Rides 
                                SET Classification = 'Uber_Pickup', LastUpdated = GETUTCDATE() 
                                WHERE RideID = ?
                            """, (pickup_id,))
                            logs.append(f"AUTO-TAG: {pickup_id} labeled as Uber_Pickup")

                    except Exception as ue:
                        logs.append(f"WARN: Failed to update Tessie drive {tessie_drive_id}: {ue}")

            sidecar = {
                "source": "scan_and_number",
                "filename": c["filename"],
                "trip_number": i,
                "raw_text": c["text"][:500],
                "card_data": card,
                "pickup": c["pickup"],
                "dropoff": c["dropoff"],
                "duration_min": c["duration_min"],
                "distance_mi": c["distance_mi"],
                "service_type": c["service_type"],
                "tessie_link": tessie_drive_id,
                "scanned_at": datetime.datetime.now(MDT).isoformat(),
            }

            try:
                cursor.execute("""
                    INSERT INTO Rides.Rides
                    (RideID, TripType, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut,
                     Classification, Sidecar_Artifact_JSON, Tessie_DriveID, CreatedAt, LastUpdated)
                    VALUES (?, 'Uber', ?, ?, ?, ?, ?, 'Uber_Matched', ?, ?, GETUTCDATE(), GETUTCDATE())
                """, (
                    trip_id,
                    trip_dt or datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=MDT),
                    card.get("rider_payment") or 0,
                    card.get("driver_earnings") or 0,
                    card.get("tip") or 0,
                    uber_cut,
                    json.dumps(sidecar),
                    tessie_drive_id
                ))
                logs.append(f"SAVED: {trip_id} — Trip #{i} — ${card.get('driver_earnings', 0):.2f}")
            except Exception as e:
                logs.append(f"ERROR saving {trip_id}: {e}")
                log.error(f"Error inserting {trip_id}: {e}")
                continue

            trips_out.append({
                "trip_id": trip_id,
                "trip_number": i,
                "timestamp": trip_dt.isoformat() if trip_dt else None,
                "time_display": trip_dt.strftime("%-I:%M %p") if trip_dt else "Unknown",
                "service_type": c["service_type"] or "UberX",
                "driver_earnings": card.get("driver_earnings") or 0,
                "rider_payment": card.get("rider_payment") or 0,
                "tip": card.get("tip") or 0,
                "uber_cut": uber_cut,
                "pickup": c["pickup"],
                "dropoff": c["dropoff"],
                "duration_min": c["duration_min"],
                "distance_mi": c["distance_mi"],
                "filename": c["filename"],
            })

        conn.commit()
        cursor.close()

        total_earnings = round(sum(t["driver_earnings"] for t in trips_out), 2)
        logs.append(f"DONE: {len(trips_out)} trips saved. Total earnings: ${total_earnings}")

        return {
            "success": True,
            "date": date_str,
            "trip_count": len(trips_out),
            "total_earnings": total_earnings,
            "trips": trips_out,
            "logs": logs,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC: Fetch saved TRIP- records from SQL for a given date
    # ─────────────────────────────────────────────────────────────────────────
    def get_trips_for_date(self, date_str: str) -> list:
        """Fetches saved TRIP-{YYYYMMDD}-* records from SQL."""
        date_compact = date_str.replace("-", "")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT RideID, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut, Sidecar_Artifact_JSON
            FROM Rides.Rides
            WHERE RideID LIKE ?
            ORDER BY RideID ASC
        """, (f"TRIP-{date_compact}-%",))
        rows = cursor.fetchall()
        trips = []
        for r in rows:
            sidecar = {}
            try:
                sidecar = json.loads(str(r[6])) if r[6] else {}
            except:
                pass

            trip_num = sidecar.get("trip_number", 0)
            ts = r[1]
            ts_iso = ts.isoformat() if ts else None
            time_display = ts.strftime("%-I:%M %p") if ts else "Unknown"

            trips.append({
                "trip_id": r[0],
                "trip_number": trip_num,
                "timestamp": ts_iso,
                "time_display": time_display,
                "service_type": sidecar.get("service_type", "UberX"),
                "driver_earnings": float(r[3] or 0),
                "rider_payment": float(r[2] or 0),
                "tip": float(r[4] or 0),
                "uber_cut": float(r[5] or 0),
                "pickup": sidecar.get("pickup"),
                "dropoff": sidecar.get("dropoff"),
                "duration_min": sidecar.get("duration_min"),
                "distance_mi": sidecar.get("distance_mi"),
                "filename": sidecar.get("filename"),
            })
        return trips

    # ─────────────────────────────────────────────────────────────────────────
    # PRIVATE helpers
    # ─────────────────────────────────────────────────────────────────────────
    def _extract_route(self, text: str):
        """Extracts pickup and dropoff from OCR text."""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        pickup = None
        dropoff = None
        # Look for Colorado Springs address patterns
        for i, line in enumerate(lines):
            if re.search(r'(Colorado Springs|Denver|Pueblo|Aurora)', line, re.IGNORECASE):
                if not pickup:
                    pickup = line
                elif not dropoff:
                    dropoff = line
                    break
        # Fallback: look for "Rd", "St", "Blvd", "Dr", "Ave" addresses
        if not pickup:
            for line in lines:
                if re.search(r'\b(Rd|St|Blvd|Dr|Ave|Ln|Way|Ct|Vw|Hwy)\b', line):
                    if not pickup:
                        pickup = line
                    elif not dropoff and line != pickup:
                        dropoff = line
                        break
        return pickup, dropoff

    def _extract_duration(self, text: str) -> Optional[float]:
        """Extracts duration in minutes from OCR text."""
        m = re.search(r'(\d+)\s*min(?:\s+(\d+)\s*sec)?', text, re.IGNORECASE)
        if m:
            mins = int(m.group(1))
            secs = int(m.group(2)) if m.group(2) else 0
            return round(mins + secs / 60, 1)
        return None

    def _extract_distance(self, text: str) -> Optional[float]:
        """Extracts distance in miles from OCR text."""
        m = re.search(r'([\d.]+)\s*mi\b', text, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    def _extract_service_type(self, text: str) -> Optional[str]:
        """Extracts Uber service type from OCR text."""
        m = re.search(r'\b(UberX|Comfort|UberXL|Black|Pet|Green|UberX Share)\b', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return "UberX"

    def _process_files(self, files: list, source_path: str, results: dict, target_date: str):
        denver_tz = ZoneInfo("America/Denver")
        now = datetime.datetime.now(denver_tz)
        if target_date:
            try:
                now = datetime.datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=denver_tz)
            except:
                pass

        for file in files:
            name = file.get("name", "")
            results["logs"].append(f"FILE: Evaluating '{name}'...")

            if not name.lower().endswith(('.jpg', '.jpeg', '.png')):
                results["logs"].append(f"SKIP: '{name}' is not an image.")
                continue

            item_id = file.get("id")
            results["processed"] += 1

            try:
                content = self.graph.get_file_content(item_id)
                results["logs"].append(f"OCR: Analyzing '{name}' ({len(content)} bytes)...")
                process_result = self.uber.process_image_bytes(content, name)

                status = process_result.get("status")
                if status == "MATCHED":
                    results["matched"] += 1
                    results["logs"].append(
                        f"MATCH: '{name}' -> Ride {process_result.get('ride_id')} ($ {process_result.get('driver_earnings')})"
                    )

                    if source_path in [self.camera_roll_path, "Pictures/Screenshots"]:
                        year = now.strftime("%Y")
                        month = now.strftime("%B")
                        week_num = _calendar_week_of_month(now)
                        week = f"Week {week_num}"
                        day = now.strftime("%d")

                        target_dir = f"{self.target_root}/{year}/{month}/{week}/{day}"
                        results["logs"].append(f"MOVE: Routing '{name}' to {target_dir}...")
                        target_id = self.graph.ensure_path_exists(target_dir)
                        self.graph.move_file(item_id, target_id)
                        results["logs"].append(f"DONE: Moved '{name}' to organization tree.")
                else:
                    reason = process_result.get("reason") or process_result.get("message", "No reason provided")
                    results["logs"].append(f"SKIP: '{name}' status: {status} ({reason})")

            except Exception as e:
                results["errors"] += 1
                results["logs"].append(f"ERROR: Failed processing '{name}': {str(e)}")
                log.error(f"Error processing {name}: {e}")
