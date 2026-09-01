import json
import pytest
from services.spatial_profitability import (
    DEFAULT_WEAR_RATE_PER_MILE,
    HexProfitability,
    SpatialProfitabilityEngine,
    TripSpatialRecord,
    map_db_row_to_trip_record,
    resolve_origin_zone,
)


def test_ac1_envelope_symmetry():
    """AC-1: Approach distance and duration must be symmetrically bound."""
    trip = TripSpatialRecord(
        trip_id="T1",
        origin_hex="hex_dt",
        gross_earnings=50.0,
        energy_cost=3.0,
        approach_duration_seconds=600,   # 10 mins
        trip_duration_seconds=1200,      # 20 mins -> total 30 mins (0.5 hrs)
        approach_distance_miles=4.0,
        trip_distance_miles=6.0,         # total 10.0 miles
    )

    assert trip.total_engaged_seconds == 1800.0
    assert trip.total_engaged_hours == 0.5
    assert trip.total_engaged_miles == 10.0


def test_ac2_wear_rate_parameterization():
    """AC-2: Wear rate is configurable with a default of $0.13/mi."""
    engine_default = SpatialProfitabilityEngine()
    assert engine_default.wear_rate_per_mile == 0.13

    engine_custom = SpatialProfitabilityEngine(wear_rate_per_mile=0.18)
    assert engine_custom.wear_rate_per_mile == 0.18


def test_ac3_ac5_zero_and_sparsity_handling():
    """AC-3 & AC-5: Unworked or zero-hour hexes return null metrics and is_worked=False."""
    engine = SpatialProfitabilityEngine()
    universe = {"hex_visited", "hex_empty"}
    
    trips = [
        TripSpatialRecord(
            trip_id="T1",
            origin_hex="hex_visited",
            gross_earnings=40.0,
            energy_cost=2.0,
            approach_duration_seconds=300,
            trip_duration_seconds=1500,
            approach_distance_miles=2.0,
            trip_distance_miles=8.0,
        )
    ]

    metrics = engine.aggregate_hex_metrics(trips, known_hex_universe=universe)

    assert metrics["hex_visited"].is_worked is True
    assert metrics["hex_visited"].has_data is True
    assert metrics["hex_visited"].net_per_hour_energy_only is not None
    assert metrics["hex_visited"].net_per_hour_wear_inclusive is not None

    assert metrics["hex_empty"].is_worked is False
    assert metrics["hex_empty"].has_data is False
    assert metrics["hex_empty"].net_per_hour_energy_only is None
    assert metrics["hex_empty"].net_per_hour_wear_inclusive is None


def test_ac4_dual_metric_calculation():
    """AC-4: Calculates both energy-only and wear-inclusive net rates correctly."""
    engine = SpatialProfitabilityEngine(wear_rate_per_mile=0.13)
    
    trips = [
        TripSpatialRecord(
            trip_id="T1",
            origin_hex="hex_a",
            gross_earnings=60.0,
            energy_cost=4.0,
            approach_duration_seconds=600,
            trip_duration_seconds=3000,
            approach_distance_miles=5.0,
            trip_distance_miles=15.0,
        )
    ]

    metrics = engine.aggregate_hex_metrics(trips)
    cell = metrics["hex_a"]

    assert cell.net_per_hour_energy_only == 56.00
    assert cell.net_per_hour_wear_inclusive == 53.40


def test_ac7_reranking_sensitivity():
    """
    AC-7: Acceptance Criterion 7 - Re-ranking Sensitivity.
    Briargate vs Downtown.
    """
    engine = SpatialProfitabilityEngine(wear_rate_per_mile=0.13)

    trips_briargate = [
        TripSpatialRecord(
            trip_id="BG1",
            origin_hex="hex_briargate",
            gross_earnings=50.0,
            energy_cost=4.0,
            approach_duration_seconds=900,
            trip_duration_seconds=2700,
            approach_distance_miles=12.0,
            trip_distance_miles=28.0,
        )
    ]

    trips_downtown = [
        TripSpatialRecord(
            trip_id="DT1",
            origin_hex="hex_downtown",
            gross_earnings=48.0,
            energy_cost=3.0,
            approach_duration_seconds=300,
            trip_duration_seconds=3300,
            approach_distance_miles=2.0,
            trip_distance_miles=8.0,
        )
    ]

    metrics = engine.aggregate_hex_metrics(trips_briargate + trips_downtown)

    rank_energy = engine.rank_hexes(metrics, metric_key="energy_only")
    assert rank_energy == ["hex_briargate", "hex_downtown"]

    rank_wear = engine.rank_hexes(metrics, metric_key="wear_inclusive")
    assert rank_wear == ["hex_downtown", "hex_briargate"]
    assert rank_energy != rank_wear


def test_zone_resolver():
    assert resolve_origin_zone("Briargate Pkwy, Colorado Springs") == "hex_briargate"
    assert resolve_origin_zone("Tejon St, Downtown COS") == "hex_downtown"
    assert resolve_origin_zone("Broadmoor Hotel, Lake Ave") == "hex_broadmoor"
    assert resolve_origin_zone("Woodmen & Meridian, Falcon") == "hex_falcon"
    assert resolve_origin_zone("Palmer Lake / Monument") == "hex_monument"
    assert resolve_origin_zone("COS Airport, Powers Blvd") == "hex_airport_south"
    assert resolve_origin_zone("Denver Tech Center / DTC") == "hex_denver_corridor"


def test_map_db_row_with_tessie_odometer_delta():
    """Tests telemetry reconciliation: Tessie physical distance minus Uber fare distance is approach distance."""
    db_row = {
        "RideID": "R-10029",
        "Pickup_Location": "Research Pkwy, Briargate",
        "Distance_mi": 10.0,
        "Duration_min": 20.0,
        "Tessie_Distance": 14.5,  # 4.5 miles approach
        "Energy_Used_kWh": 4.0,
        "Driver_Earnings": 35.0,
        "Sidecar_Artifact_JSON": json.dumps({"approach_duration_seconds": 600}),
    }

    record = map_db_row_to_trip_record(db_row)
    assert record.origin_hex == "hex_briargate"
    assert record.trip_distance_miles == 10.0
    assert record.approach_distance_miles == 4.5
    assert record.total_engaged_miles == 14.5
    assert record.trip_duration_seconds == 1200.0
    assert record.approach_duration_seconds == 600.0
    assert record.total_engaged_seconds == 1800.0
    assert record.gross_earnings == 35.0
    assert record.energy_cost == round(4.0 * 0.12, 2)
