"""
Effective charging rates by station and hour of day.

Tesla does not publish per-station pricing through any reachable API, and
Supercharger rates move with time of day, so a posted figure could not be
fetched and would be stale if it were. What CAN be known exactly is what was
actually billed: cost / energy for a session tells you the rate paid, and the
start hour tells you when. Across enough sessions the peak and off-peak
boundaries emerge from real spend rather than from a published schedule, and
they stay correct when Tesla changes them.

Rates are ENERGY-WEIGHTED (total cost / total kWh), never a mean of per-session
rates: a 5 kWh top-up and a 60 kWh fill must not carry equal weight.

Honest limits, surfaced to the caller rather than hidden:
  * A session straddling a rate boundary is billed partly at each; its derived
    rate is a blend. Reported as `spans_boundary_risk`.
  * Sessions with no recorded cost are counted and reported separately, never
    silently treated as free — that would drag every average toward zero.
  * Idle fees, if any, are inside `cost` and inflate the derived rate.
"""

from collections import defaultdict
from typing import Iterable

#: Below this, an hour bucket is an anecdote rather than a rate.
MIN_SESSIONS_FOR_HOURLY_RATE = 2

#: A session longer than this likely crosses a peak/off-peak boundary.
LONG_SESSION_MINUTES = 90


def _hour_of(start_time) -> int | None:
    """Start hour (0-23) from an ISO-ish local timestamp string."""
    text = str(start_time or "")
    if "T" in text:
        text = text.split("T", 1)[1]
    elif " " in text:
        text = text.split(" ", 1)[1]
    else:
        return None
    try:
        return int(text.split(":", 1)[0])
    except (ValueError, IndexError):
        return None


def _duration_minutes(start_time, end_time) -> float | None:
    import datetime
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            a = datetime.datetime.strptime(str(start_time), fmt)
            b = datetime.datetime.strptime(str(end_time), fmt)
            return max((b - a).total_seconds() / 60.0, 0.0)
        except (ValueError, TypeError):
            continue
    return None


def _rate(cost: float, kwh: float) -> float | None:
    return round(cost / kwh, 4) if kwh > 0 and cost > 0 else None


def invoices_to_sessions(invoices: Iterable[dict], since_epoch: float | None = None) -> list:
    """Normalise Tesla charging invoices into the shape summarize_rates expects.

    Invoices are the authoritative source: `cost_per_kwh` is the rate Tesla
    actually billed, so tiers are read rather than inferred, and `location` is
    a site name instead of a street address. Idle fees are folded into cost —
    they are real money paid at that station — but kept visible upstream.
    """
    import datetime

    out = []
    for inv in invoices or []:
        started = inv.get("started_at")
        if since_epoch is not None and started is not None:
            try:
                if float(started) < since_epoch:
                    continue
            except (TypeError, ValueError):
                pass

        start_time = None
        if started is not None:
            try:
                # Mountain Time: the operating timezone every other date in this
                # system uses. A UTC hour would misplace evening peak sessions.
                mt = datetime.timezone(datetime.timedelta(hours=-6))
                start_time = datetime.datetime.fromtimestamp(float(started), mt).strftime("%Y-%m-%dT%H:%M:%S")
            except (TypeError, ValueError, OSError):
                start_time = None

        try:
            fees = float(inv.get("charging_fees") or 0)
            idle = float(inv.get("idle_fees") or 0)
            total = float(inv.get("total_cost") if inv.get("total_cost") is not None else fees + idle)
            energy = float(inv.get("energy_used") or 0)
        except (TypeError, ValueError):
            continue

        out.append({
            "site_name": inv.get("location") or "Unknown",
            "start_time": start_time,
            "end_time": None,
            "energy_added_kwh": energy,
            "cost": total,
            # Tesla's own figure. Preferred over cost/energy, which blends in
            # idle fees and would overstate the per-kWh rate.
            "billed_rate_per_kwh": inv.get("cost_per_kwh"),
            "idle_fees": idle,
        })
    return out


