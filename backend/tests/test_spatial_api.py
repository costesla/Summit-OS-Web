import json
from unittest.mock import MagicMock, patch
import azure.functions as func
from api.spatial_profitability import get_spatial_profitability


def test_spatial_profitability_api_endpoint_fallback():
    req = func.HttpRequest(
        method="GET",
        url="/api/spatial/profitability",
        params={"wear_rate": "0.13"},
        body=b"",
    )

    response = get_spatial_profitability(req)
    assert response.status_code == 200

    payload = json.loads(response.get_body().decode("utf-8"))
    assert payload["wear_rate_per_mile"] == 0.13
    assert payload["hex_count"] == 9
    assert payload["worked_count"] == 4
    assert payload["spec_compliance"]["envelope_symmetry"] == "ENFORCED"
    assert payload["spec_compliance"]["criterion_7_satisfied"] is True
    assert payload["rankings"]["reranked"] is True


def test_spatial_profitability_api_with_mocked_db():
    mock_db_rows = [
        {
            "RideID": "R-101",
            "Pickup_Location": "Downtown Tejon St",
            "Distance_mi": 5.0,
            "Duration_min": 15.0,
            "Tessie_Distance": 6.5,
            "Energy_Used_kWh": 1.8,
            "Driver_Earnings": 28.0,
            "Sidecar_Artifact_JSON": json.dumps({"approach_duration_seconds": 240}),
        },
        {
            "RideID": "R-102",
            "Pickup_Location": "Briargate Pkwy",
            "Distance_mi": 25.0,
            "Duration_min": 35.0,
            "Tessie_Distance": 35.0,
            "Energy_Used_kWh": 8.5,
            "Driver_Earnings": 55.0,
            "Sidecar_Artifact_JSON": json.dumps({"approach_duration_seconds": 600}),
        }
    ]

    with patch("api.spatial_profitability.DatabaseClient") as mock_db_cls:
        mock_instance = MagicMock()
        mock_instance.get_spatial_trip_records.return_value = mock_db_rows
        mock_db_cls.return_value = mock_instance

        req = func.HttpRequest(
            method="GET",
            url="/api/spatial/profitability",
            params={"wear_rate": "0.13"},
            body=b"",
        )

        response = get_spatial_profitability(req)
        assert response.status_code == 200
        payload = json.loads(response.get_body().decode("utf-8"))

        assert payload["source"] == "live_sql_db"
        assert payload["trips_processed"] == 2
        assert payload["worked_count"] == 2
