"""
Chart rendering for Summit Intelligence 2.0.

The failure mode these guard against is a chart that looks fine and lies: a
missing day silently closed up so a zero day reads as though it never happened,
a QuickChart URL whose braces and quotes were pasted in raw instead of encoded,
or a range so long the daily axis turns into a smear.
"""

import datetime
import json
import os
import sys
import types
import urllib.parse

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# services.database pulls in pyodbc, which needs the native unixODBC driver.
# None of the chart logic touches the database, so stub the driver rather than
# make these tests depend on an ODBC install.
sys.modules.setdefault("pyodbc", types.ModuleType("pyodbc"))

import pytest

from api import copilot_charts
from api.copilot_charts import (
    MAX_DAILY_POINTS,
    build_adaptive_card,
    build_chart_config,
    build_chart_url,
    collect_series,
    format_value,
)


def _rows(pairs):
    """get_daily_metrics() shape: newest first, absent days simply missing."""
    return [
        {
            "DateStr": date,
            "TotalEarnings": earnings,
            "TotalTips": 0,
            "TripCount": 0,
            "TotalMiles": 0.0,
            "DriveTime_Hours": 0.0,
        }
        for date, earnings in sorted(pairs, reverse=True)
    ]


def test_missing_days_are_plotted_as_zero_not_dropped():
    rows = _rows([("2026-08-10", 120.0), ("2026-08-12", 80.0)])

    labels, values, grouping = collect_series(
        rows,
        datetime.date(2026, 8, 10),
        datetime.date(2026, 8, 12),
        "earnings",
        "auto",
    )

    assert grouping == "day"
    assert labels == ["Aug 10", "Aug 11", "Aug 12"]
    assert values == [120.0, 0.0, 80.0]


def test_series_is_ascending_even_though_rows_arrive_newest_first():
    rows = _rows([("2026-08-01", 10.0), ("2026-08-02", 20.0), ("2026-08-03", 30.0)])
    assert rows[0]["DateStr"] == "2026-08-03"

    _, values, _ = collect_series(
        rows, datetime.date(2026, 8, 1), datetime.date(2026, 8, 3), "earnings", "auto"
    )

    assert values == [10.0, 20.0, 30.0]


def test_rows_outside_the_requested_window_are_ignored():
    rows = _rows([("2026-07-31", 999.0), ("2026-08-01", 10.0), ("2026-08-05", 999.0)])

    labels, values, _ = collect_series(
        rows, datetime.date(2026, 8, 1), datetime.date(2026, 8, 2), "earnings", "auto"
    )

    assert labels == ["Aug 01", "Aug 02"]
    assert values == [10.0, 0.0]


def test_long_ranges_roll_up_to_weeks_so_the_axis_stays_readable():
    start = datetime.date(2026, 6, 1)   # a Monday
    end = start + datetime.timedelta(days=41)
    rows = _rows([
        ((start + datetime.timedelta(days=i)).isoformat(), 10.0)
        for i in range(42)
    ])

    labels, values, grouping = collect_series(rows, start, end, "earnings", "auto")

    assert grouping == "week"
    assert len(labels) == 6
    assert values == [70.0] * 6
    assert labels[0] == "Jun 01–Jun 07"
    assert sum(values) == 420.0


def test_auto_stays_daily_right_up_to_the_rollup_threshold():
    start = datetime.date(2026, 6, 1)
    end = start + datetime.timedelta(days=MAX_DAILY_POINTS - 1)
    rows = _rows([(start.isoformat(), 5.0)])

    _, values, grouping = collect_series(rows, start, end, "earnings", "auto")

    assert grouping == "day"
    assert len(values) == MAX_DAILY_POINTS


def test_explicit_day_grouping_overrides_the_rollup():
    start = datetime.date(2026, 6, 1)
    end = start + datetime.timedelta(days=59)
    rows = _rows([(start.isoformat(), 5.0)])

    _, values, grouping = collect_series(rows, start, end, "earnings", "day")

    assert grouping == "day"
    assert len(values) == 60


