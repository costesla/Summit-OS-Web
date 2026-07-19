"""
services/flight.py
------------------
Hybrid flight-status resolver for the public /flights page (via the
/api/flight-status route in api/bookings.py).

Merges two sources so the page works whether or not the flight is airborne:
  - FlightAware AeroAPI (services/flightaware.py): airline, schedule, live
    status text, and delay — available even before takeoff.
  - Flightradar24 (services/flightradar24.py): live position (lat/lon,
    altitude, speed, heading) — only while the aircraft is airborne.

Replaces the retired AviationStack integration. Each source degrades
gracefully: if one is unconfigured or misses, the other still answers.
Arrival times are rendered in Mountain Time (the pickup timezone).
"""

import logging
import datetime
from typing import Optional

from services.datetime_utils import get_timezone
from services.flightaware import FlightAwareClient
from services.flightradar24 import Flightradar24Client


def _mt(iso, tz) -> Optional[str]:
    """ISO-UTC timestamp -> readable Mountain-Time clock string (e.g. '7:11 PM')."""
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.astimezone(tz).strftime("%I:%M %p").lstrip("0")


def _airport(obj) -> dict:
    o = obj or {}
    return {
        "code": o.get("code_iata") or o.get("code_icao") or o.get("code"),
        "city": o.get("city"),
    }


class FlightStatusService:
    """Resolve a flight number to a merged FlightAware + FR24 status object."""

    def get_flight_status(self, flight_number: str) -> Optional[dict]:
        flight_number = (str(flight_number or "")).strip().upper()
        if not flight_number:
            return None

        tz = get_timezone()
        fr = Flightradar24Client()

        # ── FlightAware: schedule / status / delay (works before takeoff) ────
        info = FlightAwareClient().flight_info(flight_number)

        # ── FR24: live position (only while airborne) ────────────────────────
        pos = None
        try:
            positions = fr.live_flight_positions(flights=flight_number, cache_ttl=0)
            pos = positions[0] if positions else None
        except Exception as e:
            logging.warning(f"FR24 live position error for {flight_number}: {e}")

        if not info and not pos:
            return None

        live = None
        if pos:
            live = {
                "latitude": pos.get("lat"),
                "longitude": pos.get("lon"),
                "altitude_ft": pos.get("alt"),
                "ground_speed_kts": pos.get("gspeed"),
                "heading_deg": pos.get("track"),
            }

        result = {
            "flight_number": flight_number,
            "live": live,
            "sources": {
                "schedule": "FlightAware" if info else None,
                "live": "FlightRadar24" if live else None,
            },
        }

        if info:
            arr_delay = info.get("arrival_delay")
            delay_min = int(arr_delay / 60) if isinstance(arr_delay, (int, float)) else None
            op = info.get("operator")
            airline = op
            if op:
                try:
                    a = fr.airline_light(op)
                    airline = (a or {}).get("name") or op
                except Exception:
                    pass
            result.update({
                "airline": airline,
                "airline_code": op,
                "status": info.get("status"),
                "origin": _airport(info.get("origin")),
                "destination": _airport(info.get("destination")),
                "scheduled_arrival_mt": _mt(info.get("scheduled_in") or info.get("scheduled_on"), tz),
                "estimated_arrival_mt": _mt(
                    info.get("estimated_in") or info.get("estimated_on")
                    or info.get("actual_in") or info.get("actual_on"), tz),
                "delay_minutes": delay_min,
                "aircraft_type": info.get("aircraft_type"),
                "progress_percent": info.get("progress_percent"),
                "cancelled": bool(info.get("cancelled")),
            })
        else:
            # Airborne but FlightAware had nothing — fall back to live-only.
            result.update({
                "airline": None,
                "airline_code": pos.get("operating_as") or pos.get("painted_as"),
                "status": "En route (live)",
                "origin": {"code": pos.get("orig_iata") or pos.get("orig_icao"), "city": None},
                "destination": {"code": pos.get("dest_iata") or pos.get("dest_icao"), "city": None},
                "scheduled_arrival_mt": None,
                "estimated_arrival_mt": _mt(pos.get("eta"), tz),
                "delay_minutes": None,
                "aircraft_type": pos.get("type"),
                "progress_percent": None,
                "cancelled": False,
            })

        return result
