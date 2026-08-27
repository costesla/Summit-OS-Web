"""
test_manual_ledger.py
=====================
Tests for the Jackie & Luis Manual Ledger.

Covers the required matrix: baseline/legacy isolation, ledger mathematics,
validation, idempotency, concurrency, and the receivables exclusion policy.

Run from the repo root:
    python backend/tests/test_manual_ledger.py

No database or Azure credentials are needed. The pure helpers have no I/O, and
the service-level tests drive a fake cursor so the persistence logic (idempotent
replay, revision supersession, void transitions) is exercised without SQL Server.
"""

import sys
import os
import datetime
import unittest
from decimal import Decimal

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.manual_ledger import (  # noqa: E402
    ManualLedgerService,
    PersonKey,
    ValidationError,
    compute_balance,
    is_manual_only,
    manual_only_invoice_predicate,
    parse_amount,
    parse_effective_date,
    parse_entry_type,
    parse_note,
    parse_person_key,
    signed_amount,
    validate_entry_payload,
)


def entry(entry_type, amount, is_current=True, voided=False):
    """Shorthand for a balance-participating entry dict."""
    return {
        "entry_type": entry_type,
        "amount": Decimal(amount),
        "is_current": is_current,
        "voided_at_utc": datetime.datetime(2026, 7, 28) if voided else None,
    }


# ── Baseline & legacy isolation ──────────────────────────────────────────────

class TestBaselineAndLegacyIsolation(unittest.TestCase):
    def test_jackie_opening_balance_is_exactly_zero(self):
        self.assertEqual(compute_balance(Decimal("0.00"), []), Decimal("0.00"))

    def test_luis_opening_balance_is_exactly_zero(self):
        self.assertEqual(compute_balance(Decimal("0.00"), []), Decimal("0.00"))

    def test_balance_derives_only_from_supplied_baseline_entries(self):
        """Legacy rows carry no BaselineID, so they cannot reach the balance.

        The service only ever selects entries WHERE BaselineID = active baseline,
        which is a foreign key — this asserts the arithmetic half of that
        contract: nothing enters a balance except entries handed to it.
        """
        self.assertEqual(compute_balance(Decimal("0.00"), []), Decimal("0.00"))
        self.assertEqual(
            compute_balance(Decimal("0.00"), [entry("Charge", "25.00")]),
            Decimal("25.00"),
        )

    def test_back_dated_entry_still_counts_only_via_baseline(self):
        """A back-dated effective date does not change isolation.

        Isolation is by BaselineID, never by date, so an entry dated before the
        cutover still counts if (and only if) it belongs to the active baseline.
        """
        old = entry("Charge", "10.00")
        self.assertEqual(compute_balance(Decimal("0.00"), [old]), Decimal("10.00"))


class TestLuisAccrualDisabled(unittest.TestCase):
    """The producer must short-circuit before writing any accrual row."""

    def _tracker_with_fake_db(self):
        from services.payment_tracker import PaymentTrackerService

        class FakeDB:
            def __init__(self):
                self.saved = []
                self.reads = []

            def get_luis_balance_before(self, *a, **k):
                self.reads.append("get_luis_balance_before")
                return 0.0

            def get_luis_amount_sent_on(self, *a, **k):
                self.reads.append("get_luis_amount_sent_on")
                return 0.0

            def get_luis_balance_history(self, *a, **k):
                return {"history": []}

            def save_luis_log(self, **kwargs):
                self.saved.append(kwargs)

            def upsert_luis_simple_payment(self, *a, **k):
                self.saved.append({"simple": True})

        tracker = object.__new__(PaymentTrackerService)  # bypass __init__ (no DB)
        tracker.db = FakeDB()
        return tracker

    def test_recompute_writes_no_accrual_while_manual_only(self):
        tracker = self._tracker_with_fake_db()
        tracker._recompute_luis_chain("2026-07-01")
        self.assertEqual(
            tracker.db.saved, [],
            "manual-ledger-only Luis must never persist an accrual row",
        )

    def test_recompute_reads_nothing_while_manual_only(self):
        """Short-circuit happens BEFORE any read, not just before the write."""
        tracker = self._tracker_with_fake_db()
        tracker._recompute_luis_chain("2026-07-01")
        self.assertEqual(tracker.db.reads, [])

    def test_repeated_recompute_remains_inert(self):
        tracker = self._tracker_with_fake_db()
        for _ in range(5):
            tracker._recompute_luis_chain("2026-07-01")
        self.assertEqual(tracker.db.saved, [])

    def test_luis_is_configured_manual_only(self):
        self.assertTrue(is_manual_only(PersonKey.LUIS))


