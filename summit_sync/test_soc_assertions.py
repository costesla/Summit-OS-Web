import unittest
from unittest.mock import MagicMock, patch
import logging
import sys
import os

# Adjust path so we can import from lib
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from database import DatabaseClient

class TestSOCAssertions(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseClient()
        # Mock connection and cursor
        self.db.get_connection = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.db.get_connection.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

    def test_save_trip_valid(self):
        # Valid trip data
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": 10.5,
            "start_soc": 80,
            "end_soc": 75,
            "classification": "Uber_Core"
        }
        # Should not raise any assertion
        self.db.save_trip(trip_data)
        self.mock_cursor.execute.assert_called()

    def test_save_trip_invalid_negative_distance(self):
        # Invalid negative distance
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": -2.5,
            "start_soc": 80,
            "end_soc": 75
        }
        with self.assertRaises(AssertionError) as context:
            self.db.save_trip(trip_data)
        self.assertIn("invalid negative distance", str(context.exception))

    def test_save_trip_invalid_start_soc(self):
        # Invalid start_soc
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": 5.0,
            "start_soc": 105,
            "end_soc": 80
        }
        with self.assertRaises(AssertionError) as context:
            self.db.save_trip(trip_data)
        self.assertIn("invalid start_soc", str(context.exception))

    def test_save_trip_invalid_end_soc(self):
        # Invalid end_soc
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": 5.0,
            "start_soc": 80,
            "end_soc": -5
        }
        with self.assertRaises(AssertionError) as context:
            self.db.save_trip(trip_data)
        self.assertIn("invalid end_soc", str(context.exception))

    @patch('logging.warning')
    def test_save_trip_warning_soc_increase(self, mock_warning):
        # SOC increases over non-negligible distance (>= 0.2 mi)
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": 2.0,
            "start_soc": 70,
            "end_soc": 72
        }
        self.db.save_trip(trip_data)
        # Should call logging.warning with an AUDIT WARNING
        warn_args = [call[0][0] for call in mock_warning.call_args_list]
        self.assertTrue(any("AUDIT WARNING" in arg for arg in warn_args))

    @patch('logging.warning')
    def test_save_trip_no_warning_negligible_distance(self, mock_warning):
        # SOC increases but distance is negligible (< 0.2 mi)
        trip_data = {
            "trip_id": "T12345",
            "tessie_distance_mi": 0.1,
            "start_soc": 70,
            "end_soc": 72
        }
        self.db.save_trip(trip_data)
        # Should NOT trigger AUDIT WARNING
        warn_args = [call[0][0] for call in mock_warning.call_args_list]
        self.assertFalse(any("AUDIT WARNING" in arg for arg in warn_args))

    def test_save_charge_valid(self):
        # Valid charge data
        charge_data = {
            "session_id": "C999",
            "start_soc": 20,
            "end_soc": 80,
            "energy_added": 45.5
        }
        # Should not raise any assertion
        self.db.save_charge(charge_data)
        self.mock_cursor.execute.assert_called()

    def test_save_charge_invalid_soc_decrease(self):
        # SOC decreases in charging session
        charge_data = {
            "session_id": "C999",
            "start_soc": 80,
            "end_soc": 70,
            "energy_added": 10.0
        }
        with self.assertRaises(AssertionError) as context:
            self.db.save_charge(charge_data)
        self.assertIn("invalid negative SOC delta", str(context.exception))

    def test_save_charge_invalid_negative_energy(self):
        # Negative energy added
        charge_data = {
            "session_id": "C999",
            "start_soc": 20,
            "end_soc": 80,
            "energy_added": -5.0
        }
        with self.assertRaises(AssertionError) as context:
            self.db.save_charge(charge_data)
        self.assertIn("negative energy delta", str(context.exception))

if __name__ == "__main__":
    unittest.main()
