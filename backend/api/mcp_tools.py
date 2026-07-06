"""
MCP tools blueprint — exposes SummitOS business data as Model Context
Protocol tools via the Azure Functions MCP extension (streamable HTTP at
/runtime/webhooks/mcp, secured by the `mcp_extension` system key).

Consumed by the Copilot Studio agent. Tool descriptions here are what the
agent's orchestrator uses to decide when to call each tool, and they cannot
be edited later in Copilot Studio — write them the way questions get asked.

Date boundary rule: every tool in this module MUST derive its day window
from services.datetime_utils.get_operational_window() (04:00 -> 04:00
Mountain). Do not reintroduce midnight or fixed-UTC-offset windows.
"""
import azure.functions as func
import json
import logging
import datetime
import os

from services.database import DatabaseClient
from services.datetime_utils import get_operational_window, get_timezone

bp = func.Blueprint()

_DAY_SUMMARY_PROPERTIES = json.dumps([
    {
        "propertyName": "date",
        "propertyType": "string",
        "description": "Operational date in YYYY-MM-DD format. Omit to use the current operational day (Mountain Time, 4 AM boundary).",
        "isRequired": False,
    }
])


def _current_operational_date() -> str:
    """Date of the operational day we are currently inside (MT, 4 AM rule).

    At 1 AM Wednesday the business is still in Tuesday's operational day,
    so 'today' resolves to Tuesday until 04:00.
    """
    now_local = datetime.datetime.now(get_timezone())
    return (now_local - datetime.timedelta(hours=4)).strftime("%Y-%m-%d")


def _money(value) -> float:
    return round(float(value or 0), 2)


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_day_summary",
    description=(
        "Returns the complete operational summary for a single business day "
        "(4 AM to 4 AM Mountain Time): trip count and per-trip detail, Uber "
        "earnings, private income, charging and other expenses, net profit, "
        "private payments received that day, and any bookings still awaiting "
        "payment. Use this for any question about how a specific day went — "
        "'how did Tuesday go', 'what did we make yesterday', 'did we get "
        "paid for Saturday's trips'."
    ),
    tool_properties=_DAY_SUMMARY_PROPERTIES,
)
def get_day_summary(context) -> str:
    try:
        args = json.loads(context).get("arguments") or {}
    except Exception:
        args = {}

    date_str = (str(args.get("date") or "")).strip() or _current_operational_date()
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return json.dumps({
            "error": f"Invalid date '{date_str}'. You MUST reformat the date strictly to YYYY-MM-DD and use the tool again."
        })

    try:
        window_start, window_end = get_operational_window(date_str)

        db = DatabaseClient()
        totals   = db.get_summary_metrics_for_range(date_str, date_str)
        trips    = db.get_trips_by_date(date_str)
        payments = db.get_private_payments(date_str, date_str)
        expenses = db.get_expenses_by_date(date_str)
        unpaid   = db.get_unpaid_trips(date_str, active_only=True)

        charging_sessions = expenses.get("charging", [])
        charging_cost = round(sum(_money(c.get("amount")) for c in charging_sessions), 2)

        result = {
            "date": date_str,
            "operational_window": {
                "start": window_start.strftime("%Y-%m-%d %H:%M"),
                "end":   window_end.strftime("%Y-%m-%d %H:%M"),
                "timezone": "Mountain Time (America/Denver)",
            },
            "revenue": {
                # uber_earnings already includes tips (OCR trip cards report
                # earnings tip-inclusive); uber_tips_included is the breakdown
                # of how much of that was tips, not an addition.
                "uber_earnings":       _money(totals.get("uber_earnings")),
                "uber_tips_included":  _money(totals.get("uber_tips")),
                "private_income":      _money(totals.get("private_income")),
                "gross_earnings":      _money(totals.get("gross_earnings")),
            },
            "expenses": {
                "charging":  charging_cost,
                "opex_total": _money(totals.get("opex_expenses", totals.get("expenses"))),
                "capex_total": _money(totals.get("capex_expenses")),
                "total": _money(totals.get("expenses")),
            },
            "net_profit": _money(totals.get("net_profit")),
            "trip_count": len(trips),
            "trips": [
                {
                    "id":             t.get("id"),
                    "type":           t.get("type"),
                    "time":           t.get("timestamp"),
                    # fare = what the rider paid; driver_earnings = our cut.
                    # Revenue totals are built from driver_earnings + tip.
                    "fare":            _money(t.get("fare")),
                    "driver_earnings": _money(t.get("driver_earnings")),
                    "platform_cut":    _money(t.get("fees")),
                    "tip":             _money(t.get("tip")),
                    "distance_miles": round(float(t.get("distance_miles") or 0), 1),
                    "classification": t.get("classification"),
                    "pickup":         t.get("pickup_location"),
                    "dropoff":        t.get("dropoff_location"),
                }
                for t in trips
            ],
            "private_payments_received": [
                {
                    "client": p.get("Client"),
                    "amount": _money(p.get("Amount")),
                    "note":   p.get("Note") or "",
                }
                for p in payments
            ],
            "awaiting_payment": [
                {
                    "ride_id":        u.get("rideId"),
                    "start":          u.get("start"),
                    "fare":           _money(u.get("fare")),
                    "classification": u.get("classification"),
                }
                for u in unpaid
            ],
        }
        return json.dumps(result, default=str)

    except Exception as e:
        logging.error(f"MCP get_day_summary failed for {date_str}: {e}")
        return json.dumps({"error": f"Day summary failed: {e}"})


