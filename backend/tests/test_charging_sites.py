"""
Supercharger classification by coordinates.

Fixtures are REAL sessions captured live from /api/copilot/tessie/charges on
2026-08-19, including the exact addresses that defeated the substring rule.
"""

import os
import sys
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.charging_sites import (  # noqa: E402
    MATCH_RADIUS_M,
    UNKNOWN,
    classify,
    distance_m,
)

# (label, lat, lon, expected_site_fragment) — every one of these is a real
# Supercharger the operator actually used.
REAL_SUPERCHARGER_SESSIONS = [
    ("East Tyler Street, Colorado Springs",  38.871098, -104.82248,   "E Tyler St"),
    ("East Tyler Street, Colorado Springs",  38.87102,  -104.82249,   "E Tyler St"),
    ("Cipriani Loop, Monument",              39.0923,   -104.85257,   "Monument"),
    ("Yampa Street, Denver",                 39.81779,  -104.77331,   "Tower Rd"),
    ("Yampa Street, Denver",                 39.81782,  -104.773315,  "Tower Rd"),
    ("Chapel Hills Drive, Colorado Springs", 38.965717, -104.78513,   "Forest Bluffs View"),
]


class TestRealSessions(unittest.TestCase):
    def test_every_real_session_is_identified(self):
        for label, lat, lon, fragment in REAL_SUPERCHARGER_SESSIONS:
            with self.subTest(label):
                m = classify(lat, lon)
                self.assertIs(m.is_supercharger, True, f"{label} should be a Supercharger")
                self.assertIn(fragment, m.site_name)

    def test_matches_are_tight_not_lucky(self):
        """Real matches land within metres; a loose radius would prove nothing."""
        for label, lat, lon, _ in REAL_SUPERCHARGER_SESSIONS:
            with self.subTest(label):
                self.assertLess(classify(lat, lon).distance_m, 50.0)

    def test_the_substring_rule_this_replaced_failed_on_all_of_them(self):
        """Regression witness: the old rule was wrong for every real session."""
        for label, _, _, _ in REAL_SUPERCHARGER_SESSIONS:
            self.assertNotIn("supercharger", label.lower())


class TestNonSuperchargerLocations(unittest.TestCase):
    def test_back_country_without_a_site_is_not_a_supercharger(self):
        """Gunnison's site is still VOTING — charging there is not Supercharging."""
        m = classify(38.5458, -106.9253)
        self.assertIs(m.is_supercharger, False)
        self.assertIsNone(m.site_name)

    def test_open_country_is_not_a_supercharger(self):
        m = classify(38.6000, -105.5000)
        self.assertIs(m.is_supercharger, False)

    def test_just_outside_the_radius_does_not_match(self):
        """~800 m north of E Tyler St: near, but not at, the site."""
        m = classify(38.878300, -104.82248)
        self.assertIs(m.is_supercharger, False)
        self.assertGreater(m.distance_m, MATCH_RADIUS_M)


class TestUnknownIsNeverFalse(unittest.TestCase):
    """A missing fix must stay distinguishable from a genuine non-Supercharger:
    conflating them is exactly how the original defect stayed invisible."""

    def test_missing_coordinates(self):
        self.assertIs(classify(None, None), UNKNOWN)
        self.assertIs(classify(None, -104.82).is_supercharger, None)
        self.assertIs(classify(38.87, None).is_supercharger, None)

    def test_unparseable_coordinates(self):
        for bad in ("", "abc", [], {}):
            self.assertIs(classify(bad, bad).is_supercharger, None)

    def test_null_island_is_a_missing_fix(self):
        self.assertIs(classify(0.0, 0.0).is_supercharger, None)

    def test_out_of_range_coordinates(self):
        self.assertIs(classify(91.0, 0.0).is_supercharger, None)
        self.assertIs(classify(38.87, 181.0).is_supercharger, None)

    def test_string_coordinates_are_accepted(self):
        """pyodbc/JSON round-trips can hand back strings."""
        self.assertIs(classify("38.871098", "-104.82248").is_supercharger, True)


class TestDistance(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(distance_m(38.87, -104.82, 38.87, -104.82), 0.0, places=6)

    def test_known_separation(self):
        """Colorado Springs E Tyler St to Denver Tower Rd, ~110 km apart."""
        d = distance_m(38.871098, -104.82248, 39.81779, -104.77331)
        self.assertGreater(d, 100_000)
        self.assertLess(d, 120_000)

    def test_symmetry(self):
        a = distance_m(38.871098, -104.82248, 39.0923, -104.85257)
        b = distance_m(39.0923, -104.85257, 38.871098, -104.82248)
        self.assertAlmostEqual(a, b, places=6)


if __name__ == "__main__":
    unittest.main()