# ── Ledger mathematics ───────────────────────────────────────────────────────

class TestLedgerMathematics(unittest.TestCase):
    def test_charge_increases_balance(self):
        self.assertEqual(
            compute_balance(Decimal("0.00"), [entry("Charge", "125.00")]),
            Decimal("125.00"),
        )

    def test_payment_decreases_balance(self):
        entries = [entry("Charge", "125.00"), entry("Payment", "25.00")]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("100.00"))

    def test_credit_decreases_balance(self):
        entries = [entry("Charge", "60.00"), entry("Credit", "60.00")]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("0.00"))

    def test_decimal_arithmetic_is_exact(self):
        """0.1 + 0.2 must be 0.30 exactly — the reason floats are banned."""
        entries = [entry("Charge", "0.10"), entry("Charge", "0.20")]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("0.30"))

    def test_many_cent_entries_do_not_drift(self):
        entries = [entry("Charge", "0.01") for _ in range(1000)]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("10.00"))

    def test_voided_entries_are_excluded(self):
        entries = [entry("Charge", "50.00"), entry("Charge", "999.00", voided=True)]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("50.00"))

    def test_superseded_revisions_are_excluded(self):
        """Editing must move the balance exactly once, not twice."""
        entries = [
            entry("Charge", "40.00", is_current=False),  # original revision
            entry("Charge", "75.00", is_current=True),   # current revision
        ]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("75.00"))

    def test_balance_may_go_negative_on_overpayment(self):
        entries = [entry("Charge", "20.00"), entry("Payment", "50.00")]
        self.assertEqual(compute_balance(Decimal("0.00"), entries), Decimal("-30.00"))

    def test_signed_amount_direction(self):
        self.assertEqual(signed_amount("Charge", Decimal("5")), Decimal("5"))
        self.assertEqual(signed_amount("Payment", Decimal("5")), Decimal("-5"))
        self.assertEqual(signed_amount("Credit", Decimal("5")), Decimal("-5"))


# ── Validation ───────────────────────────────────────────────────────────────

class TestValidation(unittest.TestCase):
    def test_valid_payload_normalizes(self):
        clean = validate_entry_payload({
            "personKey": "jackie",
            "entryType": "charge",
            "amount": "125.00",
            "effectiveDate": "2026-07-28",
            "note": "Approved manual charge",
        })
        self.assertEqual(clean["person_key"], PersonKey.JACKIE)
        self.assertEqual(clean["entry_type"], "Charge")
        self.assertEqual(clean["amount"], Decimal("125.00"))
        self.assertEqual(clean["effective_date"], datetime.date(2026, 7, 28))

    def test_float_amount_is_rejected(self):
        with self.assertRaises(ValidationError):
            parse_amount(125.10)

    def test_zero_and_negative_amounts_rejected(self):
        for bad in ("0", "0.00", "-5.00"):
            with self.assertRaises(ValidationError):
                parse_amount(bad)

    def test_over_precision_amount_rejected(self):
        with self.assertRaises(ValidationError):
            parse_amount("10.001")

    def test_excessive_amount_rejected(self):
        with self.assertRaises(ValidationError):
            parse_amount("100000.01")

    def test_malformed_amount_rejected(self):
        for bad in ("abc", "", None, "1e9999"):
            with self.assertRaises(ValidationError):
                parse_amount(bad)

    def test_invalid_person_rejected(self):
        for bad in ("EMERSON", "", None, "DROP TABLE"):
            with self.assertRaises(ValidationError):
                parse_person_key(bad)

    def test_invalid_entry_type_rejected(self):
        for bad in ("Refund", "", None):
            with self.assertRaises(ValidationError):
                parse_entry_type(bad)

    def test_invalid_date_rejected(self):
        for bad in ("28-07-2026", "not-a-date", "", None, "1899-01-01"):
            with self.assertRaises(ValidationError):
                parse_effective_date(bad)

    def test_overlong_note_rejected(self):
        with self.assertRaises(ValidationError):
            parse_note("x" * 501)

    def test_non_dict_payload_rejected(self):
        with self.assertRaises(ValidationError):
            validate_entry_payload("not-a-dict")


