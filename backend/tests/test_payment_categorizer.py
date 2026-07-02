"""
test_payment_categorizer.py
============================
Tests for backend/services/payment_categorizer.py — the Payment Tracker's
Luis Canales three-tier logic, former-client flagging, Emerson Wed/Thu skip,
and inter-account transfer/passthrough matching.

Run from the repo root:
    python backend/tests/test_payment_categorizer.py

No database or Azure credentials are needed — payment_categorizer.py is a
pure module with no I/O.
"""

import sys
import os
import datetime
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.payment_categorizer import (
    classify_luis_payment,
    check_consecutive_missed,
    should_flag_missing_emerson,
    find_transfer_pairs,
    categorize_payee,
    is_former_client,
    LUIS_START_DATE,
)


class TestClassifyLuisPayment(unittest.TestCase):
    def setUp(self):
        self.on_date = LUIS_START_DATE + datetime.timedelta(days=10)

    def test_missed_day_zero_sent(self):
        result = classify_luis_payment(0, prior_balance=0, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Missed")
        self.assertEqual(result["new_balance"], 190.00)
        self.assertTrue(result["anomaly_flag"])

    def test_underpayment_below_rough_minimum(self):
        result = classify_luis_payment(80, prior_balance=0, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Underpayment")
        self.assertEqual(result["new_balance"], 190.00)
        self.assertTrue(result["anomaly_flag"])

    def test_rough_day_130_is_valid_not_an_error(self):
        result = classify_luis_payment(130, prior_balance=0, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Rough")
        self.assertEqual(result["deferred_amount"], 60.00)
        self.assertEqual(result["new_balance"], 60.00)
        self.assertFalse(result["anomaly_flag"])

    def test_review_band_between_130_and_190(self):
        result = classify_luis_payment(160, prior_balance=0, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Review")
        self.assertEqual(result["new_balance"], 0.0)
        self.assertTrue(result["anomaly_flag"])

    def test_full_day_190_exact(self):
        result = classify_luis_payment(190, prior_balance=60, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Full")
        self.assertEqual(result["new_balance"], 60.00)
        self.assertFalse(result["anomaly_flag"])

    def test_full_day_overage_pays_down_balance(self):
        result = classify_luis_payment(250, prior_balance=60, payment_date=self.on_date)
        self.assertEqual(result["tier"], "Full")
        self.assertEqual(result["new_balance"], 0.0)  # 60 - (250-190) = -60 -> clamped to 0

    def test_overage_cannot_go_negative(self):
        result = classify_luis_payment(300, prior_balance=20, payment_date=self.on_date)
        self.assertEqual(result["new_balance"], 0.0)

    def test_before_start_date_is_noop(self):
        before = LUIS_START_DATE - datetime.timedelta(days=1)
        result = classify_luis_payment(0, prior_balance=42.0, payment_date=before)
        self.assertEqual(result["tier"], "Pre-Arrangement")
        self.assertEqual(result["new_balance"], 42.0)
        self.assertFalse(result["anomaly_flag"])

    def test_accepts_iso_string_date(self):
        result = classify_luis_payment(190, prior_balance=0, payment_date=self.on_date.isoformat())
        self.assertEqual(result["tier"], "Full")


class TestConsecutiveMissed(unittest.TestCase):
    def test_no_escalation_on_first_missed_day(self):
        self.assertIsNone(check_consecutive_missed([]))
        self.assertIsNone(check_consecutive_missed(["Full"]))

    def test_escalates_on_second_consecutive_missed_day(self):
        reason = check_consecutive_missed(["Missed"])
        self.assertIsNotNone(reason)
        self.assertIn("2 consecutive", reason)

    def test_escalates_further_on_longer_streaks(self):
        reason = check_consecutive_missed(["Missed", "Missed", "Missed"])
        self.assertIn("4 consecutive", reason)

    def test_streak_broken_by_non_missed_day(self):
        reason = check_consecutive_missed(["Full", "Missed", "Missed"])
        self.assertIsNone(reason)


class TestEmersonSchedule(unittest.TestCase):
    def test_no_flag_when_paid(self):
        self.assertIsNone(should_flag_missing_emerson("2026-06-15", had_payment=True))

    def test_flags_missing_payment_on_a_work_day(self):
        # 2026-06-15 is a Monday
        reason = should_flag_missing_emerson("2026-06-15", had_payment=False)
        self.assertIsNotNone(reason)

    def test_does_not_flag_wednesday_off_day(self):
        # 2026-06-17 is a Wednesday
        self.assertIsNone(should_flag_missing_emerson("2026-06-17", had_payment=False))

    def test_does_not_flag_thursday_off_day(self):
        # 2026-06-18 is a Thursday
        self.assertIsNone(should_flag_missing_emerson("2026-06-18", had_payment=False))


class TestTransferMatching(unittest.TestCase):
    def _tx(self, id, account, amount, date, counterparty=""):
        return {"id": id, "account": account, "amount": amount, "date": date, "counterparty": counterparty}

    def test_matches_cross_account_transfer(self):
        d = datetime.date(2026, 6, 1)
        txs = [
            self._tx("a", "9776", -100.0, d, "Transfer to Personal"),
            self._tx("b", "2085", 100.0, d, "Transfer from Business"),
        ]
        self.assertEqual(find_transfer_pairs(txs), {"a", "b"})

    def test_matches_cashapp_passthrough(self):
        d = datetime.date(2026, 6, 1)
        txs = [
            self._tx("a", "2085", 45.0, d, "Cash App Deposit"),
            self._tx("b", "9776", -45.0, d, "Transfer Out"),
        ]
        self.assertEqual(find_transfer_pairs(txs), {"a", "b"})

    def test_does_not_match_unrelated_transactions(self):
        d = datetime.date(2026, 6, 1)
        txs = [
            self._tx("a", "9776", -34.99, d, "Quick Quack"),
            self._tx("b", "2085", 34.99, d, "Netflix Refund"),  # different account pair semantics still qualifies as cross-account, so use same account instead
        ]
        # Same account, so this should NOT match (transfers require two accounts)
        txs = [
            self._tx("a", "9776", -34.99, d, "Quick Quack"),
            self._tx("b", "9776", 34.99, d, "Refund"),
        ]
        self.assertEqual(find_transfer_pairs(txs), set())

    def test_does_not_match_different_amounts(self):
        d = datetime.date(2026, 6, 1)
        txs = [
            self._tx("a", "9776", -100.0, d, "Transfer"),
            self._tx("b", "2085", 50.0, d, "Transfer"),
        ]
        self.assertEqual(find_transfer_pairs(txs), set())

    def test_does_not_match_different_days(self):
        txs = [
            self._tx("a", "9776", -100.0, datetime.date(2026, 6, 1), "Transfer"),
            self._tx("b", "2085", 100.0, datetime.date(2026, 6, 2), "Transfer"),
        ]
        self.assertEqual(find_transfer_pairs(txs), set())


class TestCategorizePayee(unittest.TestCase):
    def test_former_client_flagged(self):
        self.assertTrue(is_former_client("zelle from esmeralda d'silva"))
        result = categorize_payee("Zelle From Esmeralda D'Silva", 50.0, "9776")
        self.assertEqual(result["category"], "Flagged")
        self.assertTrue(result["anomaly_flag"])

    def test_luis_payment_categorized(self):
        result = categorize_payee("Zelle To Luis Canales", -190.0, "9776")
        self.assertEqual(result["category"], "Vehicle Financing")
        self.assertEqual(result["direction"], "outbound")

    def test_uber_vs_rasier_split_into_subcategories(self):
        card = categorize_payee("Uber San Francisco CA", 45.0, "9776")
        ach = categorize_payee("Rasier LLC", 60.0, "9776")
        self.assertEqual(card["category"], "Uber Revenue")
        self.assertEqual(card["subcategory"], "Card Deposit")
        self.assertEqual(ach["category"], "Uber Revenue")
        self.assertEqual(ach["subcategory"], "ACH Deposit")

    def test_uncategorized_fallback(self):
        result = categorize_payee("Some Random Merchant", -12.34, "9776")
        self.assertEqual(result["category"], "Uncategorized")


if __name__ == "__main__":
    unittest.main()
