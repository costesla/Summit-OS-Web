import pytest
import json
import azure.functions as func
from unittest.mock import patch, MagicMock
from api.trip_yield import get_trip_yield

def test_trip_yield_options():
    req = func.HttpRequest(
        method="OPTIONS",
        url="/api/analytics/trip-yield",
        headers={"Origin": "https://www.costesla.com"},
        params={},
        body=b""
    )
    resp = get_trip_yield(req)
    assert resp.status_code == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://www.costesla.com"

@patch("api.trip_yield.require_function_key")
@patch("api.trip_yield.DatabaseClient")
def test_trip_yield_corridors(mock_db_client, mock_auth):
    mock_auth.return_value = None
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_db_client.return_value.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock row: RideID, TripType, Timestamp_Start, Start_Lat, Start_Lng, End_Lat, End_Lng, Dist, Dur, kWh, gross, engaged_hours, is_estimated
    mock_cursor.fetchall.return_value = [
        ("INV-1", "Private", MagicMock(isoformat=lambda: "2026-06-01T10:00:00"), 38.85, -104.82, 38.95, -104.79, 10.0, 30, 2.0, 50.0, 0.5, 0),
        ("UBER-1", "Uber", MagicMock(isoformat=lambda: "2026-06-01T12:00:00"), 38.83, -104.81, 38.90, -104.78, 5.0, 15, None, 20.0, 0.25, 1)
    ]
    
    req = func.HttpRequest(
        method="GET",
        url="/api/analytics/trip-yield",
        headers={"Origin": "https://www.costesla.com"},
        params={"format": "corridors"},
        body=b""
    )
    
    resp = get_trip_yield(req)
    assert resp.status_code == 200
    data = json.loads(resp.get_body().decode("utf-8"))
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2
    
    f1 = data["features"][0]
    assert f1["geometry"]["type"] == "LineString"
    assert f1["geometry"]["coordinates"] == [[-104.82, 38.85], [-104.79, 38.95]]
    assert f1["properties"]["ride_id"] == "INV-1"
    assert f1["properties"]["trip_type"] == "Private"
    assert f1["properties"]["gross"] == 50.0
    assert f1["properties"]["is_estimated"] is False
    assert "start_coords" not in f1["properties"]
    assert "classification" not in f1["properties"]
    
    f2 = data["features"][1]
    assert f2["geometry"]["type"] == "LineString"
    assert f2["properties"]["is_estimated"] is True
