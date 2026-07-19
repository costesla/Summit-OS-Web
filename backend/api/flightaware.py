"""
FlightAware MCP tools blueprint — real SCHEDULED arrivals for the SummitOS
MCP server via the Azure Functions MCP extension.

Lands on the same /runtime/webhooks/mcp endpoint as the other blueprints (the
MCP extension aggregates every @bp.mcp_tool_trigger). Registered in
function_app.py as "api.flightaware".

Division of labour: api/flightradar24.py serves LIVE airborne traffic; this
serves the scheduled timetable (airline, gate times, delays) from FlightAware
AeroAPI — including flights still on the ground. Cargo carriers are dropped by
operator ICAO because AeroAPI has no passenger-vs-cargo flag.

Tool descriptions here drive Copilot Studio routing and cannot be edited there
later — write them the way questions get asked.
"""

import re
import json
import logging
import datetime

import azure.functions as func

from services.datetime_utils import get_timezone
from services.flightaware import (
    FlightAwareClient,
    FlightAwareApiError,
    COS_ICAO,
    CARGO_OPERATORS_ICAO,
)

bp = func.Blueprint()

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ── shared helpers ───────────────────────────────────────────────────────────
def _parse_args(context) -> dict:
    """Robustly extract the arguments dict from an MCP tool context."""
    raw = context
    if hasattr(raw, "get_body"):
        try:
            raw = raw.get_body()
        except Exception:
            raw = None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return {}
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    if isinstance(raw, dict):
        args = raw.get("arguments")
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return raw
    return {}


def _as_bool(v, default=False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _iso_utc(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _to_mt(s, tz):
    dt = _parse_iso(s)
    if not dt:
        return None
    return dt.astimezone(tz).strftime("%I:%M %p").lstrip("0")


def _origin(f: dict):
    o = f.get("origin") or {}
    code = o.get("code_iata") or o.get("code_icao") or o.get("code")
    city = o.get("city")
    if city and code:
        return f"{city} ({code})"
    return city or code


_SCHEDULED_PROPERTIES = json.dumps([
    {
        "propertyName": "airport_code",
        "propertyType": "string",
        "description": "Airport ICAO code, e.g. 'KCOS' or 'KDEN'. Defaults to KCOS (Colorado Springs).",
        "isRequired": False,
    },
    {
        "propertyName": "start_time",
        "propertyType": "string",
        "description": "Start of the arrival window today, HH:MM 24-hour Mountain Time (e.g. '12:00'). Provide together with end_time. Omit both for the next 12 hours.",
        "isRequired": False,
    },
    {
        "propertyName": "end_time",
        "propertyType": "string",
        "description": "End of the arrival window today, HH:MM 24-hour Mountain Time (e.g. '14:00'). Provide together with start_time.",
        "isRequired": False,
    },
    {
        "propertyName": "include_cargo",
        "propertyType": "boolean",
        "description": "Set true to include cargo airlines (FedEx, UPS, etc.). Defaults to false — commercial passenger airlines only.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_scheduled_arrivals",
    description=(
        "Returns the real SCHEDULED commercial-airline arrivals board for an "
        "airport (default Colorado Springs, COS): airline, flight number, "
        "origin, scheduled and estimated arrival times in Mountain Time, delay "
        "in minutes, and aircraft type — including flights not yet in the air. "
        "This is a true timetable with delays (from FlightAware), unlike the "
        "live-airborne get_cos_arrivals tool. Use for questions like 'what "
        "flights are scheduled to land at COS between noon and 2 PM', 'is the "
        "United flight delayed', 'what's arriving this afternoon'. Passenger "
        "airlines only by default (cargo like FedEx/UPS excluded); set "
        "include_cargo true to include them. Optionally restrict to a "
        "start_time/end_time window (Mountain Time)."
    ),
    tool_properties=_SCHEDULED_PROPERTIES,
)
def get_scheduled_arrivals(context) -> str:
    args = _parse_args(context)
    airport = (str(args.get("airport_code") or "")).strip().upper() or COS_ICAO
    start_time = (str(args.get("start_time") or "")).strip()
    end_time = (str(args.get("end_time") or "")).strip()
    include_cargo = _as_bool(args.get("include_cargo"), default=False)

    if bool(start_time) != bool(end_time):
        return _dump({"error": "Provide start_time and end_time together (HH:MM, 24-hour Mountain Time), or omit both."})

    tz = get_timezone()
    now_local = datetime.datetime.now(tz)

    try:
        if start_time:
            for t in (start_time, end_time):
                if not _HHMM.match(t):
                    return _dump({"error": f"Invalid time '{t}' — use HH:MM, 24-hour Mountain Time (e.g. '12:00')."})
            today = now_local.date()
            sh, sm = map(int, start_time.split(":"))
            eh, em = map(int, end_time.split(":"))
            start_dt = datetime.datetime(today.year, today.month, today.day, sh, sm, tzinfo=tz)
            end_dt = datetime.datetime(today.year, today.month, today.day, eh, em, tzinfo=tz)
            if end_dt <= start_dt:  # window wraps past midnight
                end_dt += datetime.timedelta(days=1)
            window_label = f"{start_time}–{end_time} Mountain Time"
        else:
            start_dt = now_local
            end_dt = now_local + datetime.timedelta(hours=12)
            window_label = "next 12 hours"

        client = FlightAwareClient()
        flights = client.scheduled_arrivals(
            airport, start=_iso_utc(start_dt), end=_iso_utc(end_dt), flight_type="Airline",
        )

        arrivals = []
        for f in flights:
            op = (f.get("operator_icao") or f.get("operator") or "").upper()
            if not include_cargo and op in CARGO_OPERATORS_ICAO:
                continue
            sched = _parse_iso(f.get("scheduled_in") or f.get("scheduled_on"))
            est = _parse_iso(f.get("estimated_in") or f.get("estimated_on")
                             or f.get("actual_in") or f.get("actual_on"))
            delay_min = int((est - sched).total_seconds() // 60) if sched and est else None
            if delay_min is None:
                status = "scheduled"
            elif delay_min >= 15:
                status = f"delayed {delay_min} min"
            elif delay_min <= -15:
                status = f"early {abs(delay_min)} min"
            else:
                status = "on time"
            arrivals.append({
                "airline": f.get("operator") or op or None,
                "flight_number": f.get("ident_iata") or f.get("ident"),
                "origin": _origin(f),
                "scheduled_arrival_mt": _to_mt(f.get("scheduled_in") or f.get("scheduled_on"), tz),
                "estimated_arrival_mt": _to_mt(f.get("estimated_in") or f.get("estimated_on")
                                               or f.get("actual_in") or f.get("actual_on"), tz),
                "delay_minutes": delay_min,
                "aircraft_type": f.get("aircraft_type"),
                "status": status,
            })

        return _dump({
            "airport": airport,
            "board_type": "SCHEDULED commercial-airline arrivals",
            "scheduled_board": True,
            "window": window_label,
            "timezone": "Mountain Time (America/Denver)",
            "commercial_passenger_only": not include_cargo,
            "count": len(arrivals),
            "arrivals": arrivals,
        })
    except FlightAwareApiError as e:
        return _dump({"error": e.message})
    except Exception as e:
        logging.error(f"MCP get_scheduled_arrivals unexpected failure: {type(e).__name__}: {e}")
        return _dump({"error": "get_scheduled_arrivals failed unexpectedly. Please try again."})
