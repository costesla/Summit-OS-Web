"""Effective charging rates derived from billed sessions."""

import os
import sys
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.charging_rates import (  # noqa: E402
    MIN_SESSIONS_FOR_HOURLY_RATE,
    invoices_to_sessions,
    summarize_rates,
)


def invoice(epoch, kwh, fees, idle=0.0, rate=None,
            location="Colorado Springs, CO - E Tyler St"):
    """A Tesla charging invoice as Tessie returns it."""
    return {
        "id": int(epoch),
        "started_at": epoch,
        "vin": "5YJ3E1EA1PF000000",
        "location": location,
        "energy_used": kwh,
        "idle_minutes": 0,
        "charging_fees": fees,
        "idle_fees": idle,
        "total_cost": fees + idle,
        "cost_per_kwh": rate if rate is not None else round(fees / kwh, 4),
        "currency": "USD",
    }

TYLER = "Colorado Springs, CO - E Tyler St"


def session(hour, kwh, cost, station=TYLER, date="2026-08-18", end_hour=None):
    end_hour = hour if end_hour is None else end_hour
    return {
        "site_name": station,
        "start_time": f"{date}T{hour:02d}:00:00",
        "end_time": f"{date}T{end_hour:02d}:30:00",
        "energy_added_kwh": kwh,
        "cost": cost,
    }


class TestPeakOffPeakDetection(unittest.TestCase):
    def test_cheap_nights_and_expensive_evenings_are_separated(self):
        sessions = [
            session(2, 40, 12.00), session(3, 40, 12.00),    # $0.30 overnight
            session(18, 40, 20.00), session(19, 40, 20.00),  # $0.50 evening
        ]
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["cheapest_hour"]["rate_per_kwh"], 0.30)
        self.assertEqual(st["priciest_hour"]["rate_per_kwh"], 0.50)
        self.assertAlmostEqual(st["peak_offpeak_spread_per_kwh"], 0.20, places=4)
        self.assertIn(st["cheapest_hour"]["hour"], (2, 3))
        self.assertIn(st["priciest_hour"]["hour"], (18, 19))

    def test_effective_rate_is_energy_weighted_not_a_mean_of_rates(self):
        """A 5 kWh top-up must not outweigh a 60 kWh fill."""
        sessions = [session(2, 5, 5.00), session(3, 60, 18.00)]  # $1.00/kWh, $0.30
        st = summarize_rates(sessions)["stations"][0]
        self.assertAlmostEqual(st["effective_rate_per_kwh"], 23.00 / 65.0, places=4)
        self.assertLess(st["effective_rate_per_kwh"], 0.40)  # a mean would be 0.65

    def test_flat_pricing_reports_no_spread(self):
        sessions = [session(h, 40, 14.00) for h in (2, 3, 14, 15)]
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["peak_offpeak_spread_per_kwh"], 0.0)


class TestMissingCostIsNeverTreatedAsFree(unittest.TestCase):
    def test_zero_cost_sessions_are_excluded_not_averaged_in(self):
        sessions = [session(2, 40, 12.00), session(3, 40, 0.0)]
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["sessions_priced"], 1)
        self.assertEqual(st["sessions_without_cost"], 1)
        self.assertEqual(st["effective_rate_per_kwh"], 0.30)  # not 0.15

    def test_all_costs_missing_says_so_plainly(self):
        out = summarize_rates([session(2, 40, 0.0), session(3, 35, 0.0)])
        self.assertEqual(out["sessions_priced"], 0)
        self.assertEqual(out["stations"][0]["effective_rate_per_kwh"], None)
        self.assertTrue(any("data gap" in c for c in out["caveats"]))

    def test_no_sessions_at_all(self):
        out = summarize_rates([])
        self.assertEqual(out["stations"], [])
        self.assertEqual(out["sessions_priced"], 0)


class TestConfidenceAndCaveats(unittest.TestCase):
    def test_single_observation_is_not_presented_as_an_established_rate(self):
        out = summarize_rates([session(2, 40, 12.00)])
        self.assertFalse(out["stations"][0]["by_hour"][0]["confident"])
        self.assertTrue(any("individual observations" in c for c in out["caveats"]))

    def test_repeated_observations_become_confident(self):
        sessions = [session(2, 40, 12.00) for _ in range(MIN_SESSIONS_FOR_HOURLY_RATE)]
        out = summarize_rates(sessions)
        self.assertTrue(out["stations"][0]["by_hour"][0]["confident"])

    def test_long_sessions_are_flagged_as_possibly_spanning_a_boundary(self):
        out = summarize_rates([session(20, 60, 24.00, end_hour=23)])
        self.assertEqual(out["stations"][0]["spans_boundary_risk"], 1)
        self.assertTrue(any("straddle" in c for c in out["caveats"]))

    def test_confident_hours_outrank_single_observations(self):
        """A lone freak-cheap session must not be reported as the best hour.

        Both $0.40 sessions sit in the SAME hour so that hour clears the
        confidence threshold; hour 11 is seen once and must not win on it.
        """
        sessions = [
            session(2, 40, 16.00), session(2, 40, 16.00),  # $0.40, hour 2, twice
            session(11, 40, 4.00),                          # $0.10, hour 11, once
        ]
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["cheapest_hour"]["hour"], 2)
        self.assertEqual(st["cheapest_hour"]["rate_per_kwh"], 0.40)

    def test_single_observations_still_rank_when_nothing_is_confident(self):
        """With no confident hour, reporting the best available beats silence."""
        sessions = [session(2, 40, 16.00), session(11, 40, 4.00)]
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["cheapest_hour"]["rate_per_kwh"], 0.10)
        self.assertFalse(st["cheapest_hour"]["confident"])


