import logging
import datetime
import re
import json
import os
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
    # Unified logic: If month starts on Mon -> Week 1, else Week 2 for first full week
    offset = 1 if first_monday.day == 1 else 2
    return (dt.day - first_monday.day) // 7 + offset

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
                    
                    # Standardized folder name: M.DD.YY (e.g. 5.01.26)
                    short_year = dt.strftime("%y")
                    month_num = dt.month
                    day_padded = dt.strftime("%d")
                    folder_name = f"{month_num}.{day_padded}.{short_year}"
                    
                    target_folder = f"{self.target_root}/{year}/{month}/{week}/{folder_name}"
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
                
                # Standardized folder name: M.DD.YY (e.g. 5.01.26)
                short_year = dt.strftime("%y")
                month_num = dt.month
                day_padded = dt.strftime("%d")
                folder_name = f"{month_num}.{day_padded}.{short_year}"
                
                explicit_path = f"{self.target_root}/{year}/{month}/{week}/{folder_name}"
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
        non_images = [f for f in files if not f.get("name", "").lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif'))]
        if non_images:
            logs.append(f"INFO: Skipped {len(non_images)} non-image file(s) in folder (e.g. {', '.join([f.get('name') for f in non_images[:3]])}).")

        # Only OCR files that look like Uber Driver screenshots. Exclude by filename:
        #  - Starbucks/fast-food receipts, gas, scan files (unrelated expenses)
        #  - Samsung Print Spooler screenshots (printer confirmations parsed as Private trips)
        #  - Samsung Wallet specifically (payment app; never an Uber receipt)
        # NOTE: plain 'wallet' is intentionally NOT excluded — Uber has an in-app wallet screen
        #       that might be screenshot legitimately. Only 'samsung wallet' is excluded.
        _EXCLUDE_KEYWORDS = (
            'starbucks', 'scan_', 'receipt', 'gas', 'circle k', 'mcdonald',
            'print spooler', 'print_spooler', 'samsung wallet',
        )
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

                text_lower = text_for_stats.lower()

                # ── Content-based charging screen guard ─────────────────────────────
                # Tessie/Tesla charging screenshots (kWh, odometer, SOC) have no Uber
                # content and should be discarded. This catches them even when they have
                # a generic Samsung filename (e.g. Screenshot_20260514_084843.jpg).
                _EV_MARKERS   = ('total used', 'total added', 'kwh', 'odometer', 'since last charge',
                                 'electric cost', 'energy added', 'charging session', 'supercharger',
                                 'battery level', 'efficiency')
                _UBER_MARKERS = ('your earnings', 'you earned', 'uber driver', 'rider payment',
                                 'cos tesla', 'summitos', 'trip fare')
                _ev_hits   = sum(1 for m in _EV_MARKERS   if m in text_lower)
                _uber_hits = sum(1 for m in _UBER_MARKERS if m in text_lower)
                if _ev_hits >= 2 and _uber_hits == 0:
                    return None, f"SKIP: '{name}' — detected Tesla/EV charging screenshot ({_ev_hits} EV markers, 0 Uber markers)"

                # Check if it is a website reservation confirmation from COS Tesla / SummitOS
                is_website_booking = False
                if "cos tesla" in text_lower or "summitos" in text_lower:
                    if "booking" in text_lower and ("confirmed" in text_lower or "hello" in text_lower or "thank you for choosing" in text_lower):
                        is_website_booking = True

                if is_website_booking:
                    # ── Parse Private Website Booking ──
                    m_hello = re.search(r"Hello\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*,", text_for_stats)
                    passenger_name = m_hello.group(1).strip() if m_hello else "Private Client"
                    
                    m_total = re.search(r"Total\s*:?\s*\n?\s*\$?([0-9]+(?:\.[0-9]{2})?)", text_for_stats, re.IGNORECASE)
                    total_amount = float(m_total.group(1)) if m_total else 0.0
                    
                    m_dist = re.search(r"Distance\s*:?\s*\n?\s*([0-9.]+)\s*miles?", text_for_stats, re.IGNORECASE)
                    distance_mi = float(m_dist.group(1)) if m_dist else 0.0
                    
                    m_dur = re.search(r"Duration\s*:?\s*\n?\s*([0-9.]+)\s*minutes?", text_for_stats, re.IGNORECASE)
                    duration_min = float(m_dur.group(1)) if m_dur else 0.0
                    
                    pickup, dropoff = self._extract_route(text_for_stats)
                    
                    m_pickup_loc = re.search(r"Pickup Location\s*:?\s*\n?\s*(.+?)(?=\n\s*(?:Dropoff Location|Vehicle Type|Total|$))", text_for_stats, re.DOTALL | re.IGNORECASE)
                    if m_pickup_loc:
                        pickup = " ".join([line.strip() for line in m_pickup_loc.group(1).split("\n") if line.strip()])
                    
                    m_dropoff_loc = re.search(r"Dropoff Location\s*:?\s*\n?\s*(.+?)(?=\n\s*(?:Vehicle Type|Distance|Total|$))", text_for_stats, re.DOTALL | re.IGNORECASE)
                    if m_dropoff_loc:
                        dropoff = " ".join([line.strip() for line in m_dropoff_loc.group(1).split("\n") if line.strip()])
                        
                    # Extract Timestamp
                    trip_dt = None
                    m_pickup_time = re.search(r"Pickup\s*(?:Time)?\s*:?\s*\n?\s*([A-Za-z]+,\s*[A-Za-z]+\s+\d{1,2}\s+at\s+\d{1,2}:\d{2}\s*[APM]{2})", text_for_stats, re.IGNORECASE)
                    if m_pickup_time:
                        time_str = m_pickup_time.group(1).strip()
                        time_str_clean = re.sub(r"^[A-Za-z]+,\s*", "", time_str) 
                        time_str_clean = re.sub(r"\s+at\s+", " ", time_str_clean) 
                        
                        year = datetime.datetime.now(MDT).year
                        if date_str:
                            try:
                                year = datetime.datetime.strptime(date_str, "%Y-%m-%d").year
                            except:
                                pass
                        
                        m_hour = re.search(r"(\d{1,2}):(\d{2})", time_str_clean)
                        if m_hour:
                            hour = int(m_hour.group(1))
                            if hour > 12:
                                time_str_clean = re.sub(r"\s*[APM]{2}", "", time_str_clean)
                                fmt = "%B %d %H:%M"
                            else:
                                fmt = "%B %d %I:%M %p"
                        else:
                            fmt = "%B %d %I:%M %p"
                            
                        try:
                            trip_dt = datetime.datetime.strptime(f"{time_str_clean} {year}", f"{fmt} %Y")
                            trip_dt = trip_dt.replace(tzinfo=MDT)
                        except Exception as pe:
                            log.warning(f"Failed to parse booking time '{time_str_clean}': {pe}")
                            try:
                                trip_dt = datetime.datetime.strptime(f"{time_str_clean} {year}", f"{fmt.replace('%B', '%b')} %Y")
                                trip_dt = trip_dt.replace(tzinfo=MDT)
                            except Exception as pe2:
                                log.warning(f"Failed fallback parse: {pe2}")
                    
                    if not trip_dt:
                        try:
                            trip_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12, minute=0, tzinfo=MDT)
                        except:
                            trip_dt = datetime.datetime.now(MDT)
                            
                    classification = "Private_Trip"
                    if passenger_name and any(k in passenger_name.lower() for k in ["jacquelyn", "jackie"]):
                        classification = "Jackie"
                    elif passenger_name and any(k in passenger_name.lower() for k in ["nancy", "hernandez"]):
                        classification = "Private_Trip"
                        
                    card = {
                        "driver_earnings": total_amount,
                        "fare": total_amount,
                        "tip": 0.0,
                        "rider_payment": total_amount,
                        "is_private": True,
                        "passenger_name": passenger_name,
                        "classification": classification
                    }
                    
                    entry = {
                        "filename": name,
                        "text": text_for_stats,
                        "card": card,
                        "trip_dt": trip_dt,
                        "pickup": pickup,
                        "dropoff": dropoff,
                        "duration_min": duration_min,
                        "distance_mi": distance_mi,
                        "service_type": "Private Sedan" if "sedan" in text_lower else ("Private SUV" if "suv" in text_lower else "Private"),
                        "is_private": True
                    }
                    msg = f"PARSED: '{name}' (Private Booking) — Hello {passenger_name}, Total: ${total_amount:.2f} earned @ {str(trip_dt)[:16]}"
                    return entry, msg

                # ── Step A: GPT-4o Vision — accurate financial extraction ──────────
                import base64
                from openai import OpenAI
                import os, json as _json

                card = {"driver_earnings": 0.0, "fare": 0.0, "tip": 0.0, "rider_payment": 0.0}
                pickup = ""
                dropoff = ""
                trip_dt = None
                vdata = {}

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
                                        "This is a screenshot from the Uber Driver app. It could be a completed trip receipt OR a daily/weekly summary screen.\n"
                                        "Extract the data and return ONLY a JSON object with these keys:\n"
                                        "  is_uber_receipt: true if this is a single trip receipt\n"
                                        "  is_uber_summary: true if this is a daily/weekly summary screen showing total online time\n"
                                        "  you_earned: (for receipt) the large dollar amount at the very TOP\n"
                                        "  your_earnings: (for receipt) the amount next to 'Your earnings'\n"
                                        "  tip: (for receipt) the amount next to 'Tip' or 'Added tip'\n"
                                        "  rider_payment: (for receipt) the amount next to 'Rider payment'\n"
                                        "  trip_time: (for receipt) the date and time (e.g. 'May 8, 2026 · 5:40 AM')\n"
                                        "  online_time: (for summary) the total 'Online' time exactly as shown (e.g. '6h 15m')\n"
                                        "  duration_min: (for receipt) trip duration in minutes as a number (e.g. 24 or 24.5)\n"
                                        "  distance_mi: (for receipt) trip distance in miles as a number (e.g. 12.5)\n"
                                        "  pickup: (for receipt) pickup address or location if visible\n"
                                        "  dropoff: (for receipt) dropoff address or location if visible\n"
                                        "  service_type: (for receipt) service type like 'UberX', 'Comfort', 'UberXL', 'Black' if visible\n"
                                        "Return ONLY valid JSON, no markdown."
                                    )
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }],
                        max_tokens=300,
                        temperature=0,
                        timeout=15.0
                    )
                    raw = vision_resp.choices[0].message.content.strip()
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                    vdata = _json.loads(raw)

                    if vdata.get("is_uber_summary"):
                        ot = vdata.get("online_time", "Unknown")
                        log.info(f"SUMMARY DETECTED: {name} → Online Time: {ot}")
                        return None, f"SUMMARY: '{name}' — Online Time: {ot}"

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
                    if not pickup or not dropoff:
                        p_route, d_route = self._extract_route(text_for_stats)
                        pickup = pickup or p_route or ""
                        dropoff = dropoff or d_route or ""

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
                if duration_min is None or duration_min == 0.0:
                    try:
                        duration_min = float(vdata.get("duration_min") or 0.0)
                    except:
                        duration_min = 0.0

                distance_mi  = self._extract_distance(text_for_stats)
                if distance_mi is None or distance_mi == 0.0:
                    try:
                        distance_mi = float(vdata.get("distance_mi") or 0.0)
                    except:
                        distance_mi = 0.0

                service_type = self._extract_service_type(text_for_stats)
                if not service_type or service_type == "UberX":
                    gpt_service = vdata.get("service_type")
                    if gpt_service:
                        service_type = gpt_service
                if not service_type:
                    service_type = "UberX"

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
                    "is_private": False
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

        # 3b. Deduplication — if two screenshots of the SAME trip were captured
        #     (same driver_earnings ± $0.01 AND timestamps within 5 minutes), keep only the first.
        #     This prevents the "two screenshots of one receipt → two TRIP records" bug.
        import datetime as _dt
        deduped_cards = []
        for card in dated_cards:
            is_dup = False
            for existing in deduped_cards:
                earn_match = abs((card["card"].get("driver_earnings") or 0) - (existing["card"].get("driver_earnings") or 0)) <= 0.01
                if earn_match:
                    c_dt  = card["trip_dt"]
                    e_dt  = existing["trip_dt"]
                    if c_dt and e_dt:
                        # Normalise to naive for comparison
                        c_naive = c_dt.replace(tzinfo=None) if c_dt.tzinfo else c_dt
                        e_naive = e_dt.replace(tzinfo=None) if e_dt.tzinfo else e_dt
                        if abs((c_naive - e_naive).total_seconds()) <= 300:  # 5-minute window
                            is_dup = True
                            logs.append(f"DEDUP: '{card['filename']}' is a duplicate of '{existing['filename']}' (earn=${card['card'].get('driver_earnings'):.2f}, diff<5min) — skipped.")
                            break
                    elif not c_dt and not e_dt and earn_match:
                        # Both timestamps unknown — treat same-earnings as duplicate
                        is_dup = True
                        logs.append(f"DEDUP: '{card['filename']}' is a duplicate of '{existing['filename']}' (earn=${card['card'].get('driver_earnings'):.2f}, both no timestamp) — skipped.")
                        break
            if not is_dup:
                deduped_cards.append(card)
        if len(deduped_cards) < len(dated_cards):
            logs.append(f"INFO: Removed {len(dated_cards) - len(deduped_cards)} duplicate trip(s). {len(deduped_cards)} unique trips remain.")
        dated_cards = deduped_cards

        # 4. Sort chronologically by trip_dt (None last) — use tz-aware sentinel to avoid
        #    "can't compare offset-naive and offset-aware datetimes" crash
        _tz_aware_max = datetime.datetime.max.replace(tzinfo=MDT)
        dated_cards.sort(key=lambda c: c["trip_dt"] if c["trip_dt"] else _tz_aware_max)

        # 5. Delete any existing TRIP-{YYYYMMDD}-* records so re-scan is idempotent
        date_compact = date_str.replace("-", "")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
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
                    match = self.uber._find_match(trip_dt, tolerance_hours=4)
                    if match:
                        tessie_drive_id = match["RideID"]
                        trip_dt_naive = trip_dt.replace(tzinfo=None) if trip_dt.tzinfo else trip_dt
                        logs.append(f"LINK: {trip_id} matched to {tessie_drive_id} (diff: {abs((match['Timestamp_Start'] - trip_dt_naive).total_seconds())/60:.1f}m)")
                        
                        # --- NEW: Auto-tag the preceding 'Pickup' drive ---
                        # Look for a drive that ended within 60 mins before this one started
                        try:
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
                        except Exception as pickup_err:
                            logs.append(f"WARN: Failed to auto-tag pickup: {pickup_err}")

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

                # If it is a private trip, we should use 'Private' and the specific classification
                is_private = c.get("is_private", False)
                trip_type = "Private" if is_private else "Uber"
                classification = card.get("classification", "Uber_Matched") if is_private else "Uber_Matched"

                cursor.execute("""
                    INSERT INTO Rides.Rides
                    (RideID, TripType, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut,
                     Classification, Sidecar_Artifact_JSON, Tessie_DriveID, CreatedAt, LastUpdated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETUTCDATE(), GETUTCDATE())
                """, (
                    trip_id,
                    trip_type,
                    trip_dt or datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=MDT),
                    card.get("rider_payment") or 0,
                    card.get("driver_earnings") or 0,
                    card.get("tip") or 0,
                    uber_cut,
                    classification,
                    json.dumps(sidecar),
                    tessie_drive_id
                ))
                logs.append(f"SAVED: {trip_id} — Trip #{i} — ${card.get('driver_earnings', 0):.2f}")

                trips_out.append({
                    "trip_id": trip_id,
                    "trip_number": i,
                    "timestamp": trip_dt.isoformat() if trip_dt else None,
                    "time_display": trip_dt.strftime("%#I:%M %p" if os.name == "nt" else "%-I:%M %p") if trip_dt else "Unknown",
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
        except Exception as e:
            conn.rollback()
            logs.append(f"CRITICAL DATABASE ERROR: {e}. Transaction rolled back.")
            log.error(f"Database transaction rolled back for {date_str}: {e}")
            raise e
        finally:
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
            WHERE RideID LIKE ? AND (TripType = 'Uber' OR TripType IS NULL)
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

            trip_num = len(trips) + 1
            ts = r[1]
            ts_iso = ts.isoformat() if ts else None
            time_display = ts.strftime("%#I:%M %p" if os.name == "nt" else "%-I:%M %p") if ts else "Unknown"

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
    # PUBLIC: Scan daily OneDrive folder for expense receipts and process them
    # ─────────────────────────────────────────────────────────────────────────
    def scan_and_log_expenses(self, date_str: str, explicit_path: str = None) -> dict:
        """
        Scans an Uber Driver OneDrive folder, OCRs/Vision processes every receipt screenshot,
        and writes records to Rides.ManualExpenses and System_Vectors.
        """
        if not explicit_path:
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                year = dt.strftime("%Y")
                month = dt.strftime("%B")
                week_num = _calendar_week_of_month(dt)
                week = f"Week {week_num}"
                
                # Standardized folder name: M.DD.YY (e.g. 5.01.26)
                short_year = dt.strftime("%y")
                month_num = dt.month
                day_padded = dt.strftime("%d")
                folder_name = f"{month_num}.{day_padded}.{short_year}"
                
                explicit_path = f"{self.target_root}/{year}/{month}/{week}/{folder_name}"
            except Exception as e:
                return {"success": False, "error": f"Invalid date format: {e}", "expenses": [], "logs": [f"ERROR: {e}"]}

        logs = [f"START: Expense receipt scan for {date_str} in '{explicit_path}'"]

        # 1. List the folder
        try:
            files = self.graph.list_folder_files(explicit_path)
        except Exception as e:
            return {"success": False, "error": str(e), "expenses": [], "logs": [f"ERROR: {e}"]}

        if not files:
            return {"success": True, "expenses": [], "logs": logs + [f"INFO: Folder '{explicit_path}' is empty."]}

        # Filter for all images
        all_images = [f for f in files if f.get("name", "").lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif'))]
        non_images = [f for f in files if not f.get("name", "").lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif'))]
        if non_images:
            logs.append(f"INFO: Skipped {len(non_images)} non-image file(s) in folder (e.g. {', '.join([f.get('name') for f in non_images[:3]])}).")
        
        # Consider all unique images as expense candidates. 
        # Filename pre-filtering is avoided so that generic camera/screenshot filenames (e.g. Screenshot_*.jpg) are not missed.
        # The Vision AI model will accurately determine whether an image is indeed an expense receipt using is_expense_receipt.
        seen_ids = set()
        expense_files = []
        for f in all_images:
            if f.get("id") not in seen_ids:
                seen_ids.add(f.get("id"))
                expense_files.append(f)

        logs.append(f"INFO: Found {len(all_images)} images to process as potential expense receipts.")

        if not expense_files:
            return {"success": True, "expenses": [], "logs": logs + ["INFO: No image files found in folder."]}

        # OCR/Vision processing nested function
        def _ocr_and_extract_expense(file):
            name = file.get("name", "")
            item_id = file.get("id")
            try:
                # Extract capture date from filename (e.g. Screenshot_20260524_...)
                import re
                capture_date = date_str
                date_match = re.search(r'(20\d{6})', name)
                if date_match:
                    raw_date = date_match.group(1)
                    capture_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

                content = self.graph.get_file_content(item_id)
                import base64
                from openai import OpenAI
                import json as _json

                _oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                b64 = base64.b64encode(content).decode("utf-8")
                
                prompt = (
                    "This is an image of a business expense receipt or proof of payment. This includes paper/digital receipts (e.g. coffee, food, gas, parts, maintenance), AND mobile banking/credit card transaction screenshots (e.g. Chase, Amex, Apple Pay) that clearly document a business-related charge (such as 'TESLA SUPERCHARGER', fuel, tolls, or supplies).\n"
                    "Analyze the image and extract the transaction details.\n"
                    f"Note: This screenshot/image was captured on {capture_date}. If the screenshot mentions 'Today', 'Yesterday', or relative days, resolve them relative to the capture date {capture_date}.\n"
                    "Note on Charging/Tessie screenshots: If the screenshot displays both 'Electric Cost' and 'Fuel Cost' (gasoline equivalent comparison), the actual business expense amount paid is the 'Electric Cost' (e.g. $13.67), NOT the 'Fuel Cost' comparison (e.g. $25.22). Set the 'amount' to the 'Electric Cost' value, and the 'category' to 'Charging_Session'.\n"
                    "Return ONLY a JSON object with these keys:\n"
                    "  is_expense_receipt: true if this is a business expense receipt or a mobile banking transaction screenshot of a business-related charge (e.g. Tesla Supercharger, Starbucks, gas, shop maintenance). Return false if it is a completed Uber/ride-hailing trip receipt (where you earned money), a generic personal screen, or unrelated.\n"
                    "  merchant: Name of the business (e.g. 'Starbucks', 'McDonald\'s', 'Circle K', 'Shell', 'Tesla Supercharger')\n"
                    "  amount: Total transaction amount as a number (e.g. 15.45)\n"
                    "  tax: Tax amount as a number, if visible (otherwise 0.0)\n"
                    "  category: Select one from: 'Meal_Receipt', 'Fuel_Receipt', 'Maintenance', 'Charging_Session', 'ATM_Receipt', 'General_Expense'\n"
                    f"  date_time: The date and time of the transaction in YYYY-MM-DD HH:MM:SS format (e.g. '{capture_date} 08:32:00'). If time is not visible, use '12:00:00'. If date is not visible, resolve relative terms like 'Today' to {capture_date}, or estimate from context.\n"
                    "  items: List of items purchased, if readable (e.g. ['Grande Latte', 'Croissant']). For banking transactions with no items, return an empty list.\n"
                    "  currency: 'USD'\n"
                    "Return ONLY valid JSON, no markdown."
                )

                vision_resp = _oai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }],
                    max_tokens=400,
                    temperature=0,
                    timeout=15.0
                )
                
                raw = vision_resp.choices[0].message.content.strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
                vdata = _json.loads(raw)
                
                if not vdata.get("is_expense_receipt", True):
                    return None, f"SKIP: '{name}' — GPT classified as NOT an expense receipt"

                merchant = vdata.get("merchant", "Unknown Merchant").strip()
                amount = float(vdata.get("amount") or 0.0)
                tax = float(vdata.get("tax") or 0.0)
                category = vdata.get("category", "General_Expense")
                dt_str = vdata.get("date_time", "")
                items = vdata.get("items", [])
                
                if amount <= 0.0:
                    return None, f"SKIP: '{name}' — extracted amount is $0.00 or negative"
                
                # Parse date_time
                import datetime as _dt
                try:
                    parsed_dt = _dt.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except:
                    try:
                        parsed_dt = _dt.datetime.strptime(dt_str.split(" ")[0], "%Y-%m-%d")
                    except:
                        try:
                            parsed_dt = _dt.datetime.strptime(date_str, "%Y-%m-%d")
                        except:
                            parsed_dt = _dt.datetime.now()
                            
                parsed_dt = parsed_dt.replace(tzinfo=MDT)
                
                entry = {
                    "filename": name,
                    "item_id": item_id,
                    "content_bytes": content,
                    "merchant": merchant,
                    "amount": amount,
                    "tax": tax,
                    "category": category,
                    "date_time": parsed_dt,
                    "items": items
                }
                
                return entry, f"PARSED: '{name}' — {merchant} ${amount:.2f} ({category}) @ {dt_str}"
            except Exception as e:
                log.error(f"Error processing expense {name}: {e}")
                return None, f"ERROR: '{name}' — {e}"

        # 2. Parallel Processing with ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        raw_expenses = []
        logs.append(f"INFO: Starting parallel Vision analysis on {len(expense_files)} receipts (4 workers)...")
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_ocr_and_extract_expense, f): f for f in expense_files}
            for future in as_completed(futures):
                entry, msg = future.result()
                logs.append(msg)
                if entry:
                    raw_expenses.append(entry)

        if not raw_expenses:
            return {"success": True, "expenses": [], "logs": logs + ["INFO: No valid expense receipts parsed."]}

        # 3. Deduplication (same merchant, same amount, and within 10 minutes)
        deduped_expenses = []
        for exp in raw_expenses:
            is_dup = False
            for existing in deduped_expenses:
                same_merchant = exp["merchant"].lower() == existing["merchant"].lower()
                same_amount = abs(exp["amount"] - existing["amount"]) <= 0.01
                if same_merchant and same_amount:
                    # If both have valid datetimes, only treat as duplicate if within 10 minutes
                    t1 = exp.get("date_time")
                    t2 = existing.get("date_time")
                    if t1 and t2:
                        # Normalize to naive for comparison
                        t1_naive = t1.replace(tzinfo=None) if t1.tzinfo else t1
                        t2_naive = t2.replace(tzinfo=None) if t2.tzinfo else t2
                        time_diff = abs((t1_naive - t2_naive).total_seconds())
                        if time_diff <= 600:  # 10-minute window
                            is_dup = True
                            logs.append(f"DEDUP: '{exp['filename']}' is a duplicate of '{existing['filename']}' (same merchant/amount, diff {time_diff/60:.1f}m <= 10m) — skipped.")
                            break
                    else:
                        # Fallback if datetimes aren't both present: treat as duplicate
                        is_dup = True
                        logs.append(f"DEDUP: '{exp['filename']}' is a duplicate of '{existing['filename']}' (same merchant/amount, time missing) — skipped.")
                        break
            if not is_dup:
                deduped_expenses.append(exp)
        
        logs.append(f"INFO: {len(deduped_expenses)} unique expenses out of {len(raw_expenses)} parsed.")

        # 4. Clear existing manual expenses for the given date to ensure idempotence
        date_compact = date_str.replace("-", "")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT ExpenseID FROM Rides.ManualExpenses WHERE ExpenseID LIKE ?", (f"EXP-{date_compact}-%",))
        existing_rows = cursor.fetchall()
        if existing_rows:
            cursor.execute("DELETE FROM Rides.ManualExpenses WHERE ExpenseID LIKE ?", (f"EXP-{date_compact}-%",))
            conn.commit()
            logs.append(f"INFO: Cleared {len(existing_rows)} existing expense records in database for {date_str}.")

        try:
            cursor.execute("DELETE FROM System_Vectors WHERE source_pointer LIKE ?", (f"OneDrive://{explicit_path}/%",))
            conn.commit()
            if cursor.rowcount:
                logs.append(f"INFO: Cleared {cursor.rowcount} existing vector records for {date_str}.")
        except Exception as ve_err:
            log.warning(f"Failed to clear system vectors: {ve_err}")

        # 5. Persist to SQL and Vectorize
        from services.vector_store import VectorStore
        vs = VectorStore()
        
        expenses_out = []
        for i, exp in enumerate(deduped_expenses, start=1):
            exp_id = f"EXP-{date_compact}-{i:02d}"
            
            expense_data = {
                "id": exp_id,
                "category": exp["category"],
                "amount": exp["amount"],
                "note": f"Merchant: {exp['merchant']}. Items: {', '.join(exp['items'])}. File: {exp['filename']}",
                "timestamp": exp["date_time"]
            }
            
            try:
                self.db.save_manual_expense(expense_data)
                logs.append(f"SAVED: {exp_id} — {exp['merchant']} — ${exp['amount']:.2f}")
            except Exception as se_err:
                logs.append(f"ERROR saving expense {exp_id} to SQL: {se_err}")
                continue
            
            try:
                import hashlib
                timestamp_epoch = exp["date_time"].timestamp()
                raw_hash = hashlib.sha256(exp["content_bytes"]).hexdigest()
                
                vector_data = {
                    "vector_id": f"VEC-EXP-{hashlib.md5(exp['filename'].encode()).hexdigest()[:8]}-{int(timestamp_epoch)}",
                    "source_type": "Artifact",
                    "timestamp_utc": exp["date_time"],
                    "raw_text_hash": raw_hash,
                    "source_pointer": f"OneDrive://{explicit_path}/{exp['filename']}",
                    "derivation_reason": f"Verified Expense Receipt: {exp['merchant']} on {exp['date_time'].strftime('%Y-%m-%d')} for ${exp['amount']:.2f}. Items: {', '.join(exp['items'])}. Category: {exp['category']}. Filename: {exp['filename']}"
                }
                
                v_success = vs.add_vector(vector_data)
                if v_success:
                    logs.append(f"VECTOR: Vectorized and indexed '{exp['filename']}' successfully.")
                else:
                    logs.append(f"WARN: Failed to vectorize '{exp['filename']}'.")
            except Exception as vs_err:
                logs.append(f"ERROR vectorizing '{exp['filename']}': {vs_err}")
                
            expenses_out.append({
                "expense_id": exp_id,
                "merchant": exp["merchant"],
                "amount": exp["amount"],
                "tax": exp["tax"],
                "category": exp["category"],
                "date_time": exp["date_time"].isoformat(),
                "time_display": exp["date_time"].strftime("%#I:%M %p" if os.name == "nt" else "%-I:%M %p"),
                "items": exp["items"],
                "filename": exp["filename"]
            })
            
        cursor.close()
        
        total_amount = round(sum(e["amount"] for e in expenses_out), 2)
        logs.append(f"DONE: {len(expenses_out)} expenses saved/vectorized. Total amount: ${total_amount}")
        
        return {
            "success": True,
            "date": date_str,
            "expense_count": len(expenses_out),
            "total_amount": total_amount,
            "expenses": expenses_out,
            "logs": logs
        }

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
                        
                        # Standardized folder name: M.DD.YY (e.g. 5.01.26)
                        short_year = now.strftime("%y")
                        month_num = now.month
                        day_padded = now.strftime("%d")
                        folder_name = f"{month_num}.{day_padded}.{short_year}"

                        target_dir = f"{self.target_root}/{year}/{month}/{week}/{folder_name}"
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
