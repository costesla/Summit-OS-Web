"""
Time-of-use rate cards, mirroring what the operator configures in Tessie.

These are INPUT, not evidence. Billed cost is always authoritative; a card is
a statement of what pricing is believed to be, and believing it does not make
it so. Confirmed 2026-08-19: at E Tyler St the card predicted $651.01 across
45 days while Tessie actually recorded $708.78 — 8.9% higher. A tool that
reported the card as "the rate" would have been wrong by ~$470/year at one
station and looked authoritative doing it.

So a card is used for exactly two things:
  1. Filling sessions that arrive with NO cost at all — marked estimated.
  2. Reconciling billed against expected, so drift is visible rather than
     absorbed silently.

Sessions straddling a band boundary are the reason this module knows about
time at all. A 27-minute session starting 08:45 crosses into peak at 09:00 and
billed $0.3566 against a $0.26 band; bucketing it by start hour alone would
quietly corrupt the off-peak figure. Duration heuristics miss these — only the
band edges reveal them.
"""

import datetime
import json
import os
from typing import NamedTuple, Optional

_CARDS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "charging_rate_cards.json")
_cards: Optional[dict] = None

_MINUTES_PER_DAY = 24 * 60


class Band(NamedTuple):
    start_min: int
    end_min: int   # exclusive; 1440 means midnight
    rate: float


class CostEstimate(NamedTuple):
    """An estimate, never to be presented as a billed figure."""
    amount: float
    spans_boundary: bool
    bands_used: tuple


def _load() -> dict:
    global _cards
    if _cards is None:
        try:
            with open(os.path.abspath(_CARDS_PATH), encoding="utf-8") as fh:
                _cards = json.load(fh).get("cards") or {}
        except Exception:
            _cards = {}
    return _cards


def _to_minutes(hhmm: str) -> int:
    hours, _, minutes = str(hhmm).partition(":")
    return int(hours) * 60 + int(minutes or 0)


def bands_for(site_name: str) -> list:
    """Bands for a site, or [] when no card is configured.

    Matching is exact then loose, because the same station reaches this code
    both as a registry name and as a raw address.
    """
    cards = _load()
    card = cards.get(site_name)
    if card is None and site_name:
        needle = site_name.lower()
        for name, value in cards.items():
            if name.lower() in needle or needle in name.lower():
                card = value
                break
    if not card:
        return []
    out = []
    for band in card.get("bands") or []:
        try:
            start = _to_minutes(band["start"])
            end = _to_minutes(band["end"]) or _MINUTES_PER_DAY
            out.append(Band(start, end, float(band["rate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda b: b.start_min)


def rate_at(site_name: str, when: datetime.datetime) -> Optional[float]:
    """The card's rate at an instant, or None when no card covers it."""
    minute = when.hour * 60 + when.minute
    for band in bands_for(site_name):
        if band.start_min <= minute < band.end_min:
            return band.rate
    return None


def _minutes_per_band(site_name: str, start: datetime.datetime,
                      end: datetime.datetime) -> dict:
    """How many minutes of a session fall in each band, following it across
    midnight rather than assuming a session ends on the day it began."""
    bands = bands_for(site_name)
    if not bands or end <= start:
        return {}

    total = int((end - start).total_seconds() // 60)
    if total <= 0:
        return {}

    spent = {}
    cursor = start.hour * 60 + start.minute
    for _ in range(total):
        for band in bands:
            if band.start_min <= cursor < band.end_min:
                spent[band.rate] = spent.get(band.rate, 0) + 1
                break
        cursor = (cursor + 1) % _MINUTES_PER_DAY
    return spent


def estimate_cost(site_name: str, start: datetime.datetime,
                  end: Optional[datetime.datetime], kwh: float) -> Optional[CostEstimate]:
    """Estimate a session's cost from the card, prorating energy across bands.

    Energy is apportioned by TIME in each band, which assumes a roughly even
    charge curve. Real curves taper as the battery fills, so a session ending
    in a dearer band is slightly overestimated. Acceptable for filling a gap;
    not acceptable as a substitute for a billed figure, which is why the result
    is labelled an estimate all the way to the caller.
    """
    if not kwh or kwh <= 0:
        return None
    bands = bands_for(site_name)
    if not bands:
        return None

    if end is None or end <= start:
        rate = rate_at(site_name, start)
        if rate is None:
            return None
        return CostEstimate(round(rate * kwh, 2), False, (rate,))

    spent = _minutes_per_band(site_name, start, end)
    if not spent:
        return None
    total_minutes = sum(spent.values())
    amount = sum(rate * kwh * (minutes / total_minutes) for rate, minutes in spent.items())
    return CostEstimate(round(amount, 2), len(spent) > 1, tuple(sorted(spent)))


def spans_boundary(site_name: str, start: datetime.datetime,
                   end: Optional[datetime.datetime]) -> bool:
    """True when a session crosses into a differently-priced band.

    Replaces the duration heuristic this started with: a 27-minute session
    beginning 08:45 crosses a boundary while a 70-minute one beginning 21:00
    does not, and only the band edges can tell them apart.
    """
    if end is None or end <= start:
        return False
    return len(_minutes_per_band(site_name, start, end)) > 1
