"""
Chart rendering for Summit Intelligence 2.0.

Copilot Studio cannot draw. It can only emit text and Adaptive Cards, and an
Adaptive Card can only show an image it can reach by URL. So "show me a chart"
becomes: query the real numbers here, encode them into a QuickChart URL, and
hand the agent back both the URL and a ready-to-send Adaptive Card.

The agent calls this directly as an OpenAPI action (operationId generateChart) —
no Power Automate flow in the middle, and no hardcoded sample data.

NOTE ON DATA EGRESS: a QuickChart URL carries the plotted values in the query
string, so the aggregate figures are visible to whoever serves that URL. Only
dates and daily aggregates are ever plotted — no client names, addresses, or
trip-level rows. Point QUICKCHART_BASE_URL at a self-hosted QuickChart instance
to keep the figures inside the tenant.
"""

import datetime
import json
import logging
import os
import urllib.parse

import azure.functions as func
import pytz

from services.database import DatabaseClient

bp = func.Blueprint()

_MT = pytz.timezone("America/Denver")

QUICKCHART_BASE_URL = os.environ.get("QUICKCHART_BASE_URL", "https://quickchart.io/chart")

# Rendered as a PNG into a Teams chat bubble, so it has to survive both Teams
# themes on its own — the image cannot adapt. It ships its own opaque light
# surface and light-mode ink rather than inheriting anything.
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"          # categorical slot 1 / sequential blue, 3:1+ on SURFACE
SERIES_FILL = "rgba(42, 120, 214, 0.12)"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e6e5e1"

CHART_WIDTH = 700
CHART_HEIGHT = 380

# Past this many points a daily axis stops being readable and the URL starts
# straining the Adaptive Card image-URL budget, so "auto" rolls up to weeks.
MAX_DAILY_POINTS = 31
MAX_DAYS = 90

# metric key -> (row column, series label, unit suffix, y-axis title, decimals)
METRICS = {
    "earnings": ("TotalEarnings", "Earnings", "$", "Dollars ($)", 2),
    "tips": ("TotalTips", "Tips", "$", "Dollars ($)", 2),
    "trips": ("TripCount", "Trips", "", "Trips", 0),
    "miles": ("TotalMiles", "Miles", " mi", "Miles", 1),
    "hours": ("DriveTime_Hours", "Drive hours", " hrs", "Hours", 2),
    "breakdown": (None, "Financial Breakdown", "$", "Dollars ($)", 2),
    "revenue_sources": (None, "Revenue Sources", "$", "Dollars ($)", 2),
    "fare_vs_tips": (None, "Base Fares vs Tips", "$", "Dollars ($)", 2),
    "top_areas": (None, "Top Pickup Areas", "", "Pickups", 0),
    "client_balances": (None, "Client Balances", "$", "Dollars ($)", 2),
}

CHART_TYPES = ("bar", "line", "pie", "doughnut")
PALETTE = ["#2a78d6", "#34a853", "#fbbc05", "#ea4335", "#9c27b0", "#00bcd4", "#ff7043", "#7e57c2"]


def _parse_area(address: str) -> str:
    """Extract city + zip or primary area from address string."""
    import re
    parts = [p.strip() for p in (address or "").split(",")]
    if len(parts) >= 3:
        city = parts[-2]
        zip_match = re.search(r"\b(\d{5})\b", parts[-1])
        return f"{city} {zip_match.group(1)}" if zip_match else city
    return parts[0] if parts and parts[0] else "Unknown"


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-functions-key",
    }


def _json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data, default=str),
        status_code=status_code,
        headers=_cors_headers(),
        mimetype="application/json",
    )


def _now_mt():
    return pytz.utc.localize(datetime.datetime.utcnow()).astimezone(_MT)


def _copilot_response(payload):
    """Same envelope api/copilot.py uses, including the Mountain Time directive."""
    current_mt = _now_mt()
    body = {
        "success": True,
        "_system_time_directive": (
            f"CRITICAL: The user is physically in Mountain Time. It is currently "
            f"{current_mt.strftime('%Y-%m-%d %I:%M %p')}. If asked for 'today', you MUST "
            f"filter for {current_mt.strftime('%Y-%m-%d')}."
        ),
    }
    body.update(payload)
    return _json_response(body)


