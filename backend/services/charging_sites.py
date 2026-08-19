"""
Supercharger site registry — classify a charging session by where it happened.

Why coordinates rather than the address string
----------------------------------------------
The previous rule was `"supercharger" in location.lower()`, tested against the
location Tessie reports. Tessie reports STREET ADDRESSES, so that substring is
never present: on 2026-08-19 all eight of the operator's most recent sessions
were Superchargers (matched here to within 10 m) and every one of them was
classified as "not a Supercharger", sending the entire Supercharger spend into
the other-charging bucket and reporting $0.00 Supercharger cost.

Address strings cannot be repaired by better matching. "East Tyler Street,
Colorado Springs" and the site named "Colorado Springs, CO - E Tyler St" share
no reliable token, and back-country charging — where this matters most — has
the least predictable naming of all.

Design notes
------------
* The registry is a PINNED SNAPSHOT, not a live call. Classification must be
  deterministic and must not depend on a third-party site being reachable at
  the moment a report is generated.
* Sites that are not yet open (PLAN, PERMIT, CONSTRUCTION, VOTING) are kept
  deliberately. A session cannot physically occur at an unbuilt site, so they
  cost nothing in false positives, and the snapshot stays correct as they open.
* Absent coordinates yield UNKNOWN, never False. Rows written before
  coordinates were persisted must not be silently reported as non-Supercharger
  — that is the same failure this module exists to remove.
"""

import json
import math
import os
from typing import NamedTuple, Optional

#: A session is attributed to a site within this distance. Site footprints run
#: to a few tens of metres; 250 m absorbs GPS scatter and large parking areas
#: without reaching a neighbouring business. Real matches came in under 10 m.
MATCH_RADIUS_M = 250.0

_EARTH_RADIUS_M = 6371000.0
_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "supercharger_sites.json")

_sites: Optional[list] = None


class SiteMatch(NamedTuple):
    """Outcome of classifying one session.

    is_supercharger is None when it cannot be determined (no coordinates),
    which callers must report separately rather than folding into False.
    """
    is_supercharger: Optional[bool]
    site_name: Optional[str]
    distance_m: Optional[float]


UNKNOWN = SiteMatch(None, None, None)


def _load() -> list:
    global _sites
    if _sites is None:
        try:
            with open(os.path.abspath(_REGISTRY_PATH), encoding="utf-8") as fh:
                _sites = json.load(fh).get("sites") or []
        except Exception:
            # A missing registry must not take a financial report down; it
            # degrades to UNKNOWN, which is visible, rather than to False.
            _sites = []
    return _sites


def distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lam = math.radians(lon_b - lon_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lam / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def classify(lat, lon) -> SiteMatch:
    """Attribute a session to a Supercharger site, or report it as not one.

    Returns UNKNOWN when coordinates are absent or unusable — the caller decides
    how to surface that, and must not treat it as a negative.
    """
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return UNKNOWN
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return UNKNOWN
    if lat_f == 0.0 and lon_f == 0.0:
        return UNKNOWN  # null island: a missing fix, not the Gulf of Guinea

    best, best_d = None, float("inf")
    for site in _load():
        d = distance_m(lat_f, lon_f, site["lat"], site["lon"])
        if d < best_d:
            best, best_d = site, d

    if best is not None and best_d <= MATCH_RADIUS_M:
        return SiteMatch(True, best["n"], round(best_d, 1))
    return SiteMatch(False, None, round(best_d, 1) if best else None)