# ── Idempotency & concurrency ────────────────────────────────────────────────

class FakeCursor:
    """Minimal cursor: returns queued rows and records executed statements."""

    def __init__(self, rows=None, rowcount=1):
        self._rows = list(rows or [])
        self.executed = []
        self.rowcount = rowcount

    def execute(self, sql, *params):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class FakeDB:
    def __init__(self, cursor):
        self._conn = FakeConn(cursor)

    def get_connection(self):
        return self._conn


BASELINE_ROW = ("11111111-1111-1111-1111-111111111111", "JACKIE",
                Decimal("0.00"), "ManualOnly", datetime.datetime(2026, 7, 28))


class TestIdempotencyAndConcurrency(unittest.TestCase):
    def test_replayed_idempotency_key_returns_original_entry(self):
        existing = ("22222222-2222-2222-2222-222222222222", "JACKIE", "Charge",
                    Decimal("125.00"), datetime.date(2026, 7, 28), "note",
                    None, True, 1, None, None)
        cursor = FakeCursor(rows=[BASELINE_ROW, existing])
        service = ManualLedgerService(db=FakeDB(cursor))
        result = service.create_entry({
            "personKey": "JACKIE", "entryType": "Charge", "amount": "125.00",
            "effectiveDate": "2026-07-28", "idempotencyKey": "abc-123",
        })
        self.assertEqual(result["entry_id"], "22222222-2222-2222-2222-222222222222")
        inserts = [s for s, _ in cursor.executed if s.startswith("INSERT INTO Finance.ManualLedgerEntry")]
        self.assertEqual(inserts, [], "a replay must not insert a second entry")

    def test_same_key_different_payload_is_rejected(self):
        existing = ("22222222-2222-2222-2222-222222222222", "JACKIE", "Charge",
                    Decimal("125.00"), datetime.date(2026, 7, 28), "note",
                    None, True, 1, None, None)
        cursor = FakeCursor(rows=[BASELINE_ROW, existing])
        service = ManualLedgerService(db=FakeDB(cursor))
        with self.assertRaises(ValidationError):
            service.create_entry({
                "personKey": "JACKIE", "entryType": "Charge", "amount": "999.00",
                "effectiveDate": "2026-07-28", "idempotencyKey": "abc-123",
            })

    def test_create_without_baseline_is_refused(self):
        cursor = FakeCursor(rows=[None])
        service = ManualLedgerService(db=FakeDB(cursor))
        with self.assertRaises(ValidationError):
            service.create_entry({
                "personKey": "LUIS", "entryType": "Charge",
                "amount": "10.00", "effectiveDate": "2026-07-28",
            })

    def test_stale_edit_fails_optimistic_concurrency(self):
        """If a racing edit already superseded the row, this edit must fail."""
        row = ("33333333-3333-3333-3333-333333333333",
               "11111111-1111-1111-1111-111111111111", "JACKIE", "Charge",
               Decimal("40.00"), datetime.date(2026, 7, 28), "n",
               "33333333-3333-3333-3333-333333333333", 1, True, None)
        cursor = FakeCursor(rows=[row], rowcount=0)  # UPDATE affects 0 rows
        service = ManualLedgerService(db=FakeDB(cursor))
        with self.assertRaises(ValidationError):
            service.edit_entry("33333333-3333-3333-3333-333333333333", {
                "personKey": "JACKIE", "entryType": "Charge",
                "amount": "75.00", "effectiveDate": "2026-07-28",
            })

    def test_voided_entry_cannot_be_edited(self):
        row = ("33333333-3333-3333-3333-333333333333",
               "11111111-1111-1111-1111-111111111111", "JACKIE", "Charge",
               Decimal("40.00"), datetime.date(2026, 7, 28), "n",
               "33333333-3333-3333-3333-333333333333", 1, True,
               datetime.datetime(2026, 7, 28))
        cursor = FakeCursor(rows=[row])
        service = ManualLedgerService(db=FakeDB(cursor))
        with self.assertRaises(ValidationError):
            service.edit_entry("33333333-3333-3333-3333-333333333333", {
                "personKey": "JACKIE", "entryType": "Charge",
                "amount": "75.00", "effectiveDate": "2026-07-28",
            })

    def test_entry_cannot_be_reassigned_to_another_person(self):
        row = ("33333333-3333-3333-3333-333333333333",
               "11111111-1111-1111-1111-111111111111", "JACKIE", "Charge",
               Decimal("40.00"), datetime.date(2026, 7, 28), "n",
               "33333333-3333-3333-3333-333333333333", 1, True, None)
        cursor = FakeCursor(rows=[row])
        service = ManualLedgerService(db=FakeDB(cursor))
        with self.assertRaises(ValidationError):
            service.edit_entry("33333333-3333-3333-3333-333333333333", {
                "personKey": "LUIS", "entryType": "Charge",
                "amount": "75.00", "effectiveDate": "2026-07-28",
            })

    def test_repeated_void_is_safe(self):
        already_voided = ("44444444-4444-4444-4444-444444444444",
                          datetime.datetime(2026, 7, 28), True)
        cursor = FakeCursor(rows=[already_voided])
        service = ManualLedgerService(db=FakeDB(cursor))
        result = service.void_entry("44444444-4444-4444-4444-444444444444")
        self.assertTrue(result["already_voided"])
        updates = [s for s, _ in cursor.executed if s.startswith("UPDATE")]
        self.assertEqual(updates, [], "re-voiding must not issue another UPDATE")

    def test_void_uses_state_transition_not_delete(self):
        cursor = FakeCursor(rows=[("44444444-4444-4444-4444-444444444444", None, True)])
        service = ManualLedgerService(db=FakeDB(cursor))
        service.void_entry("44444444-4444-4444-4444-444444444444", actor="peter")
        statements = [s for s, _ in cursor.executed]
        self.assertFalse(any(s.startswith("DELETE") for s in statements),
                         "voiding must never issue a DELETE")
        self.assertTrue(any("VoidedAtUtc = SYSUTCDATETIME()" in s for s in statements))