def test_partial_first_week_is_labelled_from_the_range_start():
    start = datetime.date(2026, 6, 3)   # a Wednesday
    end = datetime.date(2026, 7, 14)
    rows = _rows([(start.isoformat(), 5.0)])

    labels, _, grouping = collect_series(rows, start, end, "earnings", "week")

    assert grouping == "week"
    assert labels[0] == "Jun 03–Jun 07"


def test_metric_selects_the_right_column():
    rows = [{
        "DateStr": "2026-08-10",
        "TotalEarnings": 100.0,
        "TotalTips": 12.0,
        "TripCount": 7,
        "TotalMiles": 43.5,
        "DriveTime_Hours": 3.25,
    }]
    day = datetime.date(2026, 8, 10)

    assert collect_series(rows, day, day, "tips", "day")[1] == [12.0]
    assert collect_series(rows, day, day, "trips", "day")[1] == [7.0]
    assert collect_series(rows, day, day, "miles", "day")[1] == [43.5]
    assert collect_series(rows, day, day, "hours", "day")[1] == [3.25]


def test_chart_url_encodes_the_config_instead_of_pasting_raw_json():
    config = build_chart_config("bar", "Earnings by day", ["Aug 10"], [120.0], "earnings")

    url = build_chart_url(config)

    # Raw braces/quotes in a query string are what breaks hand-built QuickChart
    # URLs; everything after the '?' must be percent-encoded.
    query = url.split("?", 1)[1]
    assert '{' not in query and '"' not in query and ' ' not in query

    parsed = urllib.parse.parse_qs(query)
    assert json.loads(parsed["chart"][0]) == config

    # The config is Chart.js 4 shaped (scales.y, not scales.yAxes). If the
    # version param stopped applying, QuickChart would fall back to Chart.js 2
    # and quietly render an axis-less chart.
    assert parsed["version"] == ["4"]
    assert "y" in config["options"]["scales"]


def test_single_series_chart_draws_no_legend():
    config = build_chart_config("line", "Trips", ["Aug 10"], [3.0], "trips")
    assert config["options"]["plugins"]["legend"]["display"] is False
    assert len(config["data"]["datasets"]) == 1


def test_value_axis_starts_at_zero():
    config = build_chart_config("bar", "Earnings", ["Aug 10", "Aug 11"], [100.0, 110.0], "earnings")
    assert config["options"]["scales"]["y"]["beginAtZero"] is True


def test_line_and_bar_carry_their_own_mark_styling():
    line = build_chart_config("line", "t", ["a"], [1.0], "earnings")["data"]["datasets"][0]
    bar = build_chart_config("bar", "t", ["a"], [1.0], "earnings")["data"]["datasets"][0]

    assert line["borderWidth"] == 2 and line["pointRadius"] == 4
    assert bar["borderRadius"] == 4 and "pointRadius" not in bar

    # Straight segments: a spline through daily totals bows past the measured
    # values and puts its peak between two days instead of on one.
    assert line["tension"] == 0


def test_format_value_matches_the_metric_unit():
    assert format_value(1234.5, "earnings") == "$1,234.50"
    assert format_value(9, "trips") == "9 trips"
    assert format_value(43.52, "miles") == "43.5 mi"
    assert format_value(3.25, "hours") == "3.25 hrs"