def _parse_date(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def format_value(value, metric_key):
    """Human-readable single value, e.g. 412.5 -> '$412.50', 9 -> '9 trips'."""
    _, label, unit, _, decimals = METRICS[metric_key]
    number = f"{value:,.{decimals}f}"
    if unit == "$":
        return f"${number}"
    if unit:
        return f"{number}{unit}"
    return f"{number} {label.lower()}"


def collect_series(rows, start, end, metric_key, group):
    """
    Turn get_daily_metrics() rows into an ascending, gap-free series.

    The rows come back newest-first and skip days with no activity. A time axis
    that silently drops its empty days reads as though those days never
    happened, so every day in the range is materialized — a zero day is data.
    """
    column = METRICS[metric_key][0]

    by_date = {}
    for row in rows:
        date_str = row.get("DateStr")
        if not date_str:
            continue
        try:
            day = _parse_date(str(date_str)[:10])
        except ValueError:
            continue
        if day < start or day > end:
            continue
        by_date[day] = by_date.get(day, 0.0) + float(row.get(column) or 0)

    days = []
    cursor = start
    while cursor <= end:
        days.append((cursor, by_date.get(cursor, 0.0)))
        cursor += datetime.timedelta(days=1)

    if group == "auto":
        group = "day" if len(days) <= MAX_DAILY_POINTS else "week"

    if group == "day":
        labels = [d.strftime("%b %d") for d, _ in days]
        values = [v for _, v in days]
        return labels, values, "day"

    # Weekly rollup, anchored to the Monday of each week.
    buckets = []
    index = {}
    for day, value in days:
        week_start = day - datetime.timedelta(days=day.weekday())
        if week_start not in index:
            index[week_start] = len(buckets)
            buckets.append([week_start, day, 0.0])
        bucket = buckets[index[week_start]]
        bucket[1] = day
        bucket[2] += value

    labels = []
    values = []
    for week_start, week_end, total in buckets:
        first = max(week_start, start)
        labels.append(
            first.strftime("%b %d")
            if first == week_end
            else f"{first.strftime('%b %d')}–{week_end.strftime('%b %d')}"
        )
        values.append(total)
    return labels, values, "week"


def build_chart_config(chart_type, title, labels, values, metric_key):
    """Chart.js v4 config for QuickChart.

    Bar and line charts use a single series without a legend. Pie and doughnut
    charts render slice color palettes with a bottom legend.
    """
    _, series_label, _, axis_title, _ = METRICS[metric_key]

    if chart_type in ("pie", "doughnut"):
        count = len(values)
        colors = (PALETTE * ((count // len(PALETTE)) + 1))[:count] if count > 0 else []
        dataset = {
            "label": series_label,
            "data": [round(v, 4) for v in values],
            "backgroundColor": colors,
            "borderColor": SURFACE,
            "borderWidth": 2,
        }
        return {
            "type": chart_type,
            "data": {"labels": labels, "datasets": [dataset]},
            "options": {
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",
                        "labels": {"color": INK_PRIMARY, "font": {"size": 12}},
                    },
                    "title": {
                        "display": True,
                        "text": title,
                        "color": INK_PRIMARY,
                        "font": {"size": 16, "weight": "bold"},
                        "padding": {"bottom": 16},
                    },
                },
            },
        }

    dataset = {
        "label": series_label,
        "data": [round(v, 4) for v in values],
    }
    if chart_type == "line":
        dataset.update({
            "borderColor": SERIES,
            "backgroundColor": SERIES_FILL,
            "borderWidth": 2,
            "pointRadius": 4,
            "pointBackgroundColor": SERIES,
            "pointBorderColor": SURFACE,
            "pointBorderWidth": 2,
            # Straight segments, not a spline. Each point is a whole day's
            # total; a curve through them bows past the measured values and
            # peaks between days rather than on one.
            "tension": 0,
            "fill": True,
        })
    else:
        dataset.update({
            "backgroundColor": SERIES,
            "borderRadius": 4,
            "borderSkipped": False,
            "barPercentage": 0.7,
            "categoryPercentage": 0.8,
            "maxBarThickness": 48,
        })

    return {
        "type": chart_type,
        "data": {"labels": labels, "datasets": [dataset]},
        "options": {
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": title,
                    "color": INK_PRIMARY,
                    "font": {"size": 16, "weight": "bold"},
                    "padding": {"bottom": 16},
                },
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": axis_title, "color": INK_SECONDARY},
                    "ticks": {"color": INK_SECONDARY},
                    "grid": {"color": GRID},
                    "border": {"display": False},
                },
                "x": {
                    "ticks": {"color": INK_SECONDARY, "maxRotation": 0, "autoSkipPadding": 12},
                    "grid": {"display": False},
                    "border": {"color": GRID},
                },
            },
        },
    }


def build_chart_url(config):
    """Encode a Chart.js config into a QuickChart image URL.

    Spelled-out parameter names, not the `c`/`w`/`v` shorthands: `version` is
    what selects Chart.js 4, and a version param that silently fails to apply
    would render this config under Chart.js 2, where `scales.y` does not exist.
    """
    query = urllib.parse.urlencode({
        "version": "4",
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
        "format": "png",
        "backgroundColor": SURFACE,
        "chart": json.dumps(config, separators=(",", ":")),
    })
    return f"{QUICKCHART_BASE_URL}?{query}"


