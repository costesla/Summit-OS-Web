"""
Flightradar24 MCP tools blueprint — live flight intelligence for the SummitOS
MCP server via the Azure Functions MCP extension.

These tools land on the SAME streamable-HTTP endpoint as api/mcp_tools.py
(/runtime/webhooks/mcp): the MCP extension aggregates every
@bp.mcp_tool_trigger across all registered blueprints. So Summit Intelligence
2.0 discovers them automatically once "api.flightradar24" is registered in
function_app.py — no new connector, no new endpoint.

Data reality (see services/flightradar24.py): the FR24 v1 API is built on LIVE
flight-positions, not a scheduled arrivals/departures board. "Arrivals" and
"departures" here are live *airborne* traffic inbound/outbound to an airport.
For a true SCHEDULED board with delays, use get_scheduled_arrivals
(FlightAware-backed, api/flightaware.py). The FR24 API has no delay data and no
static aircraft-registration database, so those fields are reported as
unavailable rather than guessed.

Tool descriptions here are what the Copilot orchestrator uses to route and
CANNOT be edited later in Copilot Studio — write them the way questions get
asked.
"""

import json
import logging
import datetime

import azure.functions as func

from services.datetime_utils import get_timezone
from services.flightradar24 import (
    Flightradar24Client,
    FR24ApiError,
    COS_ICAO,
    COS_IATA,
    CATEGORY_BUSINESS_JETS,
)

bp = func.Blueprint()

# FR24 passenger-airline category (excludes cargo like FedEx, GA, private).
CATEGORY_PASSENGER = "P"


# ── shared helpers ───────────────────────────────────────────────────────────
def _parse_args(context) -> dict:
    """Robustly extract the arguments dict from an MCP tool context.

    MCP inputs may arrive as: a dict, a JSON string, JSON bytes, an object
    exposing get_body(), or any of those wrapping a nested "arguments" field
    (which itself may be a dict or a JSON string).
    """
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


def _limit(args: dict, default: int = 30, maximum: int = 100) -> int:
    v = args.get("limit")
    if v is None or str(v).strip() == "":
        return default
    try:
        return max(1, min(int(float(v)), maximum))
    except (TypeError, ValueError):
        return default


