import os
import sys
import re
import io
import tempfile
import pytest

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.location_normalizer import clean_location
from services.pdf_generator import ExecutivePDFGenerator
from services.eod_engine_production import ProductionEODEngine


def test_location_normalizer_superchargers():
    assert clean_location("23 East Tyler Street, Colorado Springs, CO", "charging") == "Lincoln Center Supercharger"
    assert clean_location("2727 N Cascade Ave, Colorado Springs, CO", "charging") == "North Cascade Supercharger"
    assert clean_location("Lincoln Center Supercharger", "charging") == "Lincoln Center Supercharger"
    assert clean_location("Supercharger - North Cascade", "charging") == "North Cascade Supercharger"


def test_location_normalizer_merchant_names():
    assert clean_location("Maverik - Store #412", "fastfood") == "Maverik"
    assert clean_location("Dairy Queen Grill & Chill", "fastfood") == "Dairy Queen"
    assert clean_location("Rocky Mountain Calva - Oil Filter", "capital_maintenance") == "Rocky Mountain Calva"


def test_location_normalizer_removes_street_numbers_and_personal_names():
    # House numbers with street names should collapse to approved municipality
    assert clean_location("742 Evergreen Terrace, Colorado Springs, CO 80903", "trip") == "Colorado Springs, CO"
    assert clean_location("10440 Towner Ave, Peyton, CO 80831", "trip") == "Peyton, CO"
    assert clean_location("Apt 4B, 123 Elm St, Monument, CO", "trip") == "Monument, CO"

    # Raw street names without numbers should NOT leak raw street names; they generalize
    assert clean_location("Towner Ave", "trip") in ["Regional Operations", "Colorado Springs, CO"]

    # Arbitrary strings with names/coordinates
    assert clean_location("John Doe, 38.8339, -104.8214", "trip") == "Regional Operations"
    assert clean_location("", "trip") == "Regional Operations"
    assert clean_location(None, "trip") == "Regional Operations"


def test_financial_reconciliation():
    gross = 172.54
    opex = 41.87
    net = round(gross - opex, 2)
    assert net == 130.67
    margin = round((net / gross) * 100, 1)
    assert margin == 75.7

    # Positive representation
    assert f"${opex:,.2f}" == "$41.87"
    assert f"-${opex:,.2f}" != "$41.87"


def test_incident_and_rating_authority_fallback():
    # When rating and incidents are NOT provided, must display 'Not available', never falsely infer 0 or 5.00
    data_missing = {
        "report_date": "2026-09-06",
        "weekday": "Sunday",
        "formatted_date": "Sunday, September 06, 2026",
        "gross_revenue": 100.0,
        "total_expenses": 20.0,
        "net_profit": 80.0,
        "net_margin_pct": 80.0,
        "trip_count": 5,
        "avg_rev_per_trip": 20.0,
        "uber_revenue": 100.0,
        "uber_mix_pct": 100.0,
        "private_revenue": 0.0,
        "private_mix_pct": 0.0,
        "passenger_rating": None,
        "reported_incidents": None,
        "executive_summary_escaped": "Test summary",
        "operational_highlights_escaped": "Test highlights",
        "items_attention_escaped": "N/A",
        "outlook_escaped": "Test outlook"
    }

    engine = ProductionEODEngine(template_path=os.path.join(os.path.dirname(__file__), '..', 'templates', 'eod_email_template.html'))
    html = engine.render_production_html(data_missing, "ID", "HASH")
    assert "Not available" in html
    assert "Confidential — Transmitted only to recipients explicitly authorized through the COS Tesla LLC owner dispatch gate." in html

    try:
        import pypdf
        pdf_gen = ExecutivePDFGenerator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            pdf_gen.generate_daily_pdf(data_missing, "HASH", tmp_path)
            reader = pypdf.PdfReader(tmp_path)
            text = reader.pages[0].extract_text()
            assert "Not available" in text
            assert "Confidential — Transmitted only to recipients explicitly authorized through the COS Tesla LLC owner dispatch gate." in text
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except ImportError:
        pass


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "Not available"),
        (0, "0"),
        ("0", "0"),
        (1, "1"),
        ("", "Not available"),
        ("   ", "Not available"),
    ],
)
def test_reported_incidents_preserves_authoritative_zero(value, expected):
    """Verify that numeric 0 is never coerced to falsy 'Not available'."""
    data = {
        "report_date": "2026-09-06",
        "weekday": "Sunday",
        "formatted_date": "Sunday, September 06, 2026",
        "gross_revenue": 100.0,
        "total_expenses": 20.0,
        "net_profit": 80.0,
        "net_margin_pct": 80.0,
        "trip_count": 5,
        "avg_rev_per_trip": 20.0,
        "uber_revenue": 100.0,
        "uber_mix_pct": 100.0,
        "private_revenue": 0.0,
        "private_mix_pct": 0.0,
        "passenger_rating": value,
        "reported_incidents": value,
        "executive_summary_escaped": "Test summary",
        "operational_highlights_escaped": "Test highlights",
        "items_attention_escaped": "N/A",
        "outlook_escaped": "Test outlook"
    }

    engine = ProductionEODEngine(template_path=os.path.join(os.path.dirname(__file__), '..', 'templates', 'eod_email_template.html'))
    html = engine.render_production_html(data, "ID", "HASH")
    assert expected in html

    try:
        import pypdf
        pdf_gen = ExecutivePDFGenerator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            pdf_gen.generate_daily_pdf(data, "HASH", tmp_path)
            reader = pypdf.PdfReader(tmp_path)
            text = reader.pages[0].extract_text()
            assert expected in text
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except ImportError:
        pass