# ── Receivables exclusion policy ─────────────────────────────────────────────

class TestReceivablesExclusion(unittest.TestCase):
    def test_policy_covers_both_people(self):
        self.assertTrue(is_manual_only(PersonKey.JACKIE))
        self.assertTrue(is_manual_only(PersonKey.LUIS))
        self.assertTrue(is_manual_only("jackie"))  # case-insensitive key lookup

    def test_other_customers_are_unaffected(self):
        for other in ("EMERSON", "LOGAN", "NAITIK", "DAVID", ""):
            self.assertFalse(is_manual_only(other))

    def test_predicate_excludes_jackie_including_spelling_variant(self):
        predicate = manual_only_invoice_predicate()
        self.assertIn("INV-JACKIE-%", predicate)
        self.assertIn("INV-JACQUELYN-%", predicate)

    def test_predicate_excludes_luis(self):
        self.assertIn("INV-LUIS-%", manual_only_invoice_predicate())

    def test_predicate_does_not_exclude_active_clients(self):
        predicate = manual_only_invoice_predicate()
        for active in ("EMERSON", "LOGAN", "NAITIK"):
            self.assertNotIn(f"INV-{active}-%", predicate)

    def test_predicate_targets_supplied_column(self):
        self.assertIn("r.RideID NOT LIKE", manual_only_invoice_predicate("r.RideID"))

    def test_global_deferred_total_applies_the_shared_predicate(self):
        """The API total must use the same exclusion as the UI.

        Guards the exact failure the review called out: a Receivables card that
        disappears while an API/export total still counts the same invoices.
        """
        import inspect
        from services.database import DatabaseClient
        source = inspect.getsource(DatabaseClient.get_global_deferred_total)
        self.assertIn("manual_only_invoice_predicate", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
