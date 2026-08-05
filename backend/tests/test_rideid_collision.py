"""
test_rideid_collision.py
========================
Regression tests for the RideID collision fixed in:
  - backend/services/invoice.py  (build_invoice_id, HHMM -> HHMMSS)

A collision needs same client + same weekday token + same processing minute.
save_trip's MERGE then matches the existing RideID and takes the UPDATE branch,
so the second booking silently absorbs the first — no error, no duplicate row,
nothing left in SQL to find. Ten such collisions are recorded in Stripe as one
invoiceId carrying multiple payment links (2026-08-05 audit).

The dominant usage pattern is batch-booking consecutive service dates minutes
apart, and the site books 90 days out — so the same client booking the SAME
WEEKDAY across consecutive weeks, seconds apart, is routine rather than exotic.
That is the case test_same_weekday_consecutive_weeks_do_not_collide pins.

Run from the repo root:
    python backend/tests/test_rideid_collision.py
    pytest backend/tests/test_rideid_collision.py

No database, Azure or Stripe credentials are needed.
"""

import os
import sys
import datetime
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.invoice import build_invoice_id  # noqa: E402


class _FrozenClock(datetime.datetime):
    """datetime.now() pinned, so the test controls the collision window."""
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


def _at(h, m, s):
    _FrozenClock._now = _FrozenClock(2026, 8, 5, h, m, s)
    return _FrozenClock._now


class BuildInvoiceIdCollisionTests(unittest.TestCase):

    # ── the bug ──────────────────────────────────────────────────────────────

    def test_same_weekday_consecutive_weeks_do_not_collide(self):
        """Two REAL bookings, same client, same weekday, submitted 3s apart.

        This is the observed near-miss: Wednesday 08-05 and Wednesday 08-12
        booked in one sitting. Under HHMM these produced the same RideID and the
        MERGE absorbed one into the other.
        """
        with patch("services.invoice.datetime", _FrozenClock):
            _at(5, 55, 10)
            a = build_invoice_id("Emerson Jean Baptiste",
                                 "Wednesday, August 05 at 10:00 AM MDT")
            _at(5, 55, 13)
            b = build_invoice_id("Emerson Jean Baptiste",
                                 "Wednesday, August 12 at 10:00 AM MDT")
        self.assertNotEqual(a, b, "same-minute bookings for the same weekday collided")

    def test_four_rapid_bookings_all_distinct(self):
        """The 08-03 cluster: four submissions inside one minute, one weekday."""
        ids = []
        with patch("services.invoice.datetime", _FrozenClock):
            for sec in (5, 21, 34, 48):
                _at(5, 58, sec)
                ids.append(build_invoice_id("Emerson", "Wednesday, August 05 at 10:00 AM MDT"))
        self.assertEqual(len(set(ids)), 4, f"expected 4 distinct ids, got {ids}")

    # ── behaviour deliberately preserved ─────────────────────────────────────

    def test_same_second_still_merges(self):
        """A double-click is the SAME booking twice; merging is correct.

        Seconds were chosen over a random suffix precisely so this keeps
        collapsing to one row instead of creating a visible duplicate.
        """
        with patch("services.invoice.datetime", _FrozenClock):
            _at(5, 55, 10)
            a = build_invoice_id("Emerson", "Wednesday, August 05 at 10:00 AM MDT")
            b = build_invoice_id("Emerson", "Wednesday, August 05 at 10:00 AM MDT")
        self.assertEqual(a, b, "same-second resubmit should still merge")

    def test_client_token_stays_in_position_1(self):
        """get_open_client_invoices parses split('-')[1]; payment_tracker matches
        that token against bank counterparty strings. Load-bearing."""
        with patch("services.invoice.datetime", _FrozenClock):
            _at(5, 55, 10)
            rid = build_invoice_id("Emerson Jean Baptiste",
                                   "Wednesday, August 05 at 10:00 AM MDT")
        self.assertEqual(rid.split("-")[1], "EMERSON")

    def test_time_segment_is_six_digits(self):
        with patch("services.invoice.datetime", _FrozenClock):
            _at(5, 55, 10)
            rid = build_invoice_id("Emerson", "Wednesday, August 05 at 10:00 AM MDT")
        tail = rid.rsplit("-", 1)[-1]
        self.assertTrue(tail.isdigit() and len(tail) == 6, f"tail was {tail!r}")

    def test_missing_customer_name_still_builds(self):
        with patch("services.invoice.datetime", _FrozenClock):
            _at(5, 55, 10)
            rid = build_invoice_id("", "Wednesday, August 05 at 10:00 AM MDT")
        self.assertEqual(rid.split("-")[1], "CLIENT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