def test_pdf_generation_single_page_and_privacy():
    try:
        import pypdf
    except ImportError:
        pytest.skip("pypdf not installed in test environment")

    data = {
        "report_date": "2026-09-06",
        "weekday": "Sunday",
        "formatted_date": "Sunday, September 06, 2026",
        "gross_revenue": 172.54,
        "total_expenses": 41.87,
        "net_profit": 130.67,
        "net_margin_pct": 75.7,
        "trip_count": 12,
        "avg_rev_per_trip": 14.38,
        "uber_revenue": 172.54,
        "uber_mix_pct": 100.0,
        "private_revenue": 0.0,
        "private_mix_pct": 0.0,
        "passenger_rating": "5.00 ★",
        "reported_incidents": "0",
        "executive_summary": "Daily operations achieved $172.54 gross revenue across 12 completed trips with 75.7% operating margin.",
        "operational_highlights": "Active driver deployment in Colorado Springs and Peyton corridors with 100% vehicle availability.",
        "items_attention": "N/A",
        "outlook": "Operating expenses totaled $41.87 led by Charging ($30.82), yielding $130.67 net operating profit."
    }

    expenses_data = {
        "charging": [
            {"timestamp": "2026-09-06T08:15:00", "note": "23 East Tyler Street, Colorado Springs", "amount": 11.25},
            {"timestamp": "2026-09-06T14:10:00", "note": "2727 N Cascade Ave, Colorado Springs", "amount": 11.17},
            {"timestamp": "2026-09-06T19:30:00", "note": "2727 N Cascade Ave, Colorado Springs", "amount": 8.40}
        ],
        "fastfood": [
            {"timestamp": "2026-09-06T12:30:00", "note": "Maverik - Fuel & Snacks", "amount": 3.49},
            {"timestamp": "2026-09-06T17:45:00", "note": "Dairy Queen", "amount": 7.56}
        ],
        "capital_maintenance": [
            {"timestamp": "2026-09-06T10:00:00", "note": "Rocky Mountain Calva", "amount": 17.09}
        ]
    }

    completed_trips = [
        {"type": "Uber", "driver_earnings": 28.50, "pickup_location": "742 Evergreen Terrace, Colorado Springs, CO", "dropoff_location": "10440 Towner Ave, Peyton, CO"}
    ]

    pdf_gen = ExecutivePDFGenerator()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_pdf_path = tmp.name

    try:
        pdf_gen.generate_daily_pdf(
            data=data,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            output_path=tmp_pdf_path,
            expenses_data=expenses_data,
            completed_trips=completed_trips,
            is_synthetic=False
        )

        assert os.path.exists(tmp_pdf_path)
        reader = pypdf.PdfReader(tmp_pdf_path)

        # Strictly 1 page
        assert len(reader.pages) == 1, f"Expected 1 page, got {len(reader.pages)}"

        text = reader.pages[0].extract_text()

        # Labels & Headers
        assert "GROSS REVENUE ALLOCATION" in text
        assert "Lowest-Cost Charging Session" in text
        assert "Best Energy Charge" not in text
        assert "Passenger Rating" in text
        assert "Reported Incidents" in text
        assert "CapEx / Maintenance Tracking" in text
        assert "$17.09" in text

        # Positive expenses
        assert "$41.87" in text
        assert "-$41.87" not in text

        # Location Aliases
        assert "Lincoln Center Supercharger" in text
        assert "North Cascade Supercharger" in text
        assert "Maverik" in text
        assert "Dairy Queen" in text

        # Privacy checks: No street numbers or coordinates
        assert "23 East Tyler" not in text
        assert "2727 N Cascade" not in text
        assert "742 Evergreen" not in text
        assert "10440 Towner" not in text

        # Ensure no street address patterns (number followed by cardinal direction or street suffix)
        assert not re.search(r'\b\d{1,5}\s+(?:East|West|North|South|N\b|S\b|E\b|W\b|[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Drive|Dr|Road|Rd|Terrace|Way|Blvd))', text, re.IGNORECASE)

    finally:
        if os.path.exists(tmp_pdf_path):
            try:
                os.remove(tmp_pdf_path)
            except OSError:
                pass


