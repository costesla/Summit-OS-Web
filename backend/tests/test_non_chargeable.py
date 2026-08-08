"""
test_non_chargeable.py
======================
Covers the non-chargeable client class added in:
  - backend/services/database.py  (NON_CHARGEABLE_CLIENTS, client_token,
                                   is_non_chargeable)
  - backend/api/bookings.py       (link suppression + terminal status)
  - backend/api/checkout.py       (refuse the upfront-payment flow)

The load-bearing fact these tests pin: the PAYMENT LINK, not the PaymentStatus
column, is the customer-facing surface. The link is minted and emailed well
before any status is written, so a status value alone cannot stop a payment
request reaching someone's inbox.

Run from the repo root:
    python backend/tests/test_non_chargeable.py
    pytest backend/tests/test_non_chargeable.py

No database, Azure or Stripe credentials are needed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.database import (  # noqa: E402
    NON_CHARGEABLE_CLIENTS,
    INACTIVE_CLIENTS,
    PAYMENT_STATUS_NON_CHARGEABLE,
    client_token,
    is_non_chargeable,
    is_non_chargeable_token,
)


class ClientTokenTests(unittest.TestCase):
    """The token must match what build_invoice_id puts in the RideID, because
    get_open_client_invoices parses it back out and payment_tracker matches it
    against bank counterparty strings."""

    def test_first_name_uppercased(self):
        self.assertEqual(client_token("Jackie Heslep"), "JACKIE")

    def test_single_word(self):
        self.assertEqual(client_token("Jackie"), "JACKIE")

    def test_leading_whitespace_does_not_shift_the_token(self):
        self.assertEqual(client_token("   Jackie Heslep  "), "JACKIE")

    def test_empty_and_whitespace_only_are_safe(self):
        # build_invoice_id would IndexError on a whitespace-only name; this must
        # not, because it runs on the booking path for every customer.
        for bad in ("", "   ", None):
            self.assertEqual(client_token(bad), "")

    def test_agrees_with_build_invoice_id(self):
        from services.invoice import build_invoice_id
        rid = build_invoice_id("Jackie Heslep", "Friday, August 07 at 10:00 AM MDT")
        self.assertEqual(rid.split("-")[1], client_token("Jackie Heslep"))


class NonChargeableTests(unittest.TestCase):

    def test_jackie_is_non_chargeable(self):
        self.assertTrue(is_non_chargeable("Jackie Heslep"))

    def test_case_and_surname_do_not_matter(self):
        for variant in ("jackie heslep", "JACKIE HESLEP", "Jackie", "Jackie Berry"):
            self.assertTrue(is_non_chargeable(variant), variant)

    def test_ordinary_client_is_chargeable(self):
        for name in ("Emerson Jean Baptiste", "Daniel Scheu", "George Coon", ""):
            self.assertFalse(is_non_chargeable(name), name)

    def test_empty_name_never_matches(self):
        """A missing name must not accidentally fall into a free-rides class."""
        self.assertFalse(is_non_chargeable(None))
        self.assertFalse(is_non_chargeable("   "))

    def test_status_value_fits_the_column(self):
        # Rides.Rides.PaymentStatus is nvarchar(20).
        self.assertLessEqual(len(PAYMENT_STATUS_NON_CHARGEABLE), 20)

    def test_status_is_not_pending(self):
        """Pending re-enters get_unpaid_trips and the auto-collect loop."""
        self.assertNotEqual(PAYMENT_STATUS_NON_CHARGEABLE, "Pending")

    def test_status_is_not_forgiven(self):
        """Forgiven asserts a debt that existed and was released. A ride that was
        never chargeable never implied collection, so reusing it would record a
        false history."""
        self.assertNotEqual(PAYMENT_STATUS_NON_CHARGEABLE, "Forgiven")


class TokenDoorwayTests(unittest.TestCase):
    """The booking path holds a customer NAME; the nightly pairing holds only a
    RideID. Both resolve non-chargeable through one definition — if they ever
    disagree, the class means different things at write time and at
    reconciliation time."""

    def test_token_matches_directly(self):
        self.assertTrue(is_non_chargeable_token("JACKIE"))

    def test_token_is_case_insensitive(self):
        for t in ("jackie", "Jackie", "JaCkIe"):
            self.assertTrue(is_non_chargeable_token(t), t)

    def test_other_tokens_do_not_match(self):
        for t in ("EMERSON", "DANIEL", "ESMERALDA", "TERRANCE"):
            self.assertFalse(is_non_chargeable_token(t), t)

    def test_empty_token_never_matches(self):
        for t in ("", None, "   "):
            self.assertFalse(is_non_chargeable_token(t))

    def test_rideid_derived_token_resolves(self):
        """This is exactly how the nightly pairing derives it."""
        for rid in ("INV-JACKIE-Friday,J-0332", "INV-JACKIE-Tuesday,-0146"):
            self.assertTrue(is_non_chargeable_token(rid.split("-")[1]), rid)
        self.assertFalse(is_non_chargeable_token("INV-EMERSON-Monday,J-2351".split("-")[1]))

    def test_both_doorways_agree(self):
        """The property that keeps one definition from becoming two."""
        for name in ("Jackie Heslep", "Emerson Jean Baptiste", "Daniel Scheu", "", "  "):
            self.assertEqual(
                is_non_chargeable(name),
                is_non_chargeable_token(client_token(name)),
                name,
            )


class RosterSeparationTests(unittest.TestCase):
    """The two lists must stay distinct concepts even while they overlap."""

    def test_lists_are_separate_objects(self):
        self.assertIsNot(NON_CHARGEABLE_CLIENTS, INACTIVE_CLIENTS)

    def test_non_chargeable_is_not_a_superset_of_inactive(self):
        """A former client is not automatically a current non-chargeable one.
        ESMERALDA/TERRANCE/DIANA stopped riding; they must not silently acquire
        free rides if they ever come back."""
        for token in ("ESMERALDA", "TERRANCE", "DIANA", "ESME"):
            self.assertNotIn(token, NON_CHARGEABLE_CLIENTS, token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