def test_adaptive_card_points_at_the_chart_and_names_its_facts():
    card = build_adaptive_card(
        "https://example.test/chart?c=x",
        "Earnings by day",
        "Aug 08, 2026 – Aug 14, 2026 (Mountain Time)",
        [("Total", "$1,000.00")],
    )

    assert card["type"] == "AdaptiveCard"
    # 1.4, not 1.5: this card is the only reliable way to show a chart inside a
    # Teams message — Teams does not render markdown images in agent messages —
    # and 1.4 is what every current Teams client renders without qualification.
    # Nothing in this card needs a 1.5 feature.
    assert card["version"] == "1.4"

    images = [b for b in card["body"] if b["type"] == "Image"]
    assert len(images) == 1
    assert images[0]["url"] == "https://example.test/chart?c=x"
    assert images[0]["altText"]

    facts = [b for b in card["body"] if b["type"] == "FactSet"][0]
    assert facts["facts"] == [{"title": "Total", "value": "$1,000.00"}]


def test_card_is_json_serializable_for_the_send_message_node():
    config = build_chart_config("bar", "Earnings", ["Aug 10"], [1.0], "earnings")
    card = build_adaptive_card(build_chart_url(config), "Earnings", "range", [("Total", "$1.00")])
    assert json.loads(json.dumps(card)) == card


# ── The HTTP handler ──────────────────────────────────────────────────────────

class MockHttpRequest:
    def __init__(self, method="GET", params=None, body=None):
        self.method = method
        self.params = params or {}
        self.headers = {}
        self._body = body

    def get_json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeDatabaseClient:
    """Records the window it was asked for and replays fixed rows."""
    last_range = None
    rows = []

    def get_daily_metrics(self, start_date, end_date):
        FakeDatabaseClient.last_range = (start_date, end_date)
        return FakeDatabaseClient.rows


@pytest.fixture
def fake_db(monkeypatch):
    FakeDatabaseClient.last_range = None
    FakeDatabaseClient.rows = _rows([("2026-08-10", 120.0), ("2026-08-12", 80.0)])
    monkeypatch.setattr(copilot_charts, "DatabaseClient", FakeDatabaseClient)
    return FakeDatabaseClient


def _call(req):
    return json.loads(copilot_charts.copilot_chart.build().get_user_function()(req).get_body())


def test_handler_returns_url_card_and_values_together(fake_db):
    body = _call(MockHttpRequest(params={
        "metric": "earnings", "start_date": "2026-08-10", "end_date": "2026-08-12",
    }))

    assert body["success"] is True
    assert fake_db.last_range == ("2026-08-10", "2026-08-12")
    assert body["chartUrl"].startswith("https://quickchart.io/chart?")
    assert body["adaptiveCard"]["body"][2]["url"] == body["chartUrl"]
    assert body["chart"]["values"] == [120.0, 0.0, 80.0]
    assert body["chart"]["total"] == 200.0
    assert body["chart"]["peak"] == {"label": "Aug 10", "value": 120.0}
    assert body["chart"]["hasData"] is True


def test_handler_defaults_to_the_last_seven_days(fake_db):
    _call(MockHttpRequest())

    start, end = fake_db.last_range
    span = datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)
    assert span.days == 6