def test_html_and_pdf_parity():
    """Explicitly verifies 14 key points of parity between HTML and PDF outputs."""
    try:
        import pypdf
    except ImportError:
        pytest.skip("pypdf not installed")

    data = {
        "report_date": "2026-09-06",
        "weekday": "Sunday",
        "formatted_date": "Sunday, September 06, 2026",
        "gross_revenue": 172.54,
        "total_expenses": 41.87,
        "net_profit": 130.67,
        "net_margin_pct": 75.7,
        "trip_count": 12,
        "avg_rev_per_trip": 14.38,
        "uber_revenue": 172.54,
        "uber_mix_pct": 100.0,
        "private_revenue": 0.0,
        "private_mix_pct": 0.0,
        "passenger_rating": "5.00 ★",
        "reported_incidents": "0",
        "executive_summary_escaped": "Daily operations achieved $172.54 gross revenue across 12 completed trips with 75.7% operating margin.",
        "operational_highlights_escaped": "Active driver deployment in Colorado Springs and Peyton corridors with 100% vehicle availability.",
        "items_attention_escaped": "N/A",
        "outlook_escaped": "Operating expenses totaled $41.87 led by Charging ($30.82), yielding $130.67 net operating profit."
    }

    expenses_data = {
        "charging": [
            {"timestamp": "2026-09-06T08:15:00", "note": "23 East Tyler Street, Colorado Springs", "amount": 11.25},
            {"timestamp": "2026-09-06T14:10:00", "note": "2727 N Cascade Ave, Colorado Springs", "amount": 11.17},
            {"timestamp": "2026-09-06T19:30:00", "note": "2727 N Cascade Ave, Colorado Springs", "amount": 8.40}
        ],
        "fastfood": [
            {"timestamp": "2026-09-06T12:30:00", "note": "Maverik - Fuel & Snacks", "amount": 3.49},
            {"timestamp": "2026-09-06T17:45:00", "note": "Dairy Queen", "amount": 7.56}
        ],
        "capital_maintenance": [
            {"timestamp": "2026-09-06T10:00:00", "note": "Rocky Mountain Calva", "amount": 17.09}
        ]
    }

    completed_trips = [
        {"type": "Uber", "driver_earnings": 28.50, "pickup_location": "742 Evergreen Terrace, Colorado Springs, CO", "dropoff_location": "10440 Towner Ave, Peyton, CO"}
    ]

    engine = ProductionEODEngine(template_path=os.path.join(os.path.dirname(__file__), '..', 'templates', 'eod_email_template.html'))
    html = engine.render_production_html(
        data=data,
        report_id="COSTESLA-EOD-20260906-v1",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        expenses_data=expenses_data,
        completed_trips=completed_trips
    )

    pdf_gen = ExecutivePDFGenerator()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_pdf_path = tmp.name

    try:
        pdf_gen.generate_daily_pdf(
            data=data,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            output_path=tmp_pdf_path,
            expenses_data=expenses_data,
            completed_trips=completed_trips,
            is_synthetic=False
        )
        reader = pypdf.PdfReader(tmp_pdf_path)
        pdf_text = reader.pages[0].extract_text()

        # 14 Key Points of Parity:
        parity_checkpoints = [
            ("1. Report Date", "2026-09-06", "September 06, 2026"),
            ("2. Gross Revenue", "$172.54", "$172.54"),
            ("3. Trip Count", "12", "12"),
            ("4. Avg Rev / Trip", "$14.38", "$14.38"),
            ("5. Charging Total", "$30.82", "$30.82"),
            ("6. Meals Total", "$11.05", "$11.05"),
            ("7. Total OpEx", "$41.87", "$41.87"),
            ("8. Net Operating Profit", "$130.67", "$130.67"),
            ("9. Operating Margin", "75.7%", "75.7%"),
            ("10. CapEx Servicing", "$17.09", "$17.09"),
            ("11. Lowest-Cost Session Label", "Lowest-Cost Charging Session", "Lowest-Cost Charging Session"),
            ("12. Passenger Rating", "5.00 ★", "5.00 ★"),
            ("13. Incident Count", "0", "0"),
            ("14. Supercharger Alias", "Lincoln Center Supercharger", "Lincoln Center Supercharger"),
        ]

        for desc, html_needle, pdf_needle in parity_checkpoints:
            assert html_needle in html, f"HTML missing {desc}: {html_needle}"
            assert pdf_needle in pdf_text, f"PDF missing {desc}: {pdf_needle}"

        # Parity on negative exclusions
        for excluded in ["-$41.87", "Best Energy Charge", "23 East Tyler", "2727 North Cascade"]:
            assert excluded not in html, f"HTML illegally contains {excluded}"
            assert excluded not in pdf_text, f"PDF illegally contains {excluded}"

    finally:
        if os.path.exists(tmp_pdf_path):
            os.remove(tmp_pdf_path)