def summarize_rates(sessions: Iterable[dict]) -> dict:
    """Per-station effective rates, broken down by start hour.

    Each session needs: site_name (or location), start_time, energy_added_kwh,
    cost, and optionally end_time.
    """
    by_station = defaultdict(lambda: {
        "cost": 0.0, "kwh": 0.0, "priced": 0, "unpriced": 0,
        "hours": defaultdict(lambda: {"cost": 0.0, "kwh": 0.0, "n": 0, "billed": set()}),
        "long_sessions": 0, "billed_rates": set(), "idle_fees": 0.0,
    })

    for s in sessions or []:
        station = s.get("site_name") or s.get("location") or "Unknown"
        try:
            kwh = float(s.get("energy_added_kwh") or 0)
            cost = float(s.get("cost") or 0)
        except (TypeError, ValueError):
            continue

        bucket = by_station[station]
        if cost <= 0 or kwh <= 0:
            # No price recorded. Counted, never averaged in as free.
            bucket["unpriced"] += 1
            continue

        bucket["priced"] += 1
        bucket["cost"] += cost
        bucket["kwh"] += kwh

        minutes = _duration_minutes(s.get("start_time"), s.get("end_time"))
        if minutes is not None and minutes > LONG_SESSION_MINUTES:
            bucket["long_sessions"] += 1

        billed = s.get("billed_rate_per_kwh")
        if billed is not None:
            try:
                bucket["billed_rates"].add(round(float(billed), 4))
            except (TypeError, ValueError):
                pass
        try:
            bucket["idle_fees"] += float(s.get("idle_fees") or 0)
        except (TypeError, ValueError):
            pass

        hour = _hour_of(s.get("start_time"))
        if hour is not None:
            h = bucket["hours"][hour]
            h["cost"] += cost
            h["kwh"] += kwh
            h["n"] += 1
            if billed is not None:
                try:
                    h["billed"].add(round(float(billed), 4))
                except (TypeError, ValueError):
                    pass

    stations = []
    for name, b in sorted(by_station.items()):
        hourly = []
        for hour in sorted(b["hours"]):
            h = b["hours"][hour]
            rate = _rate(h["cost"], h["kwh"])
            if rate is None:
                continue
            hourly.append({
                "hour": hour,
                "clock": f"{hour:02d}:00",
                # Tesla's billed figure when there is exactly one for this hour;
                # otherwise the energy-weighted derivation. Two different billed
                # rates in one hour means a tier boundary sits inside it, and
                # picking either one would be a guess.
                "rate_per_kwh": (sorted(h["billed"])[0] if len(h["billed"]) == 1 else rate),
                "rate_source": "tesla_invoice" if len(h["billed"]) == 1 else "derived",
                "sessions": h["n"],
                "kwh": round(h["kwh"], 2),
                # Below the threshold this is one data point wearing a rate's
                # clothing; the caller should say so rather than imply a trend.
                "confident": h["n"] >= MIN_SESSIONS_FOR_HOURLY_RATE,
            })

        confident = [h for h in hourly if h["confident"]]
        ranked = sorted(confident or hourly, key=lambda h: h["rate_per_kwh"])
        cheapest = ranked[0] if ranked else None
        priciest = ranked[-1] if ranked else None
        spread = (round(priciest["rate_per_kwh"] - cheapest["rate_per_kwh"], 4)
                  if cheapest and priciest and cheapest is not priciest else None)

        stations.append({
            "station": name,
            "sessions_priced": b["priced"],
            "sessions_without_cost": b["unpriced"],
            "total_kwh": round(b["kwh"], 2),
            "total_cost": round(b["cost"], 2),
            "effective_rate_per_kwh": _rate(b["cost"], b["kwh"]),
            "by_hour": hourly,
            "cheapest_hour": cheapest,
            "priciest_hour": priciest,
            "peak_offpeak_spread_per_kwh": spread,
            "spans_boundary_risk": b["long_sessions"],
            #: Distinct rates Tesla actually billed here — the site's rate card
            #: as observed, e.g. [0.26, 0.29, 0.46] for a three-tier station.
            "billed_rate_tiers": sorted(b["billed_rates"]) or None,
            "idle_fees_total": round(b["idle_fees"], 2) if b["idle_fees"] else None,
        })

    total_priced = sum(s["sessions_priced"] for s in stations)
    total_unpriced = sum(s["sessions_without_cost"] for s in stations)

    caveats = []
    if total_priced == 0:
        caveats.append(
            "No session carries a recorded cost, so no rate can be derived. "
            "Charging cost is not reaching the database — this is a data gap, "
            "not evidence that charging was free."
        )
    if total_unpriced:
        caveats.append(
            f"{total_unpriced} session(s) had no recorded cost and were excluded "
            f"rather than counted as $0.00."
        )
    if any(s["spans_boundary_risk"] for s in stations):
        caveats.append(
            "Some sessions ran over 90 minutes and may straddle a peak/off-peak "
            "boundary; those are billed partly at each rate, so their derived "
            "rate is a blend."
        )
    if total_priced and all(
        not h["confident"] for s in stations for h in s["by_hour"]
    ):
        caveats.append(
            f"No hour has {MIN_SESSIONS_FOR_HOURLY_RATE}+ sessions yet, so hourly "
            f"figures are individual observations rather than established rates."
        )

    return {
        "stations": stations,
        "sessions_priced": total_priced,
        "sessions_without_cost": total_unpriced,
        "caveats": caveats,
    }