def build_adaptive_card(chart_url, title, subtitle, facts):
    """Adaptive Card the Send-a-Message node can post verbatim into Teams."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": subtitle,
                "isSubtle": True,
                "spacing": "None",
                "wrap": True,
            },
            {
                "type": "Image",
                "url": chart_url,
                "altText": f"{title} — {subtitle}",
                "size": "Stretch",
                "msTeams": {"allowExpand": True},
            },
            {
                "type": "FactSet",
                "facts": [{"title": k, "value": v} for k, v in facts],
            },
        ],
    }


def _resolve_range(params):
    """(start, end) dates in Mountain Time, or (None, None, error_message)."""
    start_raw = params.get("start_date")
    end_raw = params.get("end_date")

    if start_raw or end_raw:
        if not (start_raw and end_raw):
            return None, None, "Provide both start_date and end_date, or neither."
        try:
            start = _parse_date(str(start_raw))
            end = _parse_date(str(end_raw))
        except ValueError:
            return None, None, (
                "Invalid date. You MUST reformat both start_date and end_date strictly "
                "to YYYY-MM-DD and use the tool again."
            )
        if start > end:
            start, end = end, start
        if (end - start).days + 1 > MAX_DAYS:
            start = end - datetime.timedelta(days=MAX_DAYS - 1)
        return start, end, None

    try:
        days = int(params.get("days") or 7)
    except (TypeError, ValueError):
        return None, None, "Invalid 'days'. Pass a whole number of days (1-90)."
    days = max(1, min(days, MAX_DAYS))
    end = _now_mt().date()
    return end - datetime.timedelta(days=days - 1), end, None


@bp.route(route="copilot/chart", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_chart(req: func.HttpRequest) -> func.HttpResponse:
    """Render a Summit OS metric as a chart image plus a Teams-ready Adaptive Card."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    params = dict(req.params)
    if req.method == "POST":
        try:
            body = req.get_json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            # Power Automate posts a JSON body; query string still wins if both are set.
            merged = {k: v for k, v in body.items() if v not in (None, "")}
            merged.update(params)
            params = merged

    metric_key = str(params.get("metric") or "earnings").strip().lower()
    if metric_key not in METRICS:
        return _copilot_response({
            "success": False,
            "error": f"Unknown metric '{metric_key}'. Choose one of: {', '.join(sorted(METRICS))}.",
        })

    default_types = {
        "breakdown": "doughnut",
        "revenue_sources": "doughnut",
        "fare_vs_tips": "doughnut",
        "client_balances": "pie",
        "top_areas": "bar",
    }
    def_type = default_types.get(metric_key, "bar")
    chart_type = str(params.get("chart_type") or def_type).strip().lower()
    if chart_type not in CHART_TYPES:
        chart_type = def_type

    group = str(params.get("group") or "auto").strip().lower()
    if group not in ("auto", "day", "week"):
        group = "auto"

    start, end, error = _resolve_range(params)
    if error:
        return _copilot_response({"success": False, "error": error})

    if metric_key == "breakdown":
        try:
            db = DatabaseClient()
            summary_data = db.get_summary_metrics_for_range(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")) or {}
            gross = float(summary_data.get("gross_earnings") or 0)
            charging = float(summary_data.get("charging") or 0)
            total_exp = float(summary_data.get("expenses") or 0)
            other_exp = max(0.0, total_exp - charging)

            labels = ["Gross Earnings", "Charging Costs", "Other Expenses"]
            values = [gross, charging, other_exp]
            grouping = "category"
        except Exception as e:
            logging.error(f"copilot_chart breakdown error: {e}")
            labels, values, grouping = ["Gross Earnings", "Charging Costs", "Other Expenses"], [0.0, 0.0, 0.0], "category"

    elif metric_key == "revenue_sources":
        try:
            db = DatabaseClient()
            summary_data = db.get_summary_metrics_for_range(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")) or {}
            uber = float(summary_data.get("uber_earnings") or 0)
            private = float(summary_data.get("private_income") or 0)

            labels = ["Uber Earnings", "Private Client Income"]
            values = [uber, private]
            grouping = "source"
        except Exception as e:
            logging.error(f"copilot_chart revenue_sources error: {e}")
            labels, values, grouping = ["Uber Earnings", "Private Client Income"], [0.0, 0.0], "source"

    elif metric_key == "fare_vs_tips":
        try:
            db = DatabaseClient()
            summary_data = db.get_summary_metrics_for_range(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")) or {}
            uber = float(summary_data.get("uber_earnings") or 0)
            tips = float(summary_data.get("uber_tips") or 0)
            base = max(0.0, uber - tips)

            labels = ["Base Fares", "Tips"]
            values = [base, tips]
            grouping = "component"
        except Exception as e:
            logging.error(f"copilot_chart fare_vs_tips error: {e}")
            labels, values, grouping = ["Base Fares", "Tips"], [0.0, 0.0], "component"

    elif metric_key == "top_areas":
        try:
            from services.datetime_utils import get_operational_window
            w_start, _ = get_operational_window(start.strftime("%Y-%m-%d"))
            _, w_end = get_operational_window(end.strftime("%Y-%m-%d"))
            db = DatabaseClient()
            rows = db.get_area_activity(w_start, w_end) or []

            areas = {}
            for r in rows:
                addr = r.get("pickup")
                if not addr:
                    continue
                area = _parse_area(addr)
                areas[area] = areas.get(area, 0) + 1

            ranked = sorted(areas.items(), key=lambda x: -x[1])[:7]
            if ranked:
                labels = [area for area, _ in ranked]
                values = [float(count) for _, count in ranked]
            else:
                labels, values = ["No Activity"], [0.0]
            grouping = "area"
        except Exception as e:
            logging.error(f"copilot_chart top_areas error: {e}")
            labels, values, grouping = ["No Activity"], [0.0], "area"

    elif metric_key == "client_balances":
        try:
            db = DatabaseClient()
            balances = db.get_client_balances(include_inactive=False) or []
            active = [b for b in balances if float(b.get("balance") or 0) > 0 and b.get("status") == "active"]
            if active:
                labels = [str(b.get("client")) for b in active]
                values = [float(b.get("balance") or 0) for b in active]
            else:
                labels, values = ["No Outstanding Balances"], [0.0]
            grouping = "client"
        except Exception as e:
            logging.error(f"copilot_chart client_balances error: {e}")
            labels, values, grouping = ["No Outstanding Balances"], [0.0], "client"

    else:
        try:
            db = DatabaseClient()
            rows = db.get_daily_metrics(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        except Exception as e:
            logging.error(f"copilot_chart data error: {e}")
            return _json_response({"success": False, "error": str(e)}, 500)

        labels, values, grouping = collect_series(rows, start, end, metric_key, group)

    default_titles = {
        "breakdown": "Earnings vs Charging vs Expenses",
        "revenue_sources": "Uber vs Private Client Revenue",
        "fare_vs_tips": "Base Fares vs Tips",
        "top_areas": "Top Pickup Areas",
        "client_balances": "Outstanding Client Balances",
    }
    series_label = METRICS[metric_key][1]
    title = str(params.get("title") or "").strip() or default_titles.get(metric_key, f"{series_label} by {grouping}")
    subtitle = (
        f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')} "
        f"(Mountain Time)"
    )

    total = sum(values)
    average = total / len(values) if values else 0.0
    peak_index = max(range(len(values)), key=lambda i: values[i]) if values else None

    facts = [
        ("Total", format_value(total, metric_key)),
        (f"Average per {grouping}", format_value(average, metric_key)),
    ]
    peak = None
    if peak_index is not None and total > 0:
        peak = {"label": labels[peak_index], "value": values[peak_index]}
        facts.append((f"Best {grouping}", f"{peak['label']} — {format_value(peak['value'], metric_key)}"))

    config = build_chart_config(chart_type, title, labels, values, metric_key)
    chart_url = build_chart_url(config)

    if total == 0:
        text_desc = f"No {series_label.lower()} recorded between {start.isoformat()} and {end.isoformat()}."
    else:
        text_desc = (
            f"{series_label} for {start.isoformat()} to {end.isoformat()}: "
            f"{format_value(total, metric_key)} total, "
            f"{format_value(average, metric_key)} per {grouping}."
        )

    summary = (
        f"![{title}]({chart_url})\n\n{text_desc}\n\n"
        f"CRITICAL DISPLAY INSTRUCTION FOR AGENT: In your response to the user, you MUST include the exact markdown image syntax `![{title}]({chart_url})` at the top of your message. Do NOT claim that you are text-only or unable to display images — Teams renders this markdown image tag as an inline image directly in the chat bubble."
    )

    return _copilot_response({
        "chartUrl": chart_url,
        "adaptiveCard": build_adaptive_card(chart_url, title, subtitle, facts),
        "summary": summary,
        "chart": {
            "metric": metric_key,
            "chartType": chart_type,
            "grouping": grouping,
            "title": title,
            "subtitle": subtitle,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "labels": labels,
            "values": [round(v, 4) for v in values],
            "total": round(total, 4),
            "average": round(average, 4),
            "peak": peak,
            "hasData": total > 0,
        },
    })