def test_graph_recipient_deduplication():
    """Verify case-insensitive deduplication across To and CC recipients."""
    from unittest.mock import MagicMock, patch
    from services.graph import GraphClient

    # Mock GraphClient init
    with patch.dict(os.environ, {
        "OAUTH_TENANT_ID": "fake-tenant",
        "OAUTH_CLIENT_ID": "fake-client",
        "OAUTH_CLIENT_SECRET": "fake-secret"
    }):
        graph = GraphClient()
        graph._get_token = MagicMock(return_value="fake-token")

        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.status_code = 202

            # Test 1: Peter in both To and CC with mixed cases and whitespace
            to_input = [" peter.teehan@costesla.com ", "PETER.TEEHAN@COSTESLA.COM", "luis9189@gmail.com", ""]
            cc_input = ["peter.teehan@costesla.com", "LUIS9189@GMAIL.COM", " thornbrerry.brian@gmail.com "]

            graph.send_partner_eod_email(
                to_recipients=to_input,
                cc_recipients=cc_input,
                subject="Test Subject",
                body_html="<p>Test</p>"
            )

            assert mock_post.called
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            message = payload["message"]

            to_addresses = [t["emailAddress"]["address"] for t in message["toRecipients"]]
            cc_addresses = [c["emailAddress"]["address"] for c in message["ccRecipients"]]

            # Assert To deduplication
            assert to_addresses == ["peter.teehan@costesla.com", "luis9189@gmail.com"]

            # Assert CC excludes any address present in To, and deduplicates
            assert cc_addresses == ["thornbrerry.brian@gmail.com"]
            assert "peter.teehan@costesla.com" not in cc_addresses
            assert "luis9189@gmail.com" not in cc_addresses


def test_production_content_does_not_hardcode_metrics_or_named_recipients():
    """Verify production templates and generators do not hardcode metrics or restricted recipient names."""
    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    template_path = os.path.join(backend_dir, "templates", "eod_email_template.html")
    pdf_gen_path = os.path.join(backend_dir, "services", "pdf_generator.py")

    with open(template_path, "r", encoding="utf-8") as f:
        html_src = f.read()
    with open(pdf_gen_path, "r", encoding="utf-8") as f:
        pdf_src = f.read()

    # Must NOT contain hardcoded operational metrics
    assert "Passenger Rating: 5.00" not in html_src
    assert "Reported Incidents: 0" not in html_src
    assert "Passenger Rating: 5.00" not in pdf_src
    assert "Reported Incidents: 0" not in pdf_src

    # Must NOT contain old named recipients
    assert "Luis Canales & Peter Teehan" not in html_src
    assert "Luis Canales & Peter Teehan" not in pdf_src
    assert "Authorized Leadership" not in html_src
    assert "Authorized Leadership" not in pdf_src

    # Must contain recipient-neutral confidentiality notice
    expected_notice = "Confidential — Transmitted only to recipients explicitly authorized through the COS Tesla LLC owner dispatch gate."
    assert expected_notice in html_src
    assert expected_notice in pdf_src