# ═════════════════════════════════════════════════════════════════════
# Tessie vehicle tools
# ═════════════════════════════════════════════════════════════════════

def _get_vin() -> str:
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        from services.secret_manager import SecretManager
        vin = SecretManager().get_secret("TESSIE_VIN")
    return vin


def _operational_window_ts(date_str: str) -> "tuple[int, int]":
    """Operational-day window as UTC unix timestamps for the Tessie API."""
    start, end = get_operational_window(date_str, tz=get_timezone())
    return int(start.timestamp()), int(end.timestamp())


def _resolve_date(args: dict, key: str = "date") -> str:
    return (str(args.get(key) or "")).strip() or _current_operational_date()


def _parse_args(context) -> dict:
    try:
        return json.loads(context).get("arguments") or {}
    except Exception:
        return {}


_INVALID_DATE = "Invalid date '{}'. You MUST reformat the date strictly to YYYY-MM-DD and use the tool again."


def _valid_date(date_str: str) -> bool:
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_vehicle_status",
    description=(
        "Returns the Tesla's live status right now: battery percentage and "
        "range, charging state and charge limit, inside/outside temperature, "
        "climate on/off, current speed, and location. Use for questions like "
        "'how's the car', 'is the car charged', 'where's the car', 'what's "
        "the battery at'. Not for historical questions — use get_drives or "
        "get_day_summary for past days."
    ),
    tool_properties="[]",
)
def get_vehicle_status(context) -> str:
    try:
        from services.tessie import TessieClient
        tessie = TessieClient()
        vin = _get_vin()
        if not vin:
            return json.dumps({"error": "Vehicle VIN not configured"})

        raw_state = tessie.get_vehicle_state(vin)
        if not raw_state:
            return json.dumps({"error": "Vehicle unreachable or asleep"})

        charge_state  = raw_state.get("charge_state", {})
        climate_state = raw_state.get("climate_state", {})
        drive_state   = raw_state.get("drive_state", {})

        # Geofence applies only to location — never to battery/charge data
        public_location = tessie.get_public_state(vin)
        location_hidden = public_location and public_location.get("privacy", False)

        return json.dumps({
            "battery_level_pct": charge_state.get("battery_level"),
            "battery_range_mi":  charge_state.get("battery_range"),
            "charging_state":    charge_state.get("charging_state"),
            "charge_limit_pct":  charge_state.get("charge_limit_soc"),
            "inside_temp_f":  round(climate_state.get("inside_temp") * 9 / 5 + 32, 1) if climate_state.get("inside_temp") is not None else None,
            "outside_temp_f": round(climate_state.get("outside_temp") * 9 / 5 + 32, 1) if climate_state.get("outside_temp") is not None else None,
            "is_climate_on":  climate_state.get("is_climate_on"),
            "speed_mph":      drive_state.get("speed"),
            "location": "Location hidden (privacy geofence active)" if location_hidden else public_location,
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_vehicle_status failed: {e}")
        return json.dumps({"error": f"Vehicle status failed: {e}"})


_DRIVES_PROPERTIES = json.dumps([
    {
        "propertyName": "date",
        "propertyType": "string",
        "description": "Operational date in YYYY-MM-DD format. Omit to use the current operational day (Mountain Time, 4 AM boundary — 'last night' after midnight belongs to the previous date).",
        "isRequired": False,
    }
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_drives",
    description=(
        "Returns the physical driving story for one operational day (4 AM to "
        "4 AM Mountain Time): every drive with distance, duration, energy "
        "used, average and max speed, autopilot miles, battery start/end, "
        "and start/end locations, plus day totals and efficiency (Wh/mi). "
        "Use for questions like 'how far did I drive Tuesday', 'what was my "
        "battery drain', 'how fast did I go'. Not for money questions — use "
        "get_day_summary for revenue and expenses."
    ),
    tool_properties=_DRIVES_PROPERTIES,
)
def get_drives(context) -> str:
    args = _parse_args(context)
    date_str = _resolve_date(args)
    if not _valid_date(date_str):
        return json.dumps({"error": _INVALID_DATE.format(date_str)})

    try:
        from services.tessie import TessieClient
        tessie = TessieClient()
        vin = _get_vin()
        if not vin:
            return json.dumps({"error": "Vehicle VIN not configured"})

        from_ts, to_ts = _operational_window_ts(date_str)
        raw_drives = sorted(
            tessie.get_tagged_drives(vin, from_ts, to_ts) or [],
            key=lambda d: d.get("started_at", 0),
        )

        local_tz = get_timezone()

        def _local_hhmm(ts):
            if not ts:
                return None
            return datetime.datetime.fromtimestamp(ts, tz=local_tz).strftime("%I:%M %p")

        total_miles = total_energy = total_ap = 0.0
        max_speed = 0.0
        battery_start = battery_end = None
        drives = []
        # TODO: address_class masking before any multi-user surface — drive
        # endpoints carry raw GPS-derived addresses and client-encoding tags.
        for d in raw_drives:
            dist    = float(d.get("distance") or d.get("distance_miles") or d.get("odometer_distance") or 0)
            energy  = float(d.get("energy_used") or 0)
            ap      = float(d.get("autopilot_distance") or d.get("autopilot") or 0)
            spd_mph = round(float(d.get("max_speed") or 0) * 0.621371, 1)
            total_miles  += dist
            total_energy += energy
            total_ap     += ap
            max_speed = max(max_speed, spd_mph)

            b_start, b_end = d.get("starting_battery"), d.get("ending_battery")
            if battery_start is None and b_start is not None:
                battery_start = b_start
            if b_end is not None:
                battery_end = b_end

            start_ts, end_ts = d.get("started_at", 0), d.get("ended_at", 0)
            drives.append({
                "tag":              d.get("tag") or "Untagged",
                "start_time":       _local_hhmm(start_ts),
                "end_time":         _local_hhmm(end_ts),
                "duration_minutes": round((end_ts - start_ts) / 60, 1) if start_ts and end_ts else None,
                "distance_miles":   round(dist, 2),
                "energy_used_kwh":  round(energy, 2),
                "avg_speed_mph":    round(float(d.get("average_speed") or 0) * 0.621371, 1),
                "max_speed_mph":    spd_mph,
                "autopilot_miles":  round(ap, 2),
                "starting_battery": b_start,
                "ending_battery":   b_end,
                "start_location":   d.get("starting_location"),
                "end_location":     d.get("ending_location"),
            })

        window_start, window_end = get_operational_window(date_str)
        return json.dumps({
            "date": date_str,
            "operational_window": {
                "start": window_start.strftime("%Y-%m-%d %H:%M"),
                "end":   window_end.strftime("%Y-%m-%d %H:%M"),
                "timezone": "Mountain Time (America/Denver)",
            },
            "drive_count":           len(drives),
            "total_miles":           round(total_miles, 2),
            "total_energy_used_kwh": round(total_energy, 2),
            "total_autopilot_miles": round(total_ap, 2),
            "autopilot_pct":         round(total_ap / total_miles * 100, 1) if total_miles > 0 else None,
            "max_speed_mph":         max_speed,
            "efficiency_wh_mi":      round(total_energy * 1000 / total_miles, 1) if total_miles > 0 else None,
            "battery_start_pct":     battery_start,
            "battery_end_pct":       battery_end,
            "drives":                drives,
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_drives failed for {date_str}: {e}")
        return json.dumps({"error": f"Drives lookup failed: {e}"})


_CHARGING_PROPERTIES = json.dumps([
    {
        "propertyName": "start_date",
        "propertyType": "string",
        "description": "First operational date of the range, YYYY-MM-DD. Omit for the current operational day.",
        "isRequired": False,
    },
    {
        "propertyName": "end_date",
        "propertyType": "string",
        "description": "Last operational date of the range, YYYY-MM-DD (inclusive). Omit to report a single day (start_date only).",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_charging_report",
    description=(
        "Returns charging sessions and costs for one operational day or a "
        "date range (4 AM to 4 AM Mountain Time days): each session's "
        "location, energy added (kWh), cost, and start/end times, plus "
        "totals and a Supercharger vs other-location split. Use for "
        "questions like 'what did charging cost me this week', 'when did I "
        "supercharge', 'how much energy did I add yesterday'."
    ),
    tool_properties=_CHARGING_PROPERTIES,
)
def get_charging_report(context) -> str:
    args = _parse_args(context)
    start_date = _resolve_date(args, "start_date")
    end_date = (str(args.get("end_date") or "")).strip() or start_date
    for d in (start_date, end_date):
        if not _valid_date(d):
            return json.dumps({"error": _INVALID_DATE.format(d)})
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    try:
        window_start, _ = get_operational_window(start_date)
        _, window_end = get_operational_window(end_date)

        db = DatabaseClient()
        rows = db.get_charging_sessions_for_window(window_start, window_end)

        sessions = []
        supercharger_cost = other_cost = 0.0
        for r in rows:
            cost = _money(r.get("cost"))
            loc = r.get("location") or "Unknown"
            is_sc = "supercharger" in loc.lower()
            if is_sc:
                supercharger_cost += cost
            else:
                other_cost += cost
            sessions.append({
                "location":         loc,
                "is_supercharger":  is_sc,
                "start_time":       r.get("start_time"),
                "end_time":         r.get("end_time"),
                "energy_added_kwh": round(float(r.get("energy_added_kwh") or 0), 2),
                "cost":             cost,
            })

        return json.dumps({
            "start_date": start_date,
            "end_date":   end_date,
            "operational_window": {
                "start": window_start.strftime("%Y-%m-%d %H:%M"),
                "end":   window_end.strftime("%Y-%m-%d %H:%M"),
                "timezone": "Mountain Time (America/Denver)",
            },
            "session_count":     len(sessions),
            "total_cost":        round(supercharger_cost + other_cost, 2),
            "supercharger_cost": round(supercharger_cost, 2),
            "other_cost":        round(other_cost, 2),
            "total_energy_added_kwh": round(sum(s["energy_added_kwh"] for s in sessions), 2),
            "sessions":          sessions,
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_charging_report failed for {start_date}..{end_date}: {e}")
        return json.dumps({"error": f"Charging report failed: {e}"})


# ═════════════════════════════════════════════════════════════════════
# Finance tools (Teller-synced data — reads Finance schema, never the
# Teller API directly: agent traffic must not compete with the scheduled
# sync for Chase's rate-limit budget)
# ═════════════════════════════════════════════════════════════════════

def _last_synced(db) -> str:
    return db.get_last_sync_time("teller")


_CLIENT_BALANCE_PROPERTIES = json.dumps([
    {
        "propertyName": "client",
        "propertyType": "string",
        "description": "Optional client first name to filter to. Omit for all active clients ranked by balance.",
        "isRequired": False,
    },
    {
        "propertyName": "include_inactive",
        "propertyType": "boolean",
        "description": "Set true only if explicitly asked about former clients; their balances are written off and excluded by default.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_client_balance",
    description=(
        "Returns outstanding invoice balances for active private clients: "
        "amount owed, invoice count, and oldest unpaid invoice date, ranked "
        "by balance. Future-dated bookings are reported separately as "
        "upcoming, not as money owed. Use for questions like 'who owes me "
        "money', 'what's Emerson's balance', 'how much is outstanding'. "
        "Former clients' written-off balances are excluded unless "
        "explicitly requested. Response includes data_current_as_of (last "
        "bank sync)."
    ),
    tool_properties=_CLIENT_BALANCE_PROPERTIES,
)
def get_client_balance(context) -> str:
    args = _parse_args(context)
    client_filter = (str(args.get("client") or "")).strip().upper()
    include_inactive = bool(args.get("include_inactive"))
    try:
        db = DatabaseClient()
        balances = db.get_client_balances(include_inactive=include_inactive)
        if client_filter:
            balances = [b for b in balances if b["client"].upper() == client_filter]
        return json.dumps({
            "clients": balances,
            "total_outstanding": round(sum(b["balance"] for b in balances if b["status"] == "active"), 2),
            "total_upcoming": round(sum(b.get("upcoming_amount", 0) for b in balances if b["status"] == "active"), 2),
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_client_balance failed: {e}")
        return json.dumps({"error": f"Client balance failed: {e}"})


_PAYMENT_ACTIVITY_PROPERTIES = json.dumps([
    {
        "propertyName": "start_date",
        "propertyType": "string",
        "description": "First calendar date, YYYY-MM-DD. Omit for the last 7 days.",
        "isRequired": False,
    },
    {
        "propertyName": "end_date",
        "propertyType": "string",
        "description": "Last calendar date (inclusive), YYYY-MM-DD. Omit for today.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_payment_activity",
    description=(
        "Returns synced bank transactions for a date range from the payment "
        "tracker: date, account, direction, counterparty, amount, category, "
        "and any anomaly flags. Use for questions like 'what hit the account "
        "this week', 'did the Zelle payment land', 'any unusual charges'. "
        "Response includes data_current_as_of (last bank sync) — recent "
        "transactions may not appear until the next sync."
    ),
    tool_properties=_PAYMENT_ACTIVITY_PROPERTIES,
)
def get_payment_activity(context) -> str:
    args = _parse_args(context)
    local_today = _current_operational_date()
    end_date = (str(args.get("end_date") or "")).strip() or local_today
    default_start = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=7)).strftime("%Y-%m-%d") if _valid_date(end_date) else local_today
    start_date = (str(args.get("start_date") or "")).strip() or default_start
    for d in (start_date, end_date):
        if not _valid_date(d):
            return json.dumps({"error": _INVALID_DATE.format(d)})

    try:
        db = DatabaseClient()
        payments = db.get_payments(date_from=start_date, date_to=end_date, limit=200)
        inbound  = round(sum(p["amount"] for p in payments if p["direction"] == "inbound"), 2)
        outbound = round(sum(p["amount"] for p in payments if p["direction"] == "outbound"), 2)
        return json.dumps({
            "start_date": start_date,
            "end_date": end_date,
            "transaction_count": len(payments),
            "total_inbound": inbound,
            "total_outbound": outbound,
            "anomaly_count": sum(1 for p in payments if p["anomaly_flag"]),
            "transactions": payments,
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_payment_activity failed: {e}")
        return json.dumps({"error": f"Payment activity failed: {e}"})


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_bills_outlook",
    description=(
        "Returns recurring obligations (bills) with their expected day of "
        "month, expected amount, account, and category. Use for questions "
        "like 'what's due this month', 'what bills are coming up', 'what "
        "goes out next week'. Response includes data_current_as_of (last "
        "bank sync)."
    ),
    tool_properties="[]",
)
def get_bills_outlook(context) -> str:
    try:
        db = DatabaseClient()
        obligations = db.get_recurring_obligations()
        for o in obligations:
            o["expected_amount"] = float(o["expected_amount"]) if o.get("expected_amount") is not None else None
            o["tolerance_pct"] = float(o["tolerance_pct"]) if o.get("tolerance_pct") is not None else None
        monthly_total = round(sum(o["expected_amount"] or 0 for o in obligations), 2)
        return json.dumps({
            "obligation_count": len(obligations),
            "expected_monthly_total": monthly_total,
            "obligations": obligations,
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_bills_outlook failed: {e}")
        return json.dumps({"error": f"Bills outlook failed: {e}"})


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_luis_balance",
    description=(
        "Returns the Luis obligation status: current running balance (the "
        "$190/day model — negative means behind), today's entry with tier "
        "and amount sent, and recent daily history. Use for questions like "
        "'where am I with Luis', 'am I caught up with Luis', 'what did I "
        "send Luis this week'. Response includes data_current_as_of (last "
        "bank sync)."
    ),
    tool_properties="[]",
)
def get_luis_balance(context) -> str:
    try:
        db = DatabaseClient()
        data = db.get_luis_balance_history(limit_days=30)
        today_mt = _current_operational_date()
        return json.dumps({
            "current_running_balance": data.get("current_balance"),
            "operational_date": today_mt,
            "today_entry": db.get_luis_log_for_date(today_mt),
            "recent_history": data.get("history", [])[:14],
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_luis_balance failed: {e}")
        return json.dumps({"error": f"Luis balance failed: {e}"})


_SPENDING_PROPERTIES = json.dumps([
    {
        "propertyName": "start_date",
        "propertyType": "string",
        "description": "First calendar date, YYYY-MM-DD. Omit for the last 30 days. Bank history goes back to August 2024.",
        "isRequired": False,
    },
    {
        "propertyName": "end_date",
        "propertyType": "string",
        "description": "Last calendar date (inclusive), YYYY-MM-DD. Omit for today.",
        "isRequired": False,
    },
    {
        "propertyName": "account",
        "propertyType": "string",
        "description": "Optional account filter: '9776' (business) or '2085' (personal). Omit for both.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_spending_summary",
    description=(
        "Returns spending analysis for a date range across both bank "
        "accounts (business 9776, personal 2085): totals by category and "
        "direction, monthly trend, and top merchants by outbound spend. "
        "History reaches back to August 2024. Use for questions like 'what "
        "did I spend on dining in May', 'biggest expenses last quarter', "
        "'business vs personal burn', 'monthly spending trend'. Response "
        "includes data_current_as_of (last bank sync)."
    ),
    tool_properties=_SPENDING_PROPERTIES,
)
def get_spending_summary(context) -> str:
    args = _parse_args(context)
    end_date = (str(args.get("end_date") or "")).strip() or _current_operational_date()
    default_start = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=30)).strftime("%Y-%m-%d") if _valid_date(end_date) else end_date
    start_date = (str(args.get("start_date") or "")).strip() or default_start
    account = (str(args.get("account") or "")).strip() or None
    for d in (start_date, end_date):
        if not _valid_date(d):
            return json.dumps({"error": _INVALID_DATE.format(d)})

    try:
        db = DatabaseClient()
        data = db.get_spending_summary_data(start_date, end_date, account)
        outbound_total = round(sum(c["total"] for c in data.get("by_category", []) if c["direction"] == "outbound"), 2)
        inbound_total  = round(sum(c["total"] for c in data.get("by_category", []) if c["direction"] == "inbound"), 2)
        return json.dumps({
            "start_date": start_date,
            "end_date": end_date,
            "account": account or "both",
            "total_outbound": outbound_total,
            "total_inbound": inbound_total,
            **data,
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_spending_summary failed: {e}")
        return json.dumps({"error": f"Spending summary failed: {e}"})


_SEARCH_TX_PROPERTIES = json.dumps([
    {
        "propertyName": "query",
        "propertyType": "string",
        "description": "Text to search in merchant/counterparty names, categories, and notes (e.g. 'Netflix', 'Supercharger', 'Zelle').",
        "isRequired": True,
    },
    {
        "propertyName": "start_date",
        "propertyType": "string",
        "description": "Optional first calendar date, YYYY-MM-DD. History goes back to August 2024.",
        "isRequired": False,
    },
    {
        "propertyName": "end_date",
        "propertyType": "string",
        "description": "Optional last calendar date (inclusive), YYYY-MM-DD.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="search_transactions",
    description=(
        "Searches bank transactions by merchant, counterparty, category, or "
        "note text across both accounts, newest first (up to 50 results). "
        "Use for questions like 'when did I last pay Netflix', 'show all "
        "Supercharger charges in June', 'find that Zelle from Emerson'. "
        "Response includes data_current_as_of (last bank sync)."
    ),
    tool_properties=_SEARCH_TX_PROPERTIES,
)
def search_transactions(context) -> str:
    args = _parse_args(context)
    query = (str(args.get("query") or "")).strip()
    if not query:
        return json.dumps({"error": "query is required — pass merchant, category, or note text to search for."})
    start_date = (str(args.get("start_date") or "")).strip() or None
    end_date   = (str(args.get("end_date") or "")).strip() or None
    for d in (start_date, end_date):
        if d and not _valid_date(d):
            return json.dumps({"error": _INVALID_DATE.format(d)})

    try:
        db = DatabaseClient()
        results = db.search_payments(query, date_from=start_date, date_to=end_date, limit=50)
        return json.dumps({
            "query": query,
            "result_count": len(results),
            "total_amount": round(sum(r["amount"] for r in results), 2),
            "transactions": results,
            "data_current_as_of": _last_synced(db),
        }, default=str)
    except Exception as e:
        logging.error(f"MCP search_transactions failed: {e}")
        return json.dumps({"error": f"Transaction search failed: {e}"})


# ═════════════════════════════════════════════════════════════════════
# Geography + write tools
# ═════════════════════════════════════════════════════════════════════

_HEATMAP_PROPERTIES = json.dumps([
    {
        "propertyName": "start_date",
        "propertyType": "string",
        "description": "First operational date, YYYY-MM-DD. Omit for the last 30 days.",
        "isRequired": False,
    },
    {
        "propertyName": "end_date",
        "propertyType": "string",
        "description": "Last operational date (inclusive), YYYY-MM-DD. Omit for the current operational day.",
        "isRequired": False,
    },
    {
        "propertyName": "start_time",
        "propertyType": "string",
        "description": (
            "Start of a time-of-day window, HH:MM 24-hour Mountain Time "
            "(e.g. '04:30'). Use with end_time to answer staging questions "
            "like 'morning rush' or 'where should I sit before 10 AM'. "
            "Omit for all hours."
        ),
        "isRequired": False,
    },
    {
        "propertyName": "end_time",
        "propertyType": "string",
        "description": (
            "End of the time-of-day window (exclusive), HH:MM 24-hour "
            "Mountain Time (e.g. '10:00'). Windows that wrap midnight "
            "(start later than end, e.g. 22:00 to 02:00) are supported."
        ),
        "isRequired": False,
    },
])


def _parse_area(address: str) -> str:
    """'5410 N Nevada Ave, Colorado Springs, Colorado 80918, United States'
    -> 'Colorado Springs 80918'. Falls back gracefully on short addresses."""
    import re
    parts = [p.strip() for p in (address or "").split(",")]
    if len(parts) >= 3:
        city = parts[-3]
        zip_match = re.search(r"\b(\d{5})\b", parts[-2])
        return f"{city} {zip_match.group(1)}" if zip_match else city
    return parts[0] if parts and parts[0] else "Unknown"


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_activity_heatmap",
    description=(
        "Returns trip activity aggregated by area of town (city + zip) for a "
        "date range: pickups, dropoffs, and earnings per area, ranked by "
        "activity. Optionally restricted to a time-of-day window via "
        "start_time/end_time (Mountain Time) — use that for staging "
        "questions like 'where should I sit during the morning rush' or "
        "'where are pickups between 4:30 and 10 AM'. Also for questions "
        "like 'what part of town did I spend the day in', 'where do my "
        "best-paying trips come from', 'which neighborhoods were busiest "
        "this month'."
    ),
    tool_properties=_HEATMAP_PROPERTIES,
)
def get_activity_heatmap(context) -> str:
    args = _parse_args(context)
    end_date = _resolve_date(args, "end_date")
    default_start = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=30)).strftime("%Y-%m-%d") if _valid_date(end_date) else end_date
    start_date = (str(args.get("start_date") or "")).strip() or default_start
    for d in (start_date, end_date):
        if not _valid_date(d):
            return json.dumps({"error": _INVALID_DATE.format(d)})

    import re as _re
    start_time = (str(args.get("start_time") or "")).strip() or None
    end_time = (str(args.get("end_time") or "")).strip() or None
    if bool(start_time) != bool(end_time):
        return json.dumps({"error": "start_time and end_time must be provided together (HH:MM, 24-hour Mountain Time)."})
    if start_time:
        for t in (start_time, end_time):
            if not _re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
                return json.dumps({"error": f"Invalid time '{t}' — use HH:MM, 24-hour Mountain Time (e.g. '04:30')."})

    try:
        window_start, _ = get_operational_window(start_date)
        _, window_end = get_operational_window(end_date)
        db = DatabaseClient()
        rows = db.get_area_activity(window_start, window_end, start_time=start_time, end_time=end_time)

        areas = {}
        for r in rows:
            earnings = round(float(r["driver_earnings"] or 0) + float(r["tip"] or 0), 2)
            if earnings == 0 and r["trip_type"] == "Private":
                earnings = round(float(r["fare"] or 0) + float(r["tip"] or 0), 2)
            for kind, addr in (("pickups", r["pickup"]), ("dropoffs", r["dropoff"])):
                if not addr:
                    continue
                area = _parse_area(addr)
                a = areas.setdefault(area, {"area": area, "pickups": 0, "dropoffs": 0, "earnings": 0.0})
                a[kind] += 1
                if kind == "pickups":
                    a["earnings"] = round(a["earnings"] + earnings, 2)

        ranked = sorted(areas.values(), key=lambda a: -(a["pickups"] + a["dropoffs"]))
        return json.dumps({
            "start_date": start_date,
            "end_date": end_date,
            "time_window": f"{start_time}–{end_time} Mountain Time" if start_time else "all hours",
            "area_count": len(ranked),
            "areas": ranked[:25],
            "note": "earnings are attributed to the pickup area of each trip",
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_activity_heatmap failed: {e}")
        return json.dumps({"error": f"Activity heatmap failed: {e}"})


_UPCOMING_BOOKINGS_PROPERTIES = json.dumps([
    {
        "propertyName": "days_ahead",
        "propertyType": "number",
        "description": "How many days forward to look, starting now. Defaults to 7, max 60.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_upcoming_bookings",
    description=(
        "Returns FUTURE bookings and calendar events from the business "
        "calendar: customer, pickup time (Mountain Time), location, and "
        "trip details. Use for questions like 'what's on the schedule "
        "tomorrow', 'do I have any bookings this week', 'when is my next "
        "pickup'. This reads the live calendar, so it includes bookings "
        "made through the website and ones added directly to the calendar."
    ),
    tool_properties=_UPCOMING_BOOKINGS_PROPERTIES,
)
def get_upcoming_bookings(context) -> str:
    args = _parse_args(context)
    try:
        try:
            days_ahead = int(float(args.get("days_ahead") or 7))
        except (TypeError, ValueError):
            days_ahead = 7
        days_ahead = max(1, min(days_ahead, 60))

        from services.graph import GraphClient
        now_local = datetime.datetime.now(get_timezone())
        end_local = now_local + datetime.timedelta(days=days_ahead)
        events = GraphClient().get_calendar_view(now_local, end_local)

        bookings = []
        for ev in events:
            subject = ev.get("subject") or ""
            bookings.append({
                "subject": subject,
                "is_booking": subject.startswith("Booking:"),
                "customer": subject.replace("Booking:", "").strip() if subject.startswith("Booking:") else None,
                "start": (ev.get("start") or {}).get("dateTime"),
                "end": (ev.get("end") or {}).get("dateTime"),
                "location": ((ev.get("location") or {}).get("displayName")) or None,
                "details": (ev.get("bodyPreview") or "")[:300] or None,
            })

        return json.dumps({
            "from": now_local.strftime("%Y-%m-%d %H:%M"),
            "to": end_local.strftime("%Y-%m-%d %H:%M"),
            "timezone": "Mountain Time (America/Denver)",
            "event_count": len(bookings),
            "booking_count": sum(1 for b in bookings if b["is_booking"]),
            "events": bookings,
            "note": "times are already in Mountain Time; is_booking=false rows are other calendar events (time off, personal)",
        }, default=str)
    except Exception as e:
        logging.error(f"MCP get_upcoming_bookings failed: {e}")
        return json.dumps({"error": f"Upcoming bookings lookup failed: {e}"})


_RECORD_EXPENSE_PROPERTIES = json.dumps([
    {
        "propertyName": "amount",
        "propertyType": "number",
        "description": "Expense amount in USD. Must be positive and at most 1000.",
        "isRequired": True,
    },
    {
        "propertyName": "category",
        "propertyType": "string",
        "description": "Expense category, e.g. Food, Fuel, Supplies, Car_Wash, Maintenance, General_Expense. Defaults to Food.",
        "isRequired": False,
    },
    {
        "propertyName": "note",
        "propertyType": "string",
        "description": "Short description, e.g. 'Maverik snacks'. Include the merchant when known.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="record_expense",
    description=(
        "WRITES to the business ledger: records a manual expense (e.g. 'log "
        "a $14 Maverik stop'). Only call this after the user has explicitly "
        "stated the amount and you have confirmed amount and category with "
        "them in this conversation — never guess or infer an amount. The "
        "expense appears immediately in the dashboard and day summaries. "
        "Returns the created expense ID."
    ),
    tool_properties=_RECORD_EXPENSE_PROPERTIES,
)
def record_expense(context) -> str:
    import uuid
    args = _parse_args(context)
    try:
        amount = round(float(args.get("amount")), 2)
    except (TypeError, ValueError):
        return json.dumps({"error": "amount is required and must be a number."})
    if not (0 < amount <= 1000):
        return json.dumps({"error": f"Refusing to record ${amount}: expense amount must be between $0.01 and $1000. Confirm the amount with the user."})

    category = (str(args.get("category") or "Food")).strip()[:50] or "Food"
    note = (str(args.get("note") or "")).strip()[:450]
    expense_id = f"AGENT-{uuid.uuid4().hex[:10].upper()}"
    included_in_kpi = 0 if category in ("Maintenance", "General_Expense") else 1

    try:
        db = DatabaseClient()
        local_now = datetime.datetime.now(get_timezone()).replace(tzinfo=None)
        db.save_manual_expense({
            "id": expense_id,
            "category": category,
            "amount": amount,
            "note": (note + " [via agent]").strip(),
            "timestamp": local_now,
            "included_in_kpi": included_in_kpi,
        })
        return json.dumps({
            "recorded": True,
            "expense_id": expense_id,
            "amount": amount,
            "category": category,
            "note": note,
            "operational_date": _current_operational_date(),
        })
    except Exception as e:
        logging.error(f"MCP record_expense failed: {e}")
        return json.dumps({"error": f"Expense recording failed: {e}"})


_RECORD_PAYMENT_PROPERTIES = json.dumps([
    {
        "propertyName": "client",
        "propertyType": "string",
        "description": "Client first name exactly as the user said it (e.g. Jacquelyn, Emerson).",
        "isRequired": True,
    },
    {
        "propertyName": "amount",
        "propertyType": "number",
        "description": "Payment amount in USD. Must be positive and at most 2000.",
        "isRequired": True,
    },
    {
        "propertyName": "note",
        "propertyType": "string",
        "description": "Optional note, e.g. 'Venmo' or 'cash, two trips'.",
        "isRequired": False,
    },
])


@bp.mcp_tool_trigger(
    arg_name="context",
    tool_name="record_private_payment",
    description=(
        "WRITES to the business ledger: records a private client payment "
        "received (e.g. 'Jacquelyn just Venmo'd me $60'). Only call this "
        "after the user has explicitly stated the client and amount and you "
        "have confirmed both with them in this conversation — never guess. "
        "The payment appears immediately in balances and day summaries. "
        "Returns the created payment ID."
    ),
    tool_properties=_RECORD_PAYMENT_PROPERTIES,
)
def record_private_payment(context) -> str:
    import uuid
    from services.database import INACTIVE_CLIENTS
    args = _parse_args(context)
    client = (str(args.get("client") or "")).strip()
    if not client:
        return json.dumps({"error": "client is required."})
    if client.upper() in INACTIVE_CLIENTS:
        return json.dumps({"error": f"'{client}' is on the written-off/inactive roster — payments for written-off balances are handled manually, not through this tool. Confirm the client name with the user."})
    try:
        amount = round(float(args.get("amount")), 2)
    except (TypeError, ValueError):
        return json.dumps({"error": "amount is required and must be a number."})
    if not (0 < amount <= 2000):
        return json.dumps({"error": f"Refusing to record ${amount}: payment amount must be between $0.01 and $2000. Confirm the amount with the user."})

    note = (str(args.get("note") or "")).strip()[:450]
    payment_id = f"AGENT-{uuid.uuid4().hex[:10].upper()}"

    try:
        db = DatabaseClient()
        local_now = datetime.datetime.now(get_timezone())
        db.upsert_private_payments([{
            "id": payment_id,
            "client": client.title(),
            "amount": amount,
            "note": (note + " [via agent]").strip(),
            "date": _current_operational_date(),
            "timestamp": local_now.strftime("%Y-%m-%d %H:%M:%S"),
        }])
        return json.dumps({
            "recorded": True,
            "payment_id": payment_id,
            "client": client.title(),
            "amount": amount,
            "note": note,
            "operational_date": _current_operational_date(),
        })
    except Exception as e:
        logging.error(f"MCP record_private_payment failed: {e}")
        return json.dumps({"error": f"Payment recording failed: {e}"})
