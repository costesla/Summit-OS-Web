"""
Spatial Profitability Engine - Summit Intelligence
Calculates zone and H3 hexagon-level net yield rates, enforcing envelope symmetry
and separating mile-variable wear costs from energy-only baselines.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set


DEFAULT_WEAR_RATE_PER_MILE = 0.13  # Baseline wear constant ($/mile for tires, brakes, depreciation)
DEFAULT_ELECTRICITY_COST_PER_KWH = 0.12  # Average charging cost


@dataclass(frozen=True)
class TripSpatialRecord:
    trip_id: str
    origin_hex: str
    gross_earnings: float
    energy_cost: float
    approach_duration_seconds: float
    trip_duration_seconds: float
    approach_distance_miles: float
    trip_distance_miles: float

    @property
    def total_engaged_seconds(self) -> float:
        """Enforces envelope symmetry: approach + on-trip duration."""
        return max(0.0, self.approach_duration_seconds + self.trip_duration_seconds)

    @property
    def total_engaged_hours(self) -> float:
        return self.total_engaged_seconds / 3600.0

    @property
    def total_engaged_miles(self) -> float:
        """Enforces envelope symmetry: approach + on-trip distance."""
        return max(0.0, self.approach_distance_miles + self.trip_distance_miles)


@dataclass
class HexProfitability:
    hex_id: str
    trip_count: int = 0
    total_engaged_hours: float = 0.0
    total_engaged_miles: float = 0.0
    total_gross_earnings: float = 0.0
    total_energy_cost: float = 0.0
    total_wear_cost: float = 0.0
    net_per_hour_energy_only: Optional[float] = None
    net_per_hour_wear_inclusive: Optional[float] = None
    is_worked: bool = False
    has_data: bool = False


def resolve_origin_zone(pickup_location: Optional[str], sidecar: Optional[Dict[str, Any]] = None) -> str:
    """Resolves a pickup location or sidecar payload into a normalized spatial zone / H3 hex key."""
    if sidecar:
        if sidecar.get("h3_index"):
            return str(sidecar["h3_index"])
        if sidecar.get("origin_hex"):
            return str(sidecar["origin_hex"])
        if sidecar.get("zone"):
            return str(sidecar["zone"])

    if not pickup_location:
        return "hex_cos_general"

    loc = pickup_location.lower()
    if any(k in loc for k in ["briargate", "research", "voyager", "chapel hills", "pine creek", "cordera"]):
        return "hex_briargate"
    if any(k in loc for k in ["downtown", "tejon", "colorado ave", "nevada", "bijou", "kiowa", "old colorado", "cimarron"]):
        return "hex_downtown"
    if any(k in loc for k in ["broadmoor", "cheyenne", "lake ave", "south academy", "stratmoor"]):
        return "hex_broadmoor"
    if any(k in loc for k in ["falcon", "meridian", "woodmen east", "peyton", "black forest", "easton"]):
        return "hex_falcon"
    if any(k in loc for k in ["monument", "palmer lake", "woodmoor", "jackson creek", "gleneagle"]):
        return "hex_monument"
    if any(k in loc for k in ["airport", "powers south", "fountain", "fort carson", "security", "widefield"]):
        return "hex_airport_south"
    if any(k in loc for k in ["denver", "dia", "castle rock", "lone tree", "dtc", "centennial", "aurora"]):
        return "hex_denver_corridor"

    return "hex_cos_general"


def map_db_row_to_trip_record(
    row: Dict[str, Any],
    default_electricity_rate: float = DEFAULT_ELECTRICITY_COST_PER_KWH,
) -> TripSpatialRecord:
    """Transforms a raw SQL Rides.Rides row into a TripSpatialRecord with strictly bound envelopes."""
    ride_id = str(row.get("RideID") or "")
    pickup = row.get("Pickup_Location")

    sidecar: Dict[str, Any] = {}
    raw_sidecar = row.get("Sidecar_Artifact_JSON")
    if raw_sidecar:
        try:
            sidecar = json.loads(raw_sidecar) if isinstance(raw_sidecar, str) else raw_sidecar
        except Exception:
            sidecar = {}

    origin_hex = resolve_origin_zone(pickup, sidecar)

    earnings = float(row.get("Driver_Earnings") or 0.0)
    if earnings <= 0:
        earnings = float(row.get("Fare") or 0.0) + float(row.get("Tip") or 0.0)

    trip_distance_mi = float(row.get("Distance_mi") or 0.0)
    tessie_distance_mi = float(row.get("Tessie_Distance") or 0.0)

    # Approach distance: if Tessie physical odometer is higher than Uber trip distance, the delta is approach
    if tessie_distance_mi > trip_distance_mi and trip_distance_mi > 0:
        approach_distance_mi = tessie_distance_mi - trip_distance_mi
    else:
        approach_distance_mi = float(sidecar.get("approach_distance_miles") or 0.0)

    # Energy calculation: real kWh from telemetry * rate, or estimated consumption
    energy_kwh = float(row.get("Energy_Used_kWh") or 0.0)
    if energy_kwh > 0:
        energy_cost = energy_kwh * default_electricity_rate
    else:
        # Standard Tesla ~0.28 kWh / mile
        total_mi = trip_distance_mi + approach_distance_mi
        energy_cost = total_mi * 0.28 * default_electricity_rate

    trip_duration_sec = float(row.get("Duration_min") or 0.0) * 60.0
    approach_duration_sec = float(sidecar.get("approach_duration_seconds") or 0.0)
    if approach_duration_sec <= 0 and approach_distance_mi > 0:
        # Approach speed default: 30 mph
        approach_duration_sec = (approach_distance_mi / 30.0) * 3600.0

    return TripSpatialRecord(
        trip_id=ride_id,
        origin_hex=origin_hex,
        gross_earnings=round(earnings, 2),
        energy_cost=round(energy_cost, 2),
        approach_duration_seconds=round(approach_duration_sec, 1),
        trip_duration_seconds=round(trip_duration_sec, 1),
        approach_distance_miles=round(approach_distance_mi, 2),
        trip_distance_miles=round(trip_distance_mi, 2),
    )


class SpatialProfitabilityEngine:
    def __init__(self, wear_rate_per_mile: float = DEFAULT_WEAR_RATE_PER_MILE):
        self.wear_rate_per_mile = float(wear_rate_per_mile)

    def aggregate_hex_metrics(
        self,
        trips: Sequence[TripSpatialRecord],
        known_hex_universe: Optional[Set[str]] = None,
    ) -> Dict[str, HexProfitability]:
        """
        Aggregates trip records into cell-level profitability figures.
        Includes all known hexes in universe, marking unvisited hexes with is_worked=False.
        """
        results: Dict[str, HexProfitability] = {}

        # Initialize known hex universe for honest sparsity visualization
        if known_hex_universe:
            for hex_id in known_hex_universe:
                results[hex_id] = HexProfitability(
                    hex_id=hex_id,
                    is_worked=False,
                    has_data=False,
                )

        # Accumulate trips into cells
        for trip in trips:
            h = trip.origin_hex
            if h not in results:
                results[h] = HexProfitability(hex_id=h)

            cell = results[h]
            cell.trip_count += 1
            cell.total_engaged_hours += trip.total_engaged_hours
            cell.total_engaged_miles += trip.total_engaged_miles
            cell.total_gross_earnings += trip.gross_earnings
            cell.total_energy_cost += trip.energy_cost
            cell.total_wear_cost += trip.total_engaged_miles * self.wear_rate_per_mile

        # Compute hourly yield rates
        for cell in results.values():
            if cell.trip_count > 0 and cell.total_engaged_hours > 0.0:
                cell.is_worked = True
                cell.has_data = True

                # Metric 1: Energy-only baseline
                net_energy = cell.total_gross_earnings - cell.total_energy_cost
                cell.net_per_hour_energy_only = round(net_energy / cell.total_engaged_hours, 2)

                # Metric 2: Wear-inclusive marginal yield
                net_wear = net_energy - cell.total_wear_cost
                cell.net_per_hour_wear_inclusive = round(net_wear / cell.total_engaged_hours, 2)
            else:
                cell.is_worked = False
                cell.has_data = False
                cell.net_per_hour_energy_only = None
                cell.net_per_hour_wear_inclusive = None

        return results

    def rank_hexes(
        self,
        metrics: Dict[str, HexProfitability],
        metric_key: str = "wear_inclusive",
    ) -> List[str]:
        """
        Ranks worked hexes in descending order of net yield.
        metric_key: 'energy_only' | 'wear_inclusive'
        """
        worked_cells = [c for c in metrics.values() if c.is_worked and c.has_data]

        if metric_key == "energy_only":
            worked_cells.sort(
                key=lambda c: (c.net_per_hour_energy_only is not None, c.net_per_hour_energy_only or 0.0),
                reverse=True,
            )
        else:
            worked_cells.sort(
                key=lambda c: (c.net_per_hour_wear_inclusive is not None, c.net_per_hour_wear_inclusive or 0.0),
                reverse=True,
            )

        return [c.hex_id for c in worked_cells]