def test_public_api_response_suppresses_internal_paths_and_cleans_temp():
    """Verify tools_partner_eod_report suppresses internal paths and cleans temporary directories."""
    import json
    import shutil
    from unittest.mock import MagicMock, patch
    import azure.functions as func
    from api.driver import tools_partner_eod_report

    body = json.dumps({
        "date": "2026-09-06",
        "recipients": ["peter.teehan@costesla.com"],
        "cc_recipient": "peter.teehan@costesla.com"
    }).encode("utf-8")
    req = func.HttpRequest(
        method="POST",
        url="/api/tools/partner-eod-report",
        body=body
    )

    with patch("api.driver.DatabaseClient") as mock_db, \
         patch("services.graph.GraphClient") as mock_graph, \
         patch("shutil.rmtree", wraps=shutil.rmtree) as spy_rmtree:

        mock_db.return_value.get_summary_metrics_for_range.return_value = {
            "gross_earnings": 100.0, "uber_earnings": 100.0, "uber_tips": 0.0, "private_income": 0.0,
            "opex_expenses": 20.0, "capex_expenses": 0.0, "net_profit": 80.0, "profit_margin": 80.0,
            "passenger_rating": 5.0, "reported_incidents": 0
        }
        mock_db.return_value.get_expenses_by_date.return_value = {"charging": [], "fastfood": [], "capital_maintenance": []}
        mock_db.return_value.get_trips_by_date.return_value = []
        mock_graph.return_value.send_partner_eod_email.return_value = True

        resp = tools_partner_eod_report(req)
        assert resp.status_code == 200
        data = json.loads(resp.get_body().decode("utf-8"))

        # Internal path suppression
        assert "saved_dir" not in data
        assert "pdf_path" not in data
        assert data["success"] is True
        assert data["status"] == "DELIVERED"

        # Temporary cleanup verified
        assert spy_rmtree.called


def test_api_route_recipient_deduplication_and_order():
    """Verify route-level To/CC deduplication and deterministic order."""
    import json
    from unittest.mock import MagicMock, patch
    import azure.functions as func
    from api.driver import tools_partner_eod_report

    body = json.dumps({
        "date": "2026-09-06",
        "recipients": [" peter.teehan@costesla.com ", "PETER.TEEHAN@COSTESLA.COM", "luis9189@gmail.com"],
        "cc_recipient": "peter.teehan@costesla.com"
    }).encode("utf-8")
    req = func.HttpRequest(
        method="POST",
        url="/api/tools/partner-eod-report",
        body=body
    )

    with patch("api.driver.DatabaseClient") as mock_db, \
         patch("services.graph.GraphClient") as mock_graph:

        mock_db.return_value.get_summary_metrics_for_range.return_value = {
            "gross_earnings": 100.0, "uber_earnings": 100.0, "uber_tips": 0.0, "private_income": 0.0,
            "opex_expenses": 20.0, "capex_expenses": 0.0, "net_profit": 80.0, "profit_margin": 80.0,
            "passenger_rating": "5.00 ★", "reported_incidents": "0"
        }
        mock_db.return_value.get_expenses_by_date.return_value = {"charging": [], "fastfood": [], "capital_maintenance": []}
        mock_db.return_value.get_trips_by_date.return_value = []

        resp = tools_partner_eod_report(req)
        assert resp.status_code == 200

        # Verify call to send_partner_eod_email received deduplicated, order-preserved lists
        mock_graph.return_value.send_partner_eod_email.assert_called_once()
        call_kwargs = mock_graph.return_value.send_partner_eod_email.call_args[1]
        assert call_kwargs["to_recipients"] == ["peter.teehan@costesla.com", "luis9189@gmail.com"]
        assert call_kwargs["cc_recipients"] == []  # Peter already in To, excluded from CC
