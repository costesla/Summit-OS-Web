"""
Rate cards: band lookup, boundary crossing, and cost estimation.

Fixtures use the operator's real E Tyler St card, read off the Tessie app on
2026-08-19: $0.26 midnight-09:00, $0.46 09:00-20:00, $0.29 20:00-midnight.
"""

import datetime
import os
import sys
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.charging_rate_cards import (  # noqa: E402
    bands_for,
    estimate_cost,
    rate_at,
    spans_boundary,
)

TYLER = "Colorado Springs, CO - E Tyler St"


def at(hour, minute=0, day=18):
    return datetime.datetime(2026, 8, day, hour, minute)


class TestBandLookup(unittest.TestCase):
    def test_the_operators_card_is_loaded(self):
        self.assertEqual(len(bands_for(TYLER)), 3)

    def test_rate_at_each_band(self):
        self.assertEqual(rate_at(TYLER, at(0, 1)), 0.26)
        self.assertEqual(rate_at(TYLER, at(8, 59)), 0.26)
        self.assertEqual(rate_at(TYLER, at(9, 0)), 0.46)   # peak starts
        self.assertEqual(rate_at(TYLER, at(19, 59)), 0.46)
        self.assertEqual(rate_at(TYLER, at(20, 0)), 0.29)  # peak ends
        self.assertEqual(rate_at(TYLER, at(23, 59)), 0.29)

    def test_band_edges_are_end_exclusive(self):
        """09:00 belongs to peak, not to the band that ends at 09:00."""
        self.assertNotEqual(rate_at(TYLER, at(9, 0)), rate_at(TYLER, at(8, 59)))

    def test_unknown_station_has_no_card(self):
        self.assertEqual(bands_for("Nowhere, CO"), [])
        self.assertIsNone(rate_at("Nowhere, CO", at(12)))

    def test_containment_match_works(self):
        self.assertTrue(bands_for("Colorado Springs, CO - E Tyler St (Supercharger)"))

    def test_raw_address_form_does_NOT_match(self):
        """Documents a real limitation rather than papering over it.

        "23 East Tyler Street, Colorado Springs" shares no substring with
        "Colorado Springs, CO - E Tyler St" — matching them would need
        abbreviation normalisation (East/E, Street/St). It is not needed on the
        live path: sessions carry coordinates, so classify() supplies the
        registry name before a card is ever looked up. If a raw address does
        reach here, no card is found and no estimate is produced, which is the
        safe direction to fail.
        """
        self.assertEqual(bands_for("23 East Tyler Street, Colorado Springs, CO"), [])


class TestBoundaryCrossing(unittest.TestCase):
    def test_the_real_case_a_27_minute_session_crossing_peak(self):
        """08:45 + 27 min billed $0.3566 against a $0.26 band. Any duration
        heuristic misses this; the band edge is what reveals it."""
        self.assertTrue(spans_boundary(TYLER, at(8, 45), at(9, 12)))

    def test_long_session_inside_one_band_does_not_cross(self):
        self.assertFalse(spans_boundary(TYLER, at(21, 0), at(22, 10)))

    def test_session_wholly_in_peak(self):
        self.assertFalse(spans_boundary(TYLER, at(13, 0), at(13, 45)))

    def test_session_crossing_the_evening_edge(self):
        self.assertTrue(spans_boundary(TYLER, at(19, 40), at(20, 20)))

    def test_session_crossing_midnight_into_the_next_band(self):
        self.assertFalse(  # 23:30 -> 00:30 is 0.29 then 0.26
            spans_boundary(TYLER, at(23, 30), at(23, 50)))
        self.assertTrue(
            spans_boundary(TYLER, at(23, 30), datetime.datetime(2026, 8, 19, 0, 30)))

    def test_missing_end_time_cannot_cross(self):
        self.assertFalse(spans_boundary(TYLER, at(8, 45), None))

    def test_unknown_station_never_crosses(self):
        self.assertFalse(spans_boundary("Nowhere, CO", at(8, 45), at(9, 12)))


class TestCostEstimation(unittest.TestCase):
    def test_single_band_is_rate_times_energy(self):
        est = estimate_cost(TYLER, at(13, 0), at(13, 40), 40)
        self.assertAlmostEqual(est.amount, 18.40, places=2)  # 40 * 0.46
        self.assertFalse(est.spans_boundary)

    def test_off_peak_estimate(self):
        self.assertAlmostEqual(estimate_cost(TYLER, at(5, 0), at(5, 40), 40).amount,
                               10.40, places=2)  # 40 * 0.26

    def test_crossing_session_is_prorated_between_bands(self):
        """08:30-09:30 is half off-peak, half peak: 20*0.26 + 20*0.46."""
        est = estimate_cost(TYLER, at(8, 30), at(9, 30), 40)
        self.assertAlmostEqual(est.amount, 14.40, places=2)
        self.assertTrue(est.spans_boundary)
        self.assertEqual(est.bands_used, (0.26, 0.46))

    def test_estimate_sits_between_the_two_band_prices(self):
        est = estimate_cost(TYLER, at(8, 30), at(9, 30), 40)
        self.assertGreater(est.amount, 40 * 0.26)
        self.assertLess(est.amount, 40 * 0.46)

    def test_no_energy_no_estimate(self):
        self.assertIsNone(estimate_cost(TYLER, at(13), at(14), 0))

    def test_no_card_no_estimate(self):
        self.assertIsNone(estimate_cost("Nowhere, CO", at(13), at(14), 40))

    def test_missing_end_falls_back_to_the_start_band(self):
        est = estimate_cost(TYLER, at(13, 0), None, 40)
        self.assertAlmostEqual(est.amount, 18.40, places=2)

    def test_estimate_is_bounded_by_the_card_and_so_cannot_match_billing(self):
        """An estimate can only ever be the card's own arithmetic.

        Over 45 days the card predicted $651.01 where Tessie billed $708.78 —
        8.9% higher — so an estimate is structurally incapable of reproducing
        billed cost. Pinned here because the whole safety argument rests on
        estimates staying separate from billed money.
        """
        kwh = 40
        est = estimate_cost(TYLER, at(13, 0), at(13, 40), kwh)
        self.assertLessEqual(est.amount, kwh * 0.46)
        self.assertGreaterEqual(est.amount, kwh * 0.26)


if __name__ == "__main__":
    unittest.main()
