"""Regression tests for blended-mission tag stripping and operational-leg
filtering, including numbered leg suffixes (e.g. "pickup 1", "Stop 1").

These tests guard the June 4th "Terrance" scenario where three legs
("Terrance - pickup 1", "Terrance Stop 1", "Terrance Dropoff 1") must blend
into a single "Terrance" card and resolve to the passenger pickup/dropoff
addresses rather than the empty repositioning (deadhead) leg.

The production logic lives in ``api/copilot.py``, which imports Azure Functions
and several service clients at module load. To keep this test runnable in a
bare environment we stub those heavy dependencies before importing the module;
the helpers under test (regex stripping + operational-leg detection) are plain
module-level functions and are unaffected by the stubs.
"""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# ── Stub heavy/optional dependencies so api.copilot can be imported ──────────
sys.path.insert(0, os.path.dirname(__file__))

for _mod in ("azure", "azure.functions",
             "services", "services.database", "services.tessie",
             "services.vector_store", "services.agent_orchestrator"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# azure.functions is used at import time (Blueprint, AuthLevel, decorators).
_az_func = sys.modules["azure.functions"]
_az_func.Blueprint = MagicMock
_az_func.AuthLevel = types.SimpleNamespace(ANONYMOUS="anonymous")
_az_func.HttpRequest = object
_az_func.HttpResponse = object
sys.modules["azure"].functions = _az_func

# Service clients referenced via ``from services.x import Y``.
sys.modules["services.database"].DatabaseClient = MagicMock
sys.modules["services.tessie"].TessieClient = MagicMock
sys.modules["services.vector_store"].VectorStore = MagicMock
sys.modules["services.agent_orchestrator"].SystemOrchestrator = MagicMock

from api import copilot  # noqa: E402


# ── 1. is_operational_leg recognizes numbered operational tags ───────────────
@pytest.mark.parametrize("tag", [
    "Terrance - pickup 1",
    "Terrance pickup 1",
    "Jackie 1 En Route",
    "Esmeralda Staging 2",
    "Daniel Home",
    "reposition",
    "pickup",
])
def test_is_operational_leg_true(tag):
    assert copilot.is_operational_leg(tag) is True


@pytest.mark.parametrize("tag", [
    "Terrance Stop 1",       # carries the passenger
    "Terrance Dropoff 1",    # passenger dropoff
    "Terrance",              # base mission tag
    "Jackie",
    "",
    None,
])
def test_is_operational_leg_false(tag):
    assert copilot.is_operational_leg(tag) is False


# ── 2. Numbered leg suffixes strip to a shared base tag ──────────────────────
def test_numbered_legs_strip_to_base_tag():
    legs = ["Terrance - pickup 1", "Terrance Stop 1", "Terrance Dropoff 1"]
    bases = [copilot.strip_operational_suffix(t) for t in legs]
    assert bases == ["Terrance", "Terrance", "Terrance"]


@pytest.mark.parametrize("raw,expected", [
    ("Jackie En Route", "Jackie"),
    ("Jackie enroute 2", "Jackie"),
    ("Esmeralda - Dropoff", "Esmeralda"),
    ("Daniel arrival 3", "Daniel"),
    ("Terrance Staging 1", "Terrance"),
    # A bare operational word must NOT be stripped to empty.
    ("Staging", "Staging"),
    ("Home", "Home"),
])
def test_strip_operational_suffix(raw, expected):
    assert copilot.strip_operational_suffix(raw) == expected


# ── 3. Blended endpoints resolve to passenger pickup / dropoff ───────────────
def _leg(tag, start_addr, end_addr, start_ll=(0.0, 0.0), end_ll=(0.0, 0.0)):
    return {
        "tag": tag,
        "starting_location": start_addr,
        "ending_location": end_addr,
        "starting_latitude": start_ll[0],
        "starting_longitude": start_ll[1],
        "ending_latitude": end_ll[0],
        "ending_longitude": end_ll[1],
    }


def test_blended_endpoints_skip_deadhead_pickup_leg():
    # Chronological order: empty drive to pickup, passenger leg, dropoff leg.
    drives = [
        _leg("Terrance - pickup 1", "Depot",            "3620 Verde Drive"),
        _leg("Terrance Stop 1",     "3620 Verde Drive", "Midpoint"),
        _leg("Terrance Dropoff 1",  "Midpoint",         "1043 Synthes Avenue"),
    ]
    endpoints = copilot.resolve_blended_endpoints(drives)
    # Start skips the operational "pickup 1" deadhead → passenger pickup.
    assert endpoints["start"] == "3620 Verde Drive"
    # End is the passenger dropoff.
    assert endpoints["end"] == "1043 Synthes Avenue"


def test_blended_endpoints_all_operational_falls_back():
    drives = [
        _leg("Home", "A", "B"),
        _leg("Staging 1", "B", "C"),
    ]
    endpoints = copilot.resolve_blended_endpoints(drives)
    assert endpoints["start"] == "A"
    assert endpoints["end"] == "C"


def test_blended_endpoints_empty():
    assert copilot.resolve_blended_endpoints([]) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
