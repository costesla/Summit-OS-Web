"""
test_operational_window.py
==========================
Tests for the 4 AM operational-day boundary fix applied in:
  - backend/services/datetime_utils.py  (get_operational_window helper)
  - backend/services/tessie_sync.py      (sync_day uses the helper)
  - backend/services/cloud_watcher.py    (sync_private_bookings_for_date uses the helper)

Run from the repo root:
    python backend/tests/test_operational_window.py

No database or Azure credentials are needed — all SQL logic is mocked.
"""

import sys
import datetime
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path gymnastics: make sure `backend/services` is importable
# ---------------------------------------------------------------------------
import os
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND   = os.path.join(REPO_ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ---------------------------------------------------------------------------
# Helper import — no cloud deps
# ---------------------------------------------------------------------------
from services.datetime_utils import get_operational_window


# ============================================================================
# SECTION 1 — Unit tests for get_operational_window()
# ============================================================================

class TestGetOperationalWindow(unittest.TestCase):

    def test_naive_window_start(self):
        start, end = get_operational_window("2026-06-20")
        self.assertEqual(start, datetime.datetime(2026, 6, 20, 4, 0, 0))

    def test_naive_window_end(self):
        start, end = get_operational_window("2026-06-20")
        self.assertEqual(end, datetime.datetime(2026, 6, 21, 4, 0, 0))

    def test_window_spans_exactly_24h(self):
        start, end = get_operational_window("2026-06-20")
        self.assertEqual(end - start, datetime.timedelta(hours=24))

    def test_window_does_not_include_end(self):
        """The window is [start, end) — end itself should NOT be 'in' the window."""
        start, end = get_operational_window("2026-06-20")
        self.assertTrue(start <= datetime.datetime(2026, 6, 20, 22, 34) < end)   # 22:34 is IN
        self.assertTrue(start <= datetime.datetime(2026, 6, 21, 0, 9) < end)     # 00:09 next day IS IN
        self.assertFalse(datetime.datetime(2026, 6, 21, 4, 0) < end)              # 04:00 next day NOT IN

    def test_dst_aware_window_with_zoneinfo(self):
        """With a ZoneInfo timezone, the window datetimes should carry tzinfo."""
        try:
            from zoneinfo import ZoneInfo
            mdt = ZoneInfo("America/Denver")
        except ImportError:
            self.skipTest("zoneinfo not available")
        start, end = get_operational_window("2026-06-20", tz=mdt)
        self.assertIsNotNone(start.tzinfo)
        self.assertIsNotNone(end.tzinfo)
        self.assertEqual(end - start, datetime.timedelta(hours=24))

    def test_pytz_tz_aware_window(self):
        """With a pytz timezone, the window datetimes should carry tzinfo."""
        try:
            import pytz
            mdt = pytz.timezone("America/Denver")
        except ImportError:
            self.skipTest("pytz not available")
        start, end = get_operational_window("2026-06-20", tz=mdt)
        self.assertIsNotNone(start.tzinfo)
        self.assertIsNotNone(end.tzinfo)

    def test_cross_year_boundary(self):
        """Dec 31 window should end at Jan 1 04:00 of the next year."""
        start, end = get_operational_window("2025-12-31")
        self.assertEqual(start, datetime.datetime(2025, 12, 31, 4, 0, 0))
        self.assertEqual(end,   datetime.datetime(2026,  1,  1, 4, 0, 0))


# ============================================================================
# SECTION 2 — Behavioural tests for sync_private_bookings_for_date
# ============================================================================

def _make_booking(ride_id, timestamp_start, fare=30.0, classification="Jacquelyn Heslep",
                  pickup="Home", dropoff="Airport", is_test=False):
    """Helper: build a booking row tuple matching the SELECT column order."""
    sidecar = '{"quoteType": "single"}'
    return (ride_id, timestamp_start, classification, None, fare, sidecar, is_test, pickup, dropoff)

def _make_tessie_drive(ride_id, timestamp_start, classification="Jacquelyn Heslep",
                       distance_mi=15.0, duration_min=25.0):
    """Helper: build a Tessie drive row tuple matching the SELECT column order."""
    return (
        ride_id, timestamp_start, classification,
        distance_mi, duration_min,
        80.0, 70.0, 4.5, 300.0,
        "Home", "Airport", "Private", None
    )


class TestSyncPrivateBookings(unittest.TestCase):
    """
    Tests for the Jackie billing logic inside sync_private_bookings_for_date.
    We mock:
      - cursor.execute / cursor.fetchall  — to inject synthetic DB rows
      - JackieBillingEngine.classify_invoice — to inspect what was passed
      - db.get_known_client_names         — returns the short-list
    """

    def _run_sync(self, date_str, booking_rows, tessie_rows, classify_return=None):
        """
        Exercise sync_private_bookings_for_date for date_str with the given
        synthetic DB rows.  Returns (logs, classify_calls) where classify_calls
        is the list of kwargs passed to JackieBillingEngine.classify_invoice.
        """
        if classify_return is None:
            classify_return = {
                "fare": 30.0,
                "status": "Deferred",
                "legs_consumed": 1,
                "reason": "one_way",
            }

        logs = []
        classify_calls = []

        # ---------- mock cursor ----------
        cursor = MagicMock()
        fetch_sequence = [booking_rows, tessie_rows]
        fetch_iter = iter(fetch_sequence)
        cursor.fetchall.side_effect = lambda: next(fetch_iter, [])

        # ---------- patch everything that touches Azure/DB at import time ----------
        with patch("services.customer_pricing.JackieBillingEngine") as mock_billing, \
             patch("services.cloud_watcher.DatabaseClient"), \
             patch("services.cloud_watcher.GraphClient"), \
             patch("services.cloud_watcher.UberMatcherService"):

            mock_billing.classify_invoice.side_effect = lambda **kwargs: (
                classify_calls.append(kwargs) or classify_return
            )

            from services.cloud_watcher import CloudWatcherService
            svc = CloudWatcherService.__new__(CloudWatcherService)
            svc.db = MagicMock()
            svc.db.get_known_client_names.return_value = [
                "jackie", "esmeralda", "daniel", "ryan"
            ]

            svc.sync_private_bookings_for_date(date_str, cursor, logs)

        return logs, classify_calls

    # ── REGRESSION: daytime bookings unchanged ──────────────────────────────

    def test_regression_daytime_booking_still_matched(self):
        """
        A Jackie booking at 08:30 on 2026-06-20 (well within the calendar day)
        must still match a Tessie drive at 08:35 on 2026-06-20.
        Outcome: classify_invoice is called once → the billing engine ran.
        """
        b_ts = datetime.datetime(2026, 6, 20, 8, 30)
        d_ts = datetime.datetime(2026, 6, 20, 8, 35)

        booking_rows = [_make_booking("INV-JACKIE-001", b_ts)]
        tessie_rows  = [_make_tessie_drive("TESSIE-9001", d_ts)]

        logs, classify_calls = self._run_sync("2026-06-20", booking_rows, tessie_rows)

        self.assertEqual(len(classify_calls), 1,
            f"Expected 1 billing classification, got {len(classify_calls)}. Logs:\n" + "\n".join(logs))

    def test_regression_daytime_two_bookings_cap_accumulates(self):
        """
        Two daytime Jackie bookings → legs_already_billed_today increments correctly
        (1st booking: 0 legs in, 2nd booking: 1 leg in).
        """
        b1_ts = datetime.datetime(2026, 6, 20, 8, 30)
        b2_ts = datetime.datetime(2026, 6, 20, 13, 0)
        d1_ts = datetime.datetime(2026, 6, 20, 8, 35)
        d2_ts = datetime.datetime(2026, 6, 20, 13, 5)

        booking_rows = [
            _make_booking("INV-JACKIE-001", b1_ts),
            _make_booking("INV-JACKIE-002", b2_ts),
        ]
        tessie_rows = [
            _make_tessie_drive("TESSIE-9001", d1_ts),
            _make_tessie_drive("TESSIE-9002", d2_ts),
        ]

        classify_return_seq = [
            {"fare": 30.0, "status": "Deferred", "legs_consumed": 1, "reason": "one_way"},
            {"fare": 30.0, "status": "Deferred", "legs_consumed": 1, "reason": "one_way"},
        ]
        call_idx = [0]
        classify_calls = []

        with patch("services.customer_pricing.JackieBillingEngine") as mock_billing, \
             patch("services.cloud_watcher.DatabaseClient"), \
             patch("services.cloud_watcher.GraphClient"), \
             patch("services.cloud_watcher.UberMatcherService"):

            def side_effect(**kwargs):
                classify_calls.append(kwargs)
                result = classify_return_seq[call_idx[0]]
                call_idx[0] += 1
                return result

            mock_billing.classify_invoice.side_effect = side_effect

            cursor = MagicMock()
            fetch_iter = iter([booking_rows, tessie_rows])
            cursor.fetchall.side_effect = lambda: next(fetch_iter, [])

            from services.cloud_watcher import CloudWatcherService
            svc = CloudWatcherService.__new__(CloudWatcherService)
            svc.db = MagicMock()
            svc.db.get_known_client_names.return_value = ["jackie"]
            svc.sync_private_bookings_for_date("2026-06-20", cursor, [])

        self.assertEqual(len(classify_calls), 2)
        self.assertEqual(classify_calls[0]["legs_already_billed_today"], 0)
        self.assertEqual(classify_calls[1]["legs_already_billed_today"], 1)

    # ── EXPOSURE: cross-midnight booking captured under 6/20 window ────────

    def test_cross_midnight_booking_captured_in_prior_day_window(self):
        """
        A Jackie booking at 00:15 on 2026-06-21 (inside the 4 AM window of 6/20)
        MUST be captured when syncing '2026-06-20'.

        Before fix: CAST(Timestamp_Start AS DATE) = '2026-06-20' returned zero rows.
        After fix:  the range query includes it → classify_invoice called once.
        """
        b_ts = datetime.datetime(2026, 6, 21, 0, 15)
        d_ts = datetime.datetime(2026, 6, 21, 0, 20)

        booking_rows = [_make_booking("INV-JACKIE-XMN", b_ts)]
        tessie_rows  = [_make_tessie_drive("TESSIE-9010", d_ts)]

        logs, classify_calls = self._run_sync("2026-06-20", booking_rows, tessie_rows)

        self.assertEqual(len(classify_calls), 1,
            "Cross-midnight booking was NOT captured under the 6/20 operational window.\n"
            "Logs:\n" + "\n".join(logs))

    def test_cross_midnight_cap_accumulates_across_midnight(self):
        """
        Booking A at 23:45 6/20 (legs_in=0 → consumes 1 leg)
        Booking B at 00:15 6/21 (legs_in=1 → consumes leg 2)

        Both must be classified in the SAME sync run with an accumulating counter.
        This is the core anti-regression: no silent cap reset at midnight.
        """
        b1_ts = datetime.datetime(2026, 6, 20, 23, 45)
        b2_ts = datetime.datetime(2026, 6, 21, 0, 15)
        d1_ts = datetime.datetime(2026, 6, 20, 23, 50)
        d2_ts = datetime.datetime(2026, 6, 21, 0, 20)

        booking_rows = [
            _make_booking("INV-JACKIE-001", b1_ts),
            _make_booking("INV-JACKIE-002", b2_ts),
        ]
        tessie_rows = [
            _make_tessie_drive("TESSIE-9001", d1_ts),
            _make_tessie_drive("TESSIE-9002", d2_ts),
        ]

        classify_return_seq = [
            {"fare": 30.0, "status": "Deferred", "legs_consumed": 1, "reason": "one_way"},
            {"fare": 30.0, "status": "Deferred", "legs_consumed": 1, "reason": "one_way"},
        ]
        call_idx = [0]
        classify_calls = []

        with patch("services.customer_pricing.JackieBillingEngine") as mock_billing, \
             patch("services.cloud_watcher.DatabaseClient"), \
             patch("services.cloud_watcher.GraphClient"), \
             patch("services.cloud_watcher.UberMatcherService"):

            def side_effect(**kwargs):
                classify_calls.append(kwargs)
                result = classify_return_seq[call_idx[0]]
                call_idx[0] += 1
                return result

            mock_billing.classify_invoice.side_effect = side_effect

            cursor = MagicMock()
            fetch_iter = iter([booking_rows, tessie_rows])
            cursor.fetchall.side_effect = lambda: next(fetch_iter, [])

            from services.cloud_watcher import CloudWatcherService
            svc = CloudWatcherService.__new__(CloudWatcherService)
            svc.db = MagicMock()
            svc.db.get_known_client_names.return_value = ["jackie"]
            svc.sync_private_bookings_for_date("2026-06-20", cursor, [])

        self.assertEqual(len(classify_calls), 2,
            "Both cross-midnight bookings must be classified in one sync run.")
        self.assertEqual(classify_calls[0]["legs_already_billed_today"], 0,
            "First booking must see 0 prior legs")
        self.assertEqual(classify_calls[1]["legs_already_billed_today"], 1,
            "Cross-midnight second booking must see 1 prior leg — cap reset bug still present!")

    # ── INDEPENDENCE: next-day window resets correctly ──────────────────────

    def test_next_day_booking_at_09_00_not_in_6_20_window(self):
        """
        A Jackie booking at 09:00 on 6/21 is AFTER 04:00 — it belongs to 6/21's
        operational window, not 6/20's.  Syncing '2026-06-20' must produce zero
        classify_invoice calls for it.
        """
        b_ts = datetime.datetime(2026, 6, 21, 9, 0)
        d_ts = datetime.datetime(2026, 6, 21, 9, 5)

        booking_rows = [_make_booking("INV-JACKIE-NEXT", b_ts)]
        tessie_rows  = [_make_tessie_drive("TESSIE-9020", d_ts)]

        logs, classify_calls = self._run_sync("2026-06-20", booking_rows, tessie_rows)

        self.assertEqual(len(classify_calls), 0,
            "A 09:00 booking on 6/21 must NOT appear in the 6/20 window.\n"
            "Logs:\n" + "\n".join(logs))

    def test_next_day_sync_runs_independently_with_fresh_cap(self):
        """
        When syncing '2026-06-21' the 09:00 booking IS captured and the cap
        starts at 0 — no carry-over from the prior night.
        """
        b_ts = datetime.datetime(2026, 6, 21, 9, 0)
        d_ts = datetime.datetime(2026, 6, 21, 9, 5)

        booking_rows = [_make_booking("INV-JACKIE-NEXT", b_ts)]
        tessie_rows  = [_make_tessie_drive("TESSIE-9020", d_ts)]

        logs, classify_calls = self._run_sync("2026-06-21", booking_rows, tessie_rows)

        self.assertEqual(len(classify_calls), 1,
            "09:00 booking on 6/21 must be captured when syncing '2026-06-21'.\n"
            "Logs:\n" + "\n".join(logs))
        self.assertEqual(classify_calls[0]["legs_already_billed_today"], 0,
            "6/21 sync must start with 0 prior legs (no carry-over from 6/20)")

    # ── BOUNDARY: exactly at 04:00 goes to the NEXT window ─────────────────

    def test_booking_at_exactly_04_00_belongs_to_next_window(self):
        """
        A booking at exactly 04:00:00 on 6/21 is the START of the 6/21 window,
        NOT the end of 6/20's.  It must produce zero calls when syncing '2026-06-20'.
        """
        b_ts = datetime.datetime(2026, 6, 21, 4, 0, 0)
        d_ts = datetime.datetime(2026, 6, 21, 4, 0, 0)

        booking_rows = [_make_booking("INV-JACKIE-BOUNDARY", b_ts)]
        tessie_rows  = [_make_tessie_drive("TESSIE-9099", d_ts)]

        logs, classify_calls = self._run_sync("2026-06-20", booking_rows, tessie_rows)

        self.assertEqual(len(classify_calls), 0,
            "A booking at 04:00:00 on 6/21 must NOT be in the 6/20 window.\n"
            "Logs:\n" + "\n".join(logs))


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestGetOperationalWindow))
    suite.addTests(loader.loadTestsFromTestCase(TestSyncPrivateBookings))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
