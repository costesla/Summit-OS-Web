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
        #  - Outlook screenshots (booking confirmation emails — private trips handled by INV- sync)
        # NOTE: plain 'wallet' is intentionally NOT excluded — Uber has an in-app wallet screen
        #       that might be screenshot legitimately. Only 'samsung wallet' is excluded.
        _EXCLUDE_KEYWORDS = (
            'starbucks', 'scan_', 'receipt', 'gas', 'circle k', 'mcdonald',
            'print spooler', 'print_spooler', 'samsung wallet', 'outlook',
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
                        classification = "Jacquelyn Heslep"
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

                    # If GPT returned 0 for all earnings fields, try rider_payment as emergency
                    # fallback (some Uber receipt screenshots show "Rider payment" prominently)
                    if final_earnings == 0 and rider_pay > 0:
                        # Estimate driver earnings as ~80% of rider payment (Uber's typical split)
                        # This is only used when nothing else was extracted
                        final_earnings = round(rider_pay * 0.80, 2)
                        log.warning(f"GPT earnings=0 for {name}; using rider_pay×0.80 = ${final_earnings:.2f} as emergency fallback")

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


                # If earnings still 0 after all extraction attempts, try Azure OCR as last resort
                if card.get("driver_earnings", 0) == 0 and text_for_stats:
                    card_raw = self.uber._parse_uber_card(text_for_stats)
                    azure_earnings = round((card_raw.get("driver_earnings") or 0) + (card_raw.get("tip") or 0), 2)
                    if azure_earnings > 0:
                        log.info(f"RECOVERY: '{name}' — Azure OCR recovered earnings=${azure_earnings:.2f} (GPT missed it)")
                        card["driver_earnings"] = azure_earnings
                        card["fare"] = card.get("fare") or card_raw.get("fare", 0)
                        card["tip"] = card.get("tip") or card_raw.get("tip", 0)
                        card["rider_payment"] = card.get("rider_payment") or card_raw.get("rider_payment", 0)

                if card.get("driver_earnings", 0) == 0:
                    return None, f"SKIP: '{name}' — no earnings found (GPT + Azure both returned $0)"

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
            logs.append("INFO: No parseable trip cards found.")
            # Run Private Booking Sync even when no Uber screenshots exist!
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                self.sync_private_bookings_for_date(date_str, cursor, logs)
                conn.commit()
                cursor.close()
            except Exception as e:
                logs.append(f"PRIVATE-SYNC-ERROR: Failed during fallback execution: {e}")
            return {"success": True, "trips": [], "logs": logs}

        # 3. Use all cards found in the folder for this dashboard day
        # (Be less strict with date check since it's already in the targeted day folder)
        dated_cards = raw_cards
        logs.append(f"INFO: Processing {len(dated_cards)} cards from folder for {date_str}.")

        # 3b. Deduplication — if two screenshots of the SAME trip were captured
        #     (same driver_earnings ± $0.01 AND timestamps within 5 minutes), keep only the first.
        #     This prevents the "two screenshots of one receipt → two TRIP records" bug.
        #     GUARD: If the screenshots' *filename* timestamps are >10 minutes apart,
        #     they are clearly different trips even if GPT extracted the same OCR timestamp.
        import datetime as _dt

        def _filename_ts(fname: str):
            """Extract datetime from filename like Screenshot_20260602_161642_..."""
            m = re.search(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', fname or '')
            if m:
                try:
                    return _dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                        int(m.group(4)), int(m.group(5)), int(m.group(6)))
                except:
                    pass
            return None

        deduped_cards = []
        for card in dated_cards:
            is_dup = False
            for existing in deduped_cards:
                earn_match = abs((card["card"].get("driver_earnings") or 0) - (existing["card"].get("driver_earnings") or 0)) <= 0.01
                if earn_match:
                    # Check screenshot capture timestamps first — if files were taken
                    # >10 min apart, they are different trips regardless of OCR results
                    f_ts_card = _filename_ts(card.get("filename"))
                    f_ts_existing = _filename_ts(existing.get("filename"))
                    if f_ts_card and f_ts_existing:
                        capture_diff = abs((f_ts_card - f_ts_existing).total_seconds())
                        if capture_diff > 600:  # >10 minutes apart
                            continue  # Not a duplicate — different capture times

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

            # Reset any TESSIE- drives for this date that were previously matched (Classification='Uber_Matched')
            # back to their original Tessie classification based on the sidecar tag.
            try:
                cursor.execute("""
                    SELECT RideID, Sidecar_Artifact_JSON
                    FROM Rides.Rides
                    WHERE RideID LIKE 'TESSIE-%'
                      AND CAST(Timestamp_Start AS DATE) = ?
                      AND Classification = 'Uber_Matched'
                """, (date_str,))
                to_reset = cursor.fetchall()
                if to_reset:
                    from services.tessie_sync import TessieSyncService
                    sync_service = TessieSyncService()
                    reset_count = 0
                    for r_id, sc_json in to_reset:
                        orig_tag = None
                        if sc_json:
                            try:
                                sc = json.loads(sc_json)
                                orig_tag = sc.get("tag")
                            except:
                                pass
                        cls = sync_service._classify_drive(orig_tag)
                        tt = "Uber" if "uber" in (orig_tag or "").lower() else "Private"
                        cursor.execute("""
                            UPDATE Rides.Rides
                            SET Classification = ?, TripType = ?, LastUpdated = GETUTCDATE()
                            WHERE RideID = ?
                        """, (cls, tt, r_id))
                        reset_count += 1
                    logs.append(f"INFO: Reset {reset_count} previously matched TESSIE drives back to original states.")
            except Exception as reset_err:
                logs.append(f"WARN: Failed to reset matched Tessie drives: {reset_err}")

            # 6. Write numbered TRIP records & try to link to Tessie
            trips_out = []
            matched_tessie_ids = set()
            for i, c in enumerate(dated_cards, start=1):
                trip_id = f"TRIP-{date_compact}-{i:02d}"
                card = c["card"]
                trip_dt = c["trip_dt"]
                uber_cut = round((card.get("rider_payment") or 0) - (card.get("driver_earnings") or 0), 2)

                # Determine private trip fields early
                is_private = c.get("is_private", False)
                trip_type = "Private" if is_private else "Uber"
                classification = card.get("classification", "Uber_Matched") if is_private else "Uber_Matched"

                # --- Proximity Matching to Tessie ---
                # NOTE: Private trips skip _find_match here — their Tessie linkage is handled
                # exclusively by sync_private_bookings_for_date (INV- records).
                # Allowing private booking screenshots to call _find_match causes them to
                # steal Tessie drives that should be matched to Uber trips (crosstalk).
                tessie_drive_id = None
                tessie_telemetry = {}
                if trip_dt and not is_private:
                    match = self.uber._find_match(trip_dt, tolerance_hours=4, exclude_ids=matched_tessie_ids)
                    if match:
                        tessie_drive_id = match["RideID"]
                        matched_tessie_ids.add(tessie_drive_id)
                        trip_dt_naive = trip_dt.replace(tzinfo=None) if trip_dt.tzinfo else trip_dt
                        logs.append(f"LINK: {trip_id} matched to {tessie_drive_id} (diff: {abs((match['Timestamp_Start'] - trip_dt_naive).total_seconds())/60:.1f}m)")
                        
                        # Fetch the telemetry from the matched Tessie drive row in SQL
                        try:
                            cursor.execute("""
                                SELECT Distance_mi, Duration_min, Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi, Pickup_Location, Dropoff_Location
                                FROM Rides.Rides
                                WHERE RideID = ?
                            """, (tessie_drive_id,))
                            tel_row = cursor.fetchone()
                            if tel_row:
                                def _f(v): return float(v) if v is not None else None
                                tessie_telemetry = {
                                    "Distance_mi": _f(tel_row[0]),
                                    "Duration_min": _f(tel_row[1]),
                                    "Start_SOC": _f(tel_row[2]),
                                    "End_SOC": _f(tel_row[3]),
                                    "Energy_Used_kWh": _f(tel_row[4]),
                                    "Efficiency_Wh_mi": _f(tel_row[5]),
                                    "Pickup_Location": tel_row[6],
                                    "Dropoff_Location": tel_row[7]
                                }
                        except Exception as tel_err:
                            logs.append(f"WARN: Failed to fetch telemetry for matched Tessie drive {tessie_drive_id}: {tel_err}")

                        # Update the original Tessie drive in SQL so it is marked as Uber
                        try:
                            cursor.execute("""
                                UPDATE Rides.Rides
                                SET TripType = ?, Classification = ?, LastUpdated = GETUTCDATE()
                                WHERE RideID = ?
                            """, (trip_type, classification, tessie_drive_id))
                            logs.append(f"UPDATE-TESSIE: Matched Tessie drive {tessie_drive_id} updated to TripType={trip_type}, Classification={classification}")
                        except Exception as update_err:
                            logs.append(f"WARN: Failed to update matched Tessie drive classification: {update_err}")

                elif is_private:
                    logs.append(f"SKIP-TESSIE-MATCH: {trip_id} is Private — Tessie linkage handled by sync_private_bookings_for_date")


                sidecar = {
                    "source": "scan_and_number",
                    "filename": c["filename"],
                    "trip_number": i,
                    "raw_text": c["text"][:500],
                    "card_data": card,
                    "pickup": c["pickup"] or tessie_telemetry.get("Pickup_Location"),
                    "dropoff": c["dropoff"] or tessie_telemetry.get("Dropoff_Location"),
                    "duration_min": c["duration_min"] or tessie_telemetry.get("Duration_min"),
                    "distance_mi": c["distance_mi"] or tessie_telemetry.get("Distance_mi"),
                    "service_type": c["service_type"],
                    "tessie_link": tessie_drive_id,
                    "scanned_at": datetime.datetime.now(MDT).isoformat(),
                }

                cursor.execute("""
                    INSERT INTO Rides.Rides
                    (RideID, TripType, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut,
                     Classification, Sidecar_Artifact_JSON, Tessie_DriveID, 
                     Distance_mi, Duration_min, Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi,
                     Pickup_Location, Dropoff_Location, CreatedAt, LastUpdated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETUTCDATE(), GETUTCDATE())
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
                    tessie_drive_id,
                    tessie_telemetry.get("Distance_mi"),
                    tessie_telemetry.get("Duration_min"),
                    tessie_telemetry.get("Start_SOC"),
                    tessie_telemetry.get("End_SOC"),
                    tessie_telemetry.get("Energy_Used_kWh"),
                    tessie_telemetry.get("Efficiency_Wh_mi"),
                    c["pickup"] or tessie_telemetry.get("Pickup_Location"),
                    c["dropoff"] or tessie_telemetry.get("Dropoff_Location")
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

            # Call Private Booking Sync to link INV- records with Tessie drives!
            self.sync_private_bookings_for_date(date_str, cursor, logs)

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
        """Fetches saved TRIP-{YYYYMMDD}-* and INV-* records from SQL (both Uber and Private)."""
        date_compact = date_str.replace("-", "")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT RideID, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut,
                   Sidecar_Artifact_JSON, TripType, Classification, PaymentStatus,
                   PaidAt, PaymentMethod
            FROM Rides.Rides
            WHERE ((RideID LIKE 'TRIP-%' AND RideID LIKE ?) OR (RideID LIKE 'INV-%' AND CAST(Timestamp_Start AS DATE) = ?))
              AND DeletedAt IS NULL
              AND (IsTest = 0 OR IsTest IS NULL)
            ORDER BY Timestamp_Start ASC, RideID ASC
        """, (f"TRIP-{date_compact}-%", date_str))
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
            trip_type = r[7] or "Uber"  # default Uber for legacy records without TripType
            classification = r[8] or "Uber_Matched"

            # For private trips, uber_cut is meaningless (we keep full fare)
            uber_cut = float(r[5] or 0) if trip_type == "Uber" else 0.0

            # Private trips keep the full fare, so driver_earnings falls back to Fare if NULL or 0.0
            is_private = (trip_type == "Private" or r[0].startswith("INV-"))
            driver_earnings = float(r[3] if (r[3] is not None and float(r[3]) != 0.0) else (r[2] or 0)) if is_private else float(r[3] or 0)

            # Resolve passenger name with fallbacks for private bookings
            passenger_name = (
                sidecar.get("card_data", {}).get("passenger_name")
                or sidecar.get("passenger_name")
                or sidecar.get("customerName")
                or sidecar.get("name")
            )

            trips.append({
                "trip_id": r[0],
                "trip_number": trip_num,
                "trip_type": trip_type,
                "classification": classification,
                "timestamp": ts_iso,
                "time_display": time_display,
                "service_type": sidecar.get("service_type", "Private" if trip_type == "Private" else "UberX"),
                "driver_earnings": driver_earnings,
                "rider_payment": float(r[2] or 0),
                "tip": float(r[4] or 0),
                "uber_cut": uber_cut,
                "pickup": sidecar.get("pickup"),
                "dropoff": sidecar.get("dropoff"),
                "duration_min": sidecar.get("duration_min"),
                "distance_mi": sidecar.get("distance_mi"),
                "filename": sidecar.get("filename"),
                "passenger_name": passenger_name,
                "payment_status": r[9] or "Pending",
                "paid_at": r[10].isoformat() if r[10] else None,
                "payment_method": r[11] or None,
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
                # Always use date_str as the work day — the OneDrive folder is the
                # authoritative source for which day this receipt belongs to.
                # Do NOT override from the filename: screenshots are often taken
                # the morning after (e.g. Screenshot_20260525_... for May 24th receipts).
                capture_date = date_str

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
                    "  category: Select one from: 'Meal_Receipt', 'Fuel_Receipt', 'Maintenance', 'Charging_Session', 'ATM_Receipt', 'General_Expense'. IMPORTANT: Use 'Meal_Receipt' for any food or drink purchase — including convenience stores like Maverik, Circle K, 7-Eleven, Wawa, Love's, or Pilot when items are drinks/snacks/food. Use 'General_Expense' ONLY for non-food business supplies or misc charges that are not food, fuel, maintenance, charging, or ATM-related.\n"
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

                # Skip charging sessions — Tessie already tracks these in the
                # Charging Sessions panel. Importing them here creates duplicates.
                if category == "Charging_Session":
                    return None, f"SKIP: '{name}' — Charging_Session is tracked by Tessie, not expenses"
                
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

                # ── Date clamping: screenshots in this folder belong to this workday ──
                # If GPT extracted a date more than 1 day before the folder date, clamp
                # the DATE portion to date_str (preserve the extracted time).
                # Receipts often show a prior day's date when screenshotted the next morning.
                try:
                    folder_dt = _dt.datetime.strptime(date_str, "%Y-%m-%d")
                    day_diff = (folder_dt.date() - parsed_dt.date()).days
                    if day_diff >= 1:
                        log.info(f"DATE CLAMP: '{name}' GPT date {parsed_dt.date()} → {folder_dt.date()} (folder date, {day_diff}d gap)")
                        parsed_dt = parsed_dt.replace(
                            year=folder_dt.year,
                            month=folder_dt.month,
                            day=folder_dt.day
                        )
                except Exception as clamp_err:
                    log.warning(f"Date clamp failed for {name}: {clamp_err}")

                original_dt = parsed_dt
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
                    "original_date_time": original_dt,
                    "items": items
                }
                
                stored_dt_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
                clamp_note = f" [clamped from {dt_str}]" if stored_dt_str[:10] != dt_str[:10] else ""
                return entry, f"PARSED: '{name}' — {merchant} ${amount:.2f} ({category}) @ {stored_dt_str}{clamp_note}"
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
                            # If they originally had different extracted dates, they are genuinely different days (e.g. back-to-back shifts)
                            orig1 = exp.get("original_date_time")
                            orig2 = existing.get("original_date_time")
                            if orig1 and orig2 and orig1.date() != orig2.date():
                                is_dup = False
                            else:
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
        from services.artifact_registry import ArtifactRegistry
        vs = VectorStore()
        registry = ArtifactRegistry()
        
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
                onedrive_path = f"OneDrive://{explicit_path}/{exp['filename']}"
                derivation = (
                    f"Verified Expense Receipt: {exp['merchant']} on "
                    f"{exp['date_time'].strftime('%Y-%m-%d')} for ${exp['amount']:.2f}. "
                    f"Items: {', '.join(exp['items'])}. Category: {exp['category']}. "
                    f"Filename: {exp['filename']}"
                )

                guid = registry.register(
                    artifact_type='Receipt',
                    entity_id=exp_id,
                    entity_table='Rides.ManualExpenses',
                    source_path=onedrive_path,
                    content_hash=raw_hash,
                    ingestion_path='CloudWatcher',
                )

                vector_data = {
                    "vector_id":        f"VEC-EXP-{guid[:8]}",
                    "source_type":      "Artifact",
                    "timestamp_utc":    exp["date_time"],
                    "raw_text_hash":    raw_hash,
                    "source_pointer":   registry.pointer(guid),
                    "derivation_reason": derivation,
                    "artifact_guid":    guid,
                }

                v_success = vs.add_vector(vector_data)
                if v_success:
                    logs.append(f"VECTOR: Vectorized '{exp['filename']}' → artifact://{guid}")
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

    def sync_private_bookings_for_date(self, date_str: str, cursor, logs: list):
        """
        Pairs Private Website Bookings (INV- records) with Tessie drives on the same day.

        Bundle logic: If an INV- record is a Daily Bundle (pricing_type='bundle' or Fare >= 100),
        ALL Tessie drives tagged with that client's name on that day are linked to the single INV-
        record. Each drive gets the client tag (e.g. 'Jackie') and a 'bundle' flag in sidecar.

        Standard logic: 1-to-1 proximity match within 3 hours.
        """
        logs.append(f"PRIVATE-SYNC: Starting Private Booking sync for {date_str}")
        
        try:
            # Dynamically get the Mountain Time timezone offset for this target date (handles Daylight Savings)
            dt_sample = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=MDT)
            offset_hours = abs(int(dt_sample.utcoffset().total_seconds() / 3600))
            logs.append(f"PRIVATE-SYNC: Mountain Time offset for {date_str} is UTC-{offset_hours}")
            
            # 1. Fetch all private bookings for this day: INV- records (from invoicing system)
            #    and TRIP- records with TripType='Private' (from booking confirmation email screenshots)
            cursor.execute("""
                SELECT RideID, Timestamp_Start, Classification, Tessie_DriveID, Fare, Sidecar_Artifact_JSON, IsTest
                FROM Rides.Rides
                WHERE CAST(Timestamp_Start AS DATE) = ?
                  AND (RideID LIKE 'INV-%' OR (RideID LIKE 'TRIP-%' AND TripType = 'Private'))
                  AND DeletedAt IS NULL
            """, (date_str,))
            bookings = []
            for row in cursor.fetchall():
                sidecar = {}
                try:
                    sidecar = json.loads(str(row[5])) if row[5] else {}
                except:
                    pass
                # The booking sidecar records what was actually sold ('single' or
                # 'bundle'). Trust it when present — round trips routinely cost
                # $100+ now, so the fare heuristic is only a fallback for old
                # rows whose sidecar predates quoteType.
                quote_type = (sidecar.get("quoteType") or "").lower()
                if quote_type:
                    is_bundle = quote_type == "bundle"
                else:
                    is_bundle = (
                        sidecar.get("pricing_type") == "bundle"
                        or sidecar.get("customer_tier", "").lower() == "daily exclusivity bundle"
                        or float(row[4] or 0) >= 100.0
                    )
                bookings.append({
                    "RideID": row[0],
                    "Timestamp_Start": row[1],
                    "Classification": row[2],
                    "Tessie_DriveID": row[3],
                    "Fare": float(row[4] or 0),
                    "is_bundle": is_bundle,
                    "return_start": sidecar.get("returnStart"),
                    "IsTest": bool(row[6]) if row[6] is not None else False
                })

            if not bookings:
                logs.append(f"PRIVATE-SYNC: No private bookings found for {date_str}.")
                return

            logs.append(f"PRIVATE-SYNC: Found {len(bookings)} private booking(s) to process (INV- and TRIP-Private).")
            
            # 2. Fetch ALL Tessie drives on this day (unmatched and client-tagged)
            cursor.execute("""
                SELECT RideID, Timestamp_Start, Classification, Distance_mi, Duration_min,
                       Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi, Pickup_Location, Dropoff_Location, TripType,
                       Sidecar_Artifact_JSON
                FROM Rides.Rides
                WHERE RideID LIKE 'TESSIE-%'
                  AND CAST(Timestamp_Start AS DATE) = ?
            """, (date_str,))
            
            all_tessie_drives = []
            for row in cursor.fetchall():
                all_tessie_drives.append({
                    "RideID": row[0],
                    "Timestamp_Start": row[1],
                    "Classification": row[2] or "Untagged",
                    "Distance_mi": row[3],
                    "Duration_min": row[4],
                    "Start_SOC": row[5],
                    "End_SOC": row[6],
                    "Energy_Used_kWh": row[7],
                    "Efficiency_Wh_mi": row[8],
                    "Pickup_Location": row[9],
                    "Dropoff_Location": row[10],
                    "TripType": row[11],
                    "Sidecar_Artifact_JSON": row[12]
                })
                
            if not all_tessie_drives:
                logs.append(f"PRIVATE-SYNC: No TESSIE drives found on {date_str}.")
                return

            # Pool of drives still available for 1:1 matching
            unmatched_drives = list(all_tessie_drives)
                
            # 3. Process each booking
            for booking in bookings:
                if booking.get("IsTest"):
                    logs.append(f"PRIVATE-SYNC: Skipping test booking {booking['RideID']}")
                    continue
                b_id = booking["RideID"]
                b_dt = booking["Timestamp_Start"]
                is_bundle = booking["is_bundle"]

                # Determine the client name from the booking classification or RideID
                b_class = (booking["Classification"] or "").lower()
                b_id_lower = b_id.lower()
                
                # Normalize jacquelyn -> jackie
                search_str = f"{b_id_lower} {b_class}"
                if "jacquelyn" in search_str:
                    search_str += " jackie"
                
                client_name = None
                try:
                    known_clients = self.db.get_known_client_names()
                except Exception:
                    known_clients = ["jackie", "esmeralda", "daniel", "ryan", "lauren", "terrance", "lorynne", "nancy", "adrienne", "david", "emerson"]
                for client in known_clients:
                    if client in search_str:
                        client_name = client.capitalize()
                        break

                if client_name:
                    if client_name.lower() in ["jackie", "jacquelyn", "jacquelyn heslep"]:
                        tessie_class = "Jacquelyn Heslep"
                    elif client_name.lower() in ["david", "david berezov"]:
                        tessie_class = "David Berezov"
                    else:
                        tessie_class = client_name
                else:
                    tessie_class = "Private_Trip"

                if is_bundle and client_name:
                    # ── BUNDLE: Link ALL drives tagged with this client's name to the INV- record ──
                    # These drives already have the client tag from the Tessie app (e.g. 'Jackie').
                    client_drives = [
                        d for d in all_tessie_drives
                        if client_name.lower() in (d["Classification"] or "").lower()
                    ]

                    if not client_drives:
                        # Fallback: proximity match the first drive if no client-tagged drives found
                        logs.append(f"PRIVATE-SYNC-BUNDLE: No drives tagged '{client_name}' found for bundle {b_id} — falling back to proximity match")
                        is_bundle = False  # drop through to standard match below
                    else:
                        logs.append(f"PRIVATE-SYNC-BUNDLE: Bundle booking {b_id} (${booking['Fare']:.2f}) covering {len(client_drives)} '{client_name}' drives")

                        # Link ALL client drives to this INV- record
                        first_drive = min(client_drives, key=lambda d: d["Timestamp_Start"])
                        last_drive = max(client_drives, key=lambda d: d["Timestamp_Start"])

                        # Update the INV- booking with aggregate telemetry (first pickup → last dropoff)
                        total_dist = sum(float(d["Distance_mi"] or 0) for d in client_drives)
                        total_dur = sum(float(d["Duration_min"] or 0) for d in client_drives)
                        cursor.execute("""
                            UPDATE Rides.Rides
                            SET Tessie_DriveID = ?,
                                Distance_mi = ?,
                                Duration_min = ?,
                                Start_SOC = ?,
                                End_SOC = ?,
                                Pickup_Location = COALESCE(Pickup_Location, ?),
                                Dropoff_Location = COALESCE(Dropoff_Location, ?),
                                LastUpdated = GETUTCDATE()
                            WHERE RideID = ?
                        """, (
                            first_drive["RideID"],
                            total_dist,
                            total_dur,
                            first_drive["Start_SOC"],
                            last_drive["End_SOC"],
                            first_drive["Pickup_Location"],
                            last_drive["Dropoff_Location"],
                            b_id
                        ))

                        # Tag every client drive: client name + bundle flag
                        for drive in client_drives:
                            tessie_id = drive["RideID"]
                            cursor.execute("""
                                UPDATE Rides.Rides
                                SET TripType = 'Private',
                                    Classification = ?,
                                    LastUpdated = GETUTCDATE()
                                WHERE RideID = ?
                            """, (tessie_class, tessie_id))
                            logs.append(f"PRIVATE-SYNC-BUNDLE-TAG: {tessie_id} → {tessie_class} (bundle)")
                            # Remove from unmatched pool so standard matching skips it
                            if drive in unmatched_drives:
                                unmatched_drives.remove(drive)
                        continue  # move to next booking

                if not is_bundle:
                    # ── STANDARD 1:1 PROXIMITY MATCH ──
                    best_drive = None
                    best_diff_seconds = 999999
                    
                    def get_tag(drive) -> str:
                        try:
                            sc_str = drive.get("Sidecar_Artifact_JSON")
                            if sc_str:
                                sc = json.loads(sc_str)
                                if "Sidecar_Artifact_JSON" in sc:
                                    nested = json.loads(sc["Sidecar_Artifact_JSON"])
                                    return (nested.get("tag") or "").lower()
                                return (sc.get("tag") or "").lower()
                        except:
                            pass
                        return ""

                    # 1. Try to find drives that explicitly match the client name first (and are not pickup legs)
                    client_drives = []
                    if client_name:
                        client_drives = [
                            d for d in unmatched_drives
                            if (
                                client_name.lower() in (d["Classification"] or "").lower()
                                or client_name.lower() in get_tag(d)
                            )
                            and not any(w in (d["Classification"] or "").lower() or w in get_tag(d) for w in ["pickup", "en route", "charging", "charge"])
                            and not (float(d.get("Distance_mi") or 0) < 1.0 and booking.get("Fare", 0) > 0)
                        ]
                        
                    if client_drives:
                        logs.append(f"PRIVATE-SYNC: Found {len(client_drives)} client-tagged candidate(s) for client '{client_name}'")
                        for drive in client_drives:
                            t_dt = drive["Timestamp_Start"]
                            # Require date alignment (local MT date must match)
                            if t_dt.date() != b_dt.date():
                                continue
                            diff = abs((b_dt - t_dt).total_seconds())
                            if diff < best_diff_seconds:
                                best_diff_seconds = diff
                                best_drive = drive
                    else:
                        # 2. Fall back to normal proximity matching, but skip pickup legs, charging, and short staging runs (< 1.0 mi)
                        for drive in unmatched_drives:
                            drive_class = (drive.get("Classification") or "").lower()
                            drive_tag = get_tag(drive)
                            drive_dist = float(drive.get("Distance_mi") or 0)
                            if "pickup" in drive_class or "pickup" in drive_tag or "en route" in drive_class or "en route" in drive_tag or "charging" in drive_class or "charging" in drive_tag or "charge" in drive_class or "charge" in drive_tag or (drive_dist < 1.0 and booking.get("Fare", 0) > 0):
                                continue
                            t_dt = drive["Timestamp_Start"]
                            # Require date alignment (local MT date must match)
                            if t_dt.date() != b_dt.date():
                                continue
                            diff = abs((b_dt - t_dt).total_seconds())
                            if diff < best_diff_seconds:
                                best_diff_seconds = diff
                                best_drive = drive
                            
                    # Proximity tolerance: 3 hours
                    if best_drive and best_diff_seconds <= 10800:
                        tessie_id = best_drive["RideID"]
                        logs.append(f"PRIVATE-SYNC-MATCH: Booking {b_id} matched to Tessie drive {tessie_id} (diff: {best_diff_seconds/60:.1f}m)")
                        
                        # Update booking record with Tessie drive ID and telemetry
                        cursor.execute("""
                            UPDATE Rides.Rides
                            SET Tessie_DriveID = ?,
                                Distance_mi = ?,
                                Duration_min = ?,
                                Start_SOC = ?,
                                End_SOC = ?,
                                Energy_Used_kWh = ?,
                                Efficiency_Wh_mi = ?,
                                Pickup_Location = COALESCE(Pickup_Location, ?),
                                Dropoff_Location = COALESCE(Dropoff_Location, ?),
                                LastUpdated = GETUTCDATE()
                            WHERE RideID = ?
                        """, (
                            tessie_id,
                            best_drive["Distance_mi"],
                            best_drive["Duration_min"],
                            best_drive["Start_SOC"],
                            best_drive["End_SOC"],
                            best_drive["Energy_Used_kWh"],
                            best_drive["Efficiency_Wh_mi"],
                            best_drive["Pickup_Location"],
                            best_drive["Dropoff_Location"],
                            b_id
                        ))
                        
                        # Update the Tessie drive classification
                        cursor.execute("""
                            UPDATE Rides.Rides
                            SET TripType = 'Private',
                                Classification = ?,
                                LastUpdated = GETUTCDATE()
                            WHERE RideID = ?
                        """, (tessie_class, tessie_id))
                        logs.append(f"PRIVATE-SYNC-UPDATE: {tessie_id} → TripType=Private, Classification={tessie_class}")
                        
                        # Auto-tag the preceding pickup drive
                        try:
                            cursor.execute("""
                                SELECT TOP 1 RideID 
                                FROM Rides.Rides 
                                WHERE Timestamp_Start < ? 
                                  AND Timestamp_Start > DATEADD(minute, -60, ?)
                                  AND (Classification IS NULL OR Classification = 'Untagged' OR Classification = 'Uber_Pickup')
                                ORDER BY Timestamp_Start DESC
                            """, (best_drive['Timestamp_Start'], best_drive['Timestamp_Start']))
                            pickup_row = cursor.fetchone()
                            if pickup_row:
                                pickup_id = pickup_row[0]
                                cursor.execute("""
                                    UPDATE Rides.Rides 
                                    SET TripType = 'Private',
                                        Classification = 'Private_Pickup',
                                        LastUpdated = GETUTCDATE() 
                                    WHERE RideID = ?
                                """, (pickup_id,))
                                logs.append(f"PRIVATE-SYNC-AUTO-TAG: {pickup_id} labeled as Private_Pickup")
                        except Exception as pickup_err:
                            logs.append(f"PRIVATE-SYNC-WARN: Failed to auto-tag pickup: {pickup_err}")
                            
                        # Remove matched drive from pool
                        unmatched_drives.remove(best_drive)

                        # ── Scheduled-return round trip: tag the return-leg drive too ──
                        # The booking sidecar carries returnStart (UTC ISO); without
                        # this, the return drive stays untagged on the dashboard.
                        return_start = booking.get("return_start")
                        if return_start:
                            try:
                                ret_utc = datetime.datetime.fromisoformat(str(return_start).replace("Z", "+00:00"))
                                ret_local = ret_utc.replace(tzinfo=None) - datetime.timedelta(hours=offset_hours)
                                ret_drive = None
                                ret_diff = 999999
                                for drive in unmatched_drives:
                                    diff = abs((ret_local - drive["Timestamp_Start"]).total_seconds())
                                    if diff < ret_diff:
                                        ret_diff = diff
                                        ret_drive = drive
                                if ret_drive and ret_diff <= 10800:
                                    cursor.execute("""
                                        UPDATE Rides.Rides
                                        SET TripType = 'Private',
                                            Classification = ?,
                                            LastUpdated = GETUTCDATE()
                                        WHERE RideID = ?
                                    """, (tessie_class, ret_drive["RideID"]))
                                    logs.append(f"PRIVATE-SYNC-RETURN: Booking {b_id} return leg matched to {ret_drive['RideID']} (diff: {ret_diff/60:.1f}m)")
                                    unmatched_drives.remove(ret_drive)
                                else:
                                    logs.append(f"PRIVATE-SYNC-RETURN: No drive matched the return leg of {b_id} (best diff: {ret_diff/60:.1f}m)")
                            except Exception as ret_err:
                                logs.append(f"PRIVATE-SYNC-WARN: Return-leg match failed for {b_id}: {ret_err}")
                    else:
                        logs.append(f"PRIVATE-SYNC-NOMATCH: Booking {b_id} could not be matched (best diff: {best_diff_seconds/60:.1f}m)")
        except Exception as e:
            logs.append(f"PRIVATE-SYNC-ERROR: Failed to run private booking sync: {e}")

