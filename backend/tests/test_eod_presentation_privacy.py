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


def test_html_email_template_parity():
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

    assert "Gross Revenue Allocation" in html
    assert "Lowest-Cost Charging Session" in html
    assert "Best Energy Charge" not in html
    assert "$41.87" in html
    assert "-$41.87" not in html
    assert "Passenger Rating" in html
    assert "Reported Incidents" in html
    assert "5.00 ★" in html
    assert "0" in html
    assert "Lincoln Center Supercharger" in html
    assert "North Cascade Supercharger" in html
    assert "Maverik" in html
    assert "Dairy Queen" in html
    assert "23 East Tyler" not in html
    assert "2727 N Cascade" not in html
    assert "742 Evergreen" not in html
    assert "10440 Towner" not in html
    assert not re.search(r'\b\d{1,5}\s+(?:East|West|North|South|N\b|S\b|E\b|W\b|[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Drive|Dr|Road|Rd|Terrace|Way|Blvd))', html, re.IGNORECASE)
