import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
import azure.functions as func

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from api.driver import financials_summary
from services.database import DatabaseClient


def test_financials_summary_surfaces_cash_tips_and_uber_on_app():
    """Verify /financials/summary includes cash_tips and uber_on_app in its payload."""
    mock_req = MagicMock(spec=func.HttpRequest)
    mock_req.params = {"date": "2026-09-08"}

    mock_metrics = {
        "uber_earnings": 150.0,
        "uber_on_app": 140.0,
        "cash_tips": 10.0,
        "uber_tips": 25.0,
        "private_income": 80.0,
        "gross_earnings": 230.0,
        "opex_expenses": 30.0,
        "capex_expenses": 0.0,
        "expenses": 30.0,
        "net_profit": 200.0,
    }

    with patch("api.driver.DatabaseClient") as mock_db_cls:
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance
        mock_db_instance.get_summary_metrics_for_range.return_value = mock_metrics
        mock_db_instance.get_global_deferred_total.return_value = 0.0

        resp = financials_summary(mock_req)
        assert resp.status_code == 200

        data = json.loads(resp.get_body().decode("utf-8"))
        assert data["success"] is True
        assert data["date"] == "2026-09-08"

        # Assert cash_tips and uber_on_app are explicitly exposed
        assert "cash_tips" in data
        assert data["cash_tips"] == 10.0
        assert "uber_on_app" in data
        assert data["uber_on_app"] == 140.0
        assert data["private_income"] == 80.0
        assert data["gross_earnings"] == 230.0


def test_get_summary_metrics_query_decoupling():
    """Verify get_summary_metrics_for_range isolates cash tips from private income queries."""
    client = DatabaseClient()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate query returns:
    # 1a (Uber on-app): Driver_Earnings=100.0, Tips=15.0
    # 1b (Cash Tips): 10.0
    # 2  (Private Bookings): 50.0
    # 3  (Private Payments): 0.0
    # 4  (Manual OpEx): 20.0
    # 5  (Charging Sessions): 10.0
    # 6  (Manual CapEx): 0.0
    mock_cursor.fetchone.side_effect = [
        (100.0, 15.0), # 1a
        (10.0,),       # 1b
        (50.0,),       # 2
        (0.0,),        # 3
        (20.0,),       # 4
        (10.0,),       # 5
        (0.0,),        # 6
    ]

    with patch.object(client, "get_connection", return_value=mock_conn):
        result = client.get_summary_metrics_for_range("2026-09-08", "2026-09-08")

        assert result["uber_on_app"] == 100.0
        assert result["cash_tips"] == 10.0
        assert result["uber_earnings"] == 110.0  # 100 + 10
        assert result["private_income"] == 50.0   # decoupled, tips NOT added here
        assert result["gross_earnings"] == 160.0  # 110 + 50
        assert result["net_profit"] == 130.0     # 160 - 30 (opex)

        # Verify SQL queries executed
        executed_sqls = [call[0][0] for call in mock_cursor.execute.call_args_list]

        # Query 1b must capture M-TIP, Uber_OffApp, %Tip%
        query_1b = executed_sqls[1]
        assert "Uber_OffApp" in query_1b or "%Tip%" in query_1b
        assert "M-TIP-%" in query_1b

        # Query 2 (Private) must exclude cash tips and M-TIP-%
        query_2 = executed_sqls[2]
        assert "TripType = 'Private'" in query_2
        assert "RideID NOT LIKE 'M-TIP-%'" in query_2
        assert "Classification NOT LIKE '%Tip%'" in query_2