class TestMultipleStations(unittest.TestCase):
    def test_stations_are_reported_separately(self):
        sessions = [
            session(2, 40, 12.00, station=TYLER),
            session(2, 40, 20.00, station="Monument, CO"),
        ]
        out = summarize_rates(sessions)
        self.assertEqual(len(out["stations"]), 2)
        rates = {s["station"]: s["effective_rate_per_kwh"] for s in out["stations"]}
        self.assertEqual(rates[TYLER], 0.30)
        self.assertEqual(rates["Monument, CO"], 0.50)

    def test_unparseable_values_do_not_crash_the_report(self):
        out = summarize_rates([
            {"site_name": TYLER, "start_time": "nonsense",
             "energy_added_kwh": "abc", "cost": None},
            session(2, 40, 12.00),
        ])
        self.assertEqual(out["sessions_priced"], 1)


class TestTeslaInvoices(unittest.TestCase):
    """Invoices are authoritative: cost_per_kwh is what Tesla actually billed."""

    # 2026-08-18 in Mountain Time
    H05 = 1787050800  # ~05:00 MT
    H18 = 1787097600  # ~18:00 MT

    def test_billed_rate_is_used_verbatim_not_recomputed(self):
        """cost/energy would blend in idle fees; the billed rate must win."""
        sessions = invoices_to_sessions([
            invoice(self.H05, 40, 10.40, idle=5.00, rate=0.26),
        ])
        st = summarize_rates(sessions)["stations"][0]
        hour = st["by_hour"][0]
        self.assertEqual(hour["rate_per_kwh"], 0.26)
        self.assertEqual(hour["rate_source"], "tesla_invoice")
        # cost/energy would have read (10.40+5.00)/40 = 0.385
        self.assertNotEqual(hour["rate_per_kwh"], 0.385)

    def test_rate_tiers_are_surfaced(self):
        """The station's observed rate card, e.g. 0.26 / 0.29 / 0.46."""
        sessions = invoices_to_sessions([
            invoice(self.H05, 40, 10.40, rate=0.26),
            invoice(self.H05 + 3600, 40, 11.60, rate=0.29),
            invoice(self.H18, 40, 18.40, rate=0.46),
        ])
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["billed_rate_tiers"], [0.26, 0.29, 0.46])

    def test_idle_fees_are_counted_in_cost_but_reported_separately(self):
        sessions = invoices_to_sessions([invoice(self.H05, 40, 10.40, idle=7.50, rate=0.26)])
        st = summarize_rates(sessions)["stations"][0]
        self.assertEqual(st["total_cost"], 17.90)
        self.assertEqual(st["idle_fees_total"], 7.50)

    def test_start_hour_is_mountain_time_not_utc(self):
        """An evening peak session must not land in the small hours."""
        sessions = invoices_to_sessions([invoice(self.H18, 40, 18.40, rate=0.46)])
        self.assertEqual(summarize_rates(sessions)["stations"][0]["by_hour"][0]["hour"], 18)

    def test_since_epoch_filters_older_invoices(self):
        rows = invoices_to_sessions(
            [invoice(self.H05, 40, 10.40), invoice(self.H05 - 86400 * 400, 40, 10.40)],
            since_epoch=self.H05 - 86400,
        )
        self.assertEqual(len(rows), 1)

    def test_mixed_tiers_within_one_hour_fall_back_to_derivation(self):
        """Two different billed rates in one hour means a boundary sits inside
        it; picking either would be a guess."""
        sessions = invoices_to_sessions([
            invoice(self.H05, 40, 10.40, rate=0.26),
            invoice(self.H05 + 600, 40, 11.60, rate=0.29),
        ])
        hour = summarize_rates(sessions)["stations"][0]["by_hour"][0]
        self.assertEqual(hour["rate_source"], "derived")

    def test_malformed_invoices_are_skipped_not_fatal(self):
        rows = invoices_to_sessions([
            {"location": "X", "energy_used": "abc", "charging_fees": None},
            invoice(self.H05, 40, 10.40, rate=0.26),
        ])
        self.assertEqual(len(rows), 1)

    def test_empty_input(self):
        self.assertEqual(invoices_to_sessions([]), [])
        self.assertEqual(invoices_to_sessions(None), [])


if __name__ == "__main__":
    unittest.main()