def _as_bool(v, default=False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _origin(f: dict):
    return f.get("orig_iata") or f.get("orig_icao")


def _dest(f: dict):
    return f.get("dest_iata") or f.get("dest_icao")


def _operator(f: dict):
    return f.get("operating_as") or f.get("painted_as")


def _eta_mt(eta):
    """Convert an FR24 ISO-UTC ETA to a readable Mountain-Time clock string."""
    if not eta:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(eta).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.astimezone(get_timezone()).strftime("%I:%M %p").lstrip("0")


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _error(e: Exception, tool: str) -> str:
    if isinstance(e, FR24ApiError):
        return _dump({"error": e.message})
    logging.error(f"MCP {tool} unexpected failure: {type(e).__name__}: {e}")
    return _dump({"error": f"{tool} failed unexpectedly. Please try again."})


# ═════════════════════════════════════════════════════════════════════════════
# 1. get_cos_arrivals
# ═════════════════════════════════════════════════════════════════════════════
_ARRIVALS_PROPERTIES = json.dumps([
    {
        "propertyName": "limit",
        "propertyType": "number",
        "description": "Maximum flights to return (1-100). Defaults to 30.",
        "isRequired": False,
    },
    {
        "propertyName": "commercial_only",
        "propertyType": "boolean",
        "description": "Passenger airlines only (excludes cargo like FedEx/UPS, private jets, and general aviation). Defaults to true. Set false to include all inbound traffic.",
        "isRequired": False,
    },
])

_LIMIT_PROPERTY = json.dumps([
    {
        "propertyName": "limit",
        "propertyType": "number",
        "description": "Maximum flights to return (1-100). Defaults to 30.",
        "isRequired": False,
    }
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_cos_arrivals",
    description=(
        "Returns commercial passenger flights currently airborne and inbound "
        "to Colorado Springs Airport (COS): flight number, callsign, origin "
        "airport, ETA (Mountain Time), aircraft type, registration, operator, "
        "and status. Use for questions like 'what flights are arriving at COS', "
        "'who's flying into Colorado Springs right now', 'any inbound flights'. "
        "Passenger airlines only by default (cargo like FedEx, private jets, "
        "and general aviation are excluded); set commercial_only false to "
        "include all inbound traffic. This is LIVE airborne traffic, not a "
        "scheduled board and with no delay data — for the scheduled timetable "
        "with delays use get_scheduled_arrivals instead."
    ),
    tool_properties=_ARRIVALS_PROPERTIES,
)
def get_cos_arrivals(context) -> str:
    args = _parse_args(context)
    limit = _limit(args)
    commercial_only = _as_bool(args.get("commercial_only"), default=True)
    try:
        flights = Flightradar24Client().live_flight_positions(
            airports=f"inbound:{COS_ICAO}",
            categories=CATEGORY_PASSENGER if commercial_only else None,
            limit=limit,
        )
        return _dump({
            "airport": COS_ICAO,
            "airport_iata": COS_IATA,
            "label": "LIVE INBOUND AIRBORNE TRAFFIC",
            "scheduled_board": False,
            "delay_data_available": False,
            "commercial_passenger_only": commercial_only,
            "count": len(flights),
            "flights": [
                {
                    "flight_number": f.get("flight"),
                    "callsign": f.get("callsign"),
                    "origin": _origin(f),
                    "destination": _dest(f),
                    "eta": f.get("eta"),
                    "eta_mountain": _eta_mt(f.get("eta")),
                    "aircraft_type": f.get("type"),
                    "registration": f.get("reg"),
                    "operator": _operator(f),
                    "status": "LIVE INBOUND (airborne)",
                }
                for f in flights
            ],
        })
    except Exception as e:
        return _error(e, "get_cos_arrivals")


# ═════════════════════════════════════════════════════════════════════════════
# 2. get_cos_departures
# ═════════════════════════════════════════════════════════════════════════════
@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_cos_departures",
    description=(
        "Returns flights currently airborne and outbound from Colorado Springs "
        "Airport (COS): flight number, callsign, destination airport, aircraft "
        "type, registration, operator, and status. Use for questions like "
        "'what flights are departing COS', 'who just left Colorado Springs', "
        "'any outbound flights right now'. This is LIVE airborne traffic, not "
        "a scheduled airline departures board, and it does not include delay "
        "data."
    ),
    tool_properties=_LIMIT_PROPERTY,
)
def get_cos_departures(context) -> str:
    args = _parse_args(context)
    limit = _limit(args)
    try:
        flights = Flightradar24Client().live_flight_positions(
            airports=f"outbound:{COS_ICAO}", limit=limit,
        )
        return _dump({
            "airport": COS_ICAO,
            "airport_iata": COS_IATA,
            "label": "LIVE OUTBOUND AIRBORNE TRAFFIC",
            "scheduled_board": False,
            "delay_data_available": False,
            "count": len(flights),
            "flights": [
                {
                    "flight_number": f.get("flight"),
                    "callsign": f.get("callsign"),
                    "origin": _origin(f),
                    "destination": _dest(f),
                    "eta": f.get("eta"),
                    "aircraft_type": f.get("type"),
                    "registration": f.get("reg"),
                    "operator": _operator(f),
                    "status": "LIVE OUTBOUND (airborne)",
                }
                for f in flights
            ],
        })
    except Exception as e:
        return _error(e, "get_cos_departures")


# ═════════════════════════════════════════════════════════════════════════════
# 3. track_flight
# ═════════════════════════════════════════════════════════════════════════════
_TRACK_PROPERTIES = json.dumps([
    {
        "propertyName": "flight_number",
        "propertyType": "string",
        "description": "Flight number to track, e.g. 'UA1234'. Provide this OR callsign.",
        "isRequired": False,
    },
    {
        "propertyName": "callsign",
        "propertyType": "string",
        "description": "ATC callsign to track, e.g. 'UAL1234'. Provide this OR flight_number.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="track_flight",
    description=(
        "Tracks a single flight in real time by flight number or callsign and "
        "returns its current live position (latitude/longitude), altitude in "
        "feet, ground speed in knots, heading, vertical speed, origin, "
        "destination, ETA, and operator. Use for 'where is flight UA1234 right "
        "now', 'track callsign UAL55', 'how high is that flight'. Provide "
        "either flight_number or callsign. Returns only live airborne "
        "positions."
    ),
    tool_properties=_TRACK_PROPERTIES,
)
def track_flight(context) -> str:
    args = _parse_args(context)
    flight_number = (str(args.get("flight_number") or "")).strip()
    callsign = (str(args.get("callsign") or "")).strip()
    if not flight_number and not callsign:
        return _dump({"error": "Provide either flight_number or callsign to track."})
    try:
        results = Flightradar24Client().live_flight_positions(
            flights=flight_number or None,
            callsigns=callsign or None,
            limit=10,
            cache_ttl=0,
        )
        if not results:
            return _dump({
                "found": False,
                "message": "No live airborne position was found. The flight may be on the ground, not departed, already landed, or outside available live coverage.",
                "flight_number": flight_number or None,
                "callsign": callsign or None,
            })
        return _dump({
            "query": {
                "flight_number": flight_number or None,
                "callsign": callsign or None,
            },
            "count": len(results),
            "results": [
                {
                    "found": True,
                    "flight_number": f.get("flight"),
                    "callsign": f.get("callsign"),
                    "fr24_id": f.get("fr24_id"),
                    "latitude": f.get("lat"),
                    "longitude": f.get("lon"),
                    "altitude_ft": f.get("alt"),
                    "ground_speed_kts": f.get("gspeed"),
                    "heading_deg": f.get("track"),
                    "vertical_speed_fpm": f.get("vspeed"),
                    "aircraft_type": f.get("type"),
                    "registration": f.get("reg"),
                    "origin": _origin(f),
                    "destination": _dest(f),
                    "eta": f.get("eta"),
                    "operator": _operator(f),
                    "status": "LIVE AIRBORNE POSITION",
                }
                for f in results
            ],
        })
    except Exception as e:
        return _error(e, "track_flight")


# ═════════════════════════════════════════════════════════════════════════════
# 4. get_aircraft_details
# ═════════════════════════════════════════════════════════════════════════════
_AIRCRAFT_PROPERTIES = json.dumps([
    {
        "propertyName": "registration",
        "propertyType": "string",
        "description": "Aircraft tail/registration number, e.g. 'N123AB'.",
        "isRequired": True,
    }
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_aircraft_details",
    description=(
        "Looks up an aircraft by its registration (tail number) and returns "
        "registration, aircraft type, and operator, plus its current live "
        "position if airborne. Use for 'what kind of aircraft is N123AB', 'who "
        "operates tail number N628TS'. Note: this reads live flight data, so "
        "details are only available while the aircraft is airborne, and "
        "aircraft age is not available from Flightradar24."
    ),
    tool_properties=_AIRCRAFT_PROPERTIES,
)
def get_aircraft_details(context) -> str:
    args = _parse_args(context)
    registration = (str(args.get("registration") or "")).strip().upper()
    if not registration:
        return _dump({"error": "registration is required (e.g. 'N123AB')."})
    try:
        client = Flightradar24Client()
        results = client.live_flight_positions(
            registrations=registration, limit=10, cache_ttl=0,
        )
        if not results:
            return _dump({
                "found": False,
                "registration": registration,
                "message": "No live airborne aircraft was found for this registration. Flightradar24 live positions does not provide a static registration database, so the aircraft may be on the ground, not departed, already landed, or outside live coverage.",
                "age": None,
                "age_note": "not available from FR24",
            })
        f = results[0]
        operator_code = _operator(f)
        operator_name = None
        if operator_code:
            airline = client.airline_light(operator_code)
            operator_name = (airline or {}).get("name")
        return _dump({
            "found": True,
            "registration": f.get("reg") or registration,
            "aircraft_type": f.get("type"),
            "operator": operator_name or operator_code,
            "operator_code": operator_code,
            "age": None,
            "age_note": "not available from FR24",
            "live_position": {
                "latitude": f.get("lat"),
                "longitude": f.get("lon"),
                "altitude_ft": f.get("alt"),
                "ground_speed_kts": f.get("gspeed"),
                "heading_deg": f.get("track"),
                "origin": _origin(f),
                "destination": _dest(f),
                "eta": f.get("eta"),
                "flight_number": f.get("flight"),
                "callsign": f.get("callsign"),
            },
        })
    except Exception as e:
        return _error(e, "get_aircraft_details")


# ═════════════════════════════════════════════════════════════════════════════
# 5. search_private_arrivals  (lead generation)
# ═════════════════════════════════════════════════════════════════════════════
@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="search_private_arrivals",
    description=(
        "Returns business jets and private/charter aircraft currently airborne "
        "and inbound to Colorado Springs Airport (COS): registration, "
        "operator, origin, destination, ETA, and aircraft type. This is a "
        "transportation lead-generation tool for private aviation / black-car "
        "opportunities — use it for 'any private jets flying into COS', 'who's "
        "landing a business jet in Colorado Springs', 'find charter arrivals'. "
        "Filtered to the business-jet category, so scheduled airline traffic "
        "is excluded. Live airborne traffic only; no delay data."
    ),
    tool_properties=_LIMIT_PROPERTY,
)
def search_private_arrivals(context) -> str:
    args = _parse_args(context)
    limit = _limit(args)
    try:
        flights = Flightradar24Client().live_flight_positions(
            airports=f"inbound:{COS_ICAO}",
            categories=CATEGORY_BUSINESS_JETS,
            limit=limit,
        )
        return _dump({
            "airport": COS_ICAO,
            "airport_iata": COS_IATA,
            "label": "LIVE INBOUND BUSINESS JET TRAFFIC",
            "scheduled_board": False,
            "category_filter": CATEGORY_BUSINESS_JETS,
            "category_note": "J == Business jets",
            "delay_data_available": False,
            "count": len(flights),
            "aircraft": [
                {
                    "registration": f.get("reg"),
                    "operator": _operator(f),
                    "origin": _origin(f),
                    "destination": _dest(f),
                    "eta": f.get("eta"),
                    "aircraft_type": f.get("type"),
                    "callsign": f.get("callsign"),
                    "flight_number": f.get("flight"),
                    "status": "LIVE INBOUND BUSINESS JET (airborne)",
                }
                for f in flights
            ],
        })
    except Exception as e:
        return _error(e, "search_private_arrivals")


# ═════════════════════════════════════════════════════════════════════════════
# 6. get_airport_status
# ═════════════════════════════════════════════════════════════════════════════
_AIRPORT_STATUS_PROPERTIES = json.dumps([
    {
        "propertyName": "airport_code",
        "propertyType": "string",
        "description": "Airport ICAO code, e.g. 'KCOS' or 'KDEN'. Defaults to KCOS (Colorado Springs).",
        "isRequired": False,
    }
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_airport_status",
    description=(
        "Returns a live activity snapshot for an airport: count of flights "
        "currently airborne inbound (arrivals), currently airborne outbound "
        "(departures), and total active flights. Use for 'how busy is COS "
        "right now', 'how many flights are around Denver', 'live airport "
        "status'. Defaults to Colorado Springs (KCOS). This counts live "
        "airborne traffic, not a scheduled board; delayed-flight counts are "
        "not available."
    ),
    tool_properties=_AIRPORT_STATUS_PROPERTIES,
)
def get_airport_status(context) -> str:
    args = _parse_args(context)
    airport_code = (str(args.get("airport_code") or "")).strip().upper() or COS_ICAO
    try:
        client = Flightradar24Client()
        arrivals_count = client.live_flight_count(airports=f"inbound:{airport_code}")
        departures_count = client.live_flight_count(airports=f"outbound:{airport_code}")
        return _dump({
            "airport": airport_code,
            "status_type": "LIVE AIRBORNE TRAFFIC COUNT",
            "scheduled_board": False,
            "arrivals_count": arrivals_count,
            "departures_count": departures_count,
            "active_flights": arrivals_count + departures_count,
            "delayed_flights": None,
            "delay_note": "Delay data is unavailable from the Flightradar24 live positions count endpoint. Use get_scheduled_arrivals for scheduled times and delays.",
        })
    except Exception as e:
        return _error(e, "get_airport_status")