def test_handler_clamps_an_over_long_window(fake_db):
    _call(MockHttpRequest(params={"days": "5000"}))

    start, end = fake_db.last_range
    assert (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days == 89


def test_handler_reads_a_post_body_for_power_automate(fake_db):
    body = _call(MockHttpRequest(
        method="POST",
        body={"metric": "trips", "start_date": "2026-08-10", "end_date": "2026-08-12"},
    ))

    assert body["success"] is True
    assert body["chart"]["metric"] == "trips"
    assert fake_db.last_range == ("2026-08-10", "2026-08-12")


def test_handler_rejects_an_unknown_metric_with_a_usable_message(fake_db):
    body = _call(MockHttpRequest(params={"metric": "profit"}))

    assert body["success"] is False
    assert "earnings" in body["error"]


def test_handler_tells_the_agent_how_to_fix_a_malformed_date(fake_db):
    body = _call(MockHttpRequest(params={"start_date": "08/10/2026", "end_date": "08/12/2026"}))

    assert body["success"] is False
    assert "YYYY-MM-DD" in body["error"]


def test_handler_says_so_plainly_when_the_range_is_empty(fake_db):
    fake_db.rows = []

    body = _call(MockHttpRequest(params={"start_date": "2026-08-10", "end_date": "2026-08-12"}))

    assert body["success"] is True
    assert body["chart"]["hasData"] is False
    assert body["chart"]["peak"] is None
    assert "No earnings recorded" in body["summary"]


def test_pie_and_doughnut_charts_generate_valid_configs():
    for c_type in ("pie", "doughnut"):
        config = build_chart_config(c_type, "Earnings Breakdown", ["Aug 10", "Aug 11"], [100.0, 150.0], "earnings")
        assert config["type"] == c_type
        assert config["options"]["plugins"]["legend"]["display"] is True
        assert config["options"]["plugins"]["legend"]["position"] == "bottom"
        assert len(config["data"]["datasets"][0]["backgroundColor"]) == 2


def test_breakdown_metric_returns_earnings_charging_and_expenses(monkeypatch):
    def fake_summary_metrics(self, start_date, end_date):
        return {
            "gross_earnings": 1000.0,
            "charging": 150.0,
            "expenses": 350.0,
            "uber_earnings": 800.0,
            "private_income": 200.0,
            "uber_tips": 100.0,
        }
    monkeypatch.setattr(copilot_charts.DatabaseClient, "get_summary_metrics_for_range", fake_summary_metrics)

    body = _call(MockHttpRequest(params={"metric": "breakdown", "start_date": "2026-08-01", "end_date": "2026-08-07"}))
    assert body["success"] is True
    assert body["chart"]["chartType"] == "doughnut"
    assert body["chart"]["labels"] == ["Gross Earnings", "Charging Costs", "Other Expenses"]
    assert body["chart"]["values"] == [1000.0, 150.0, 200.0]

    body_rev = _call(MockHttpRequest(params={"metric": "revenue_sources", "start_date": "2026-08-01", "end_date": "2026-08-07"}))
    assert body_rev["success"] is True
    assert body_rev["chart"]["labels"] == ["Uber Earnings", "Private Client Income"]
    assert body_rev["chart"]["values"] == [800.0, 200.0]

    body_tips = _call(MockHttpRequest(params={"metric": "fare_vs_tips", "start_date": "2026-08-01", "end_date": "2026-08-07"}))
    assert body_tips["success"] is True
    assert body_tips["chart"]["labels"] == ["Base Fares", "Tips"]
    assert body_tips["chart"]["values"] == [700.0, 100.0]


def test_top_areas_metric(monkeypatch):
    def fake_area_activity(self, start, end):
        return [
            {"pickup": "5410 N Nevada Ave, Colorado Springs, CO 80918"},
            {"pickup": "5410 N Nevada Ave, Colorado Springs, CO 80918"},
            {"pickup": "777 E Pikes Peak Ave, Colorado Springs, CO 80903"},
        ]
    monkeypatch.setattr(copilot_charts.DatabaseClient, "get_area_activity", fake_area_activity)

    body = _call(MockHttpRequest(params={"metric": "top_areas", "start_date": "2026-08-01", "end_date": "2026-08-07"}))
    assert body["success"] is True
    assert body["chart"]["labels"][0] == "Colorado Springs 80918"
    assert body["chart"]["values"][0] == 2.0


def test_client_balances_metric(monkeypatch):
    def fake_balances(self, include_inactive=False):
        return [
            {"client": "Jackie", "balance": 150.0, "status": "active"},
            {"client": "Emerson", "balance": 75.0, "status": "active"},
        ]
    monkeypatch.setattr(copilot_charts.DatabaseClient, "get_client_balances", fake_balances)

    body = _call(MockHttpRequest(params={"metric": "client_balances"}))
    assert body["success"] is True
    assert body["chart"]["labels"] == ["Jackie", "Emerson"]
    assert body["chart"]["values"] == [150.0, 75.0]



