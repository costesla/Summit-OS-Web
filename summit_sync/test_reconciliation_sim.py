import os
import sys
import unittest
import logging
import datetime
from unittest.mock import MagicMock, patch

# Setup paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lib.reconciliation import ReconciliationEngine

class TestReconciliationSim(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        # Mock environment
        os.environ["TESSIE_VIN"] = "TEST_VIN"
        self.engine = ReconciliationEngine()

    @patch('lib.reconciliation.TessieClient')
    def test_process_trip_future(self, MockTessieClient):
        # Setup trip in the future
        future_time = datetime.datetime.now() + datetime.timedelta(days=1)
        trip = {
            'TripID': 'T-FUTURE',
            'Timestamp_Offer': future_time,
            'Duration_min': 30,
            'Passenger_FirstName': 'Jackie',
            'Notes': 'Future Booking'
        }
        
        mock_cursor = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            self.engine._process_trip(trip, mock_cursor)
            
        self.assertTrue(any("FUTURE_TRIP_SKIPPED" in line for line in log.output))

    @patch('lib.reconciliation.TessieClient')
    def test_process_trip_no_match(self, MockTessieClient):
        # Setup trip in the past
        past_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        trip = {
            'TripID': 'T-PAST-NO-MATCH',
            'Timestamp_Offer': past_time,
            'Duration_min': 30,
            'Passenger_FirstName': 'Jackie',
            'Notes': 'Past Booking'
        }
        
        # Tessie returns no drives in ±4h and ±6h
        mock_tessie = MockTessieClient.return_value
        mock_tessie.get_tagged_drives.return_value = []
        self.engine.tessie = mock_tessie
        
        mock_cursor = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            self.engine._process_trip(trip, mock_cursor)
            
        self.assertTrue(any("NO_MATCH" in line for line in log.output))

    @patch('lib.reconciliation.TessieClient')
    def test_process_trip_low_confidence(self, MockTessieClient):
        # Setup trip in the past
        past_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        trip = {
            'TripID': 'T-PAST-LOW-CONF',
            'Timestamp_Offer': past_time,
            'Duration_min': 30,
            'Passenger_FirstName': 'Jackie',
            'Notes': 'Past Booking',
            'Distance_mi': 10
        }
        
        # Tessie returns drive but ending time and distance are way off (leading to low confidence < 60)
        mock_tessie = MockTessieClient.return_value
        mock_tessie.get_tagged_drives.return_value = [{
            'id': 'DRIVE-LOW-CONF',
            'started_at': past_time.timestamp() - 3600 * 5,
            'ending_time': past_time.timestamp() + 3600 * 5,
            'distance': 500
        }]
        self.engine.tessie = mock_tessie
        
        mock_cursor = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            self.engine._process_trip(trip, mock_cursor)
            
        self.assertTrue(any("LOW_CONFIDENCE_MATCH" in line for line in log.output))

    @patch('lib.reconciliation.TessieClient')
    def test_process_trip_match_success(self, MockTessieClient):
        # Setup trip in the past
        past_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        trip = {
            'TripID': 'T-PAST-MATCH',
            'Timestamp_Offer': past_time,
            'Duration_min': 30,
            'Passenger_FirstName': 'Jackie',
            'Notes': 'Past Booking',
            'Distance_mi': 10
        }
        
        # Perfect matching drive
        mock_tessie = MockTessieClient.return_value
        mock_tessie.get_tagged_drives.return_value = [{
            'id': 'DRIVE-MATCH',
            'started_at': past_time.timestamp(),
            'ending_time': past_time.timestamp() + 1800, # 30 min duration
            'distance': 10
        }]
        self.engine.tessie = mock_tessie
        
        mock_cursor = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            self.engine._process_trip(trip, mock_cursor)
            
        self.assertTrue(any("MATCH" in line for line in log.output))
        self.assertTrue(mock_cursor.execute.called)

    @patch('lib.reconciliation.TessieClient')
    def test_sequence_integrity_rebuild(self, MockTessieClient):
        # Setup mock cursor to return 3 trips on the same day for Jackie
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            # Row format: TripID, Tessie_DriveID, Classification, TripType
            ('TRIP1', 'DRIVE1', 'Jackie trip one', 'Private'),
            ('TRIP2', 'DRIVE2', 'Jackie trip three', 'Private'), # Inconsistent tag!
            ('TRIP3', 'DRIVE3', 'Jackie trip three', 'Private')
        ]
        
        mock_tessie = MockTessieClient.return_value
        mock_tessie.set_drive_tag.return_value = True
        self.engine.tessie = mock_tessie
        
        trip_date = datetime.date.today()
        
        with self.assertLogs(level='INFO') as log:
            self.engine._enforce_sequence_integrity(mock_cursor, 'Jackie', trip_date, 'TEST_VIN')
            
        # We expect a SEQUENCE_REBUILT log because TRIP2 had expected tag 'Jackie trip two' but database had 'Jackie trip three'
        self.assertTrue(any("SEQUENCE_REBUILT" in line for line in log.output))
        self.assertTrue(any("TAG_SUCCESS" in line for line in log.output))
        
        # Verify set_drive_tag was called for the rebuilt sequence
        mock_tessie.set_drive_tag.assert_called_with('TEST_VIN', 'DRIVE2', 'Jackie trip two')

if __name__ == '__main__':
    unittest.main()
