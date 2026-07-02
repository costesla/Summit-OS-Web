"""Payment Tracker orchestration.

Classifies bank transactions, maintains the Luis Canales running balance,
checks recurring obligations, and produces the daily scorecard.

Source-agnostic: sync_day() takes an already-fetched batch of transactions,
so the same logic serves both the local Teller-MCP nightly job
(scripts/sync_payments_from_teller.py) and the cloud on-demand
`POST /financials/payments/sync` route (which pulls via the existing
BankingClient).
"""

import logging
import datetime

from .database import DatabaseClient
from .datetime_utils import get_operational_window
from .payment_categorizer import (
    BUSINESS_ACCOUNT,
    PERSONAL_ACCOUNT,
    EMERSON_KEYWORD,
    categorize_payee,
    classify_luis_payment,
    check_consecutive_missed,
    should_flag_missing_emerson,
    find_transfer_pairs,
)

DAILY_TARGETS = {
    "gross_earnings": 300.00,
    "supercharging": 25.00,
    "food_dining": 20.00,
}

REVENUE_CATEGORIES = (
    "Uber Revenue", "Booking Revenue", "Private Client Revenue", "Tip/Fare",
)


class PaymentTrackerService:
    def __init__(self):
        self.db = DatabaseClient()
        self.db.ensure_finance_tables()

    # ── Ingestion ────────────────────────────────────────────────────────

    def sync_day(self, date_str: str, transactions: list) -> dict:
        """Classifies and persists a batch of already-fetched transactions
        for a single operational day.

        Each transaction dict must provide: id, account ('9776'/'2085'),
        amount (Teller sign convention: negative=out, positive=in),
        date ('YYYY-MM-DD' or date), counterparty (str).
        """
        normalized = []
        for tx in transactions:
            tx_date = tx["date"]
            if isinstance(tx_date, str):
                tx_date = datetime.date.fromisoformat(tx_date)
            normalized.append({**tx, "date": tx_date})

        transfer_ids = find_transfer_pairs(normalized)

        saved = 0
        emerson_paid = False

        for tx in normalized:
            counterparty = tx.get("counterparty") or ""
            amount = float(tx["amount"])
            account = tx["account"]

            if tx["id"] in transfer_ids:
                classification = {
                    "category": "Transfer", "subcategory": None,
                    "direction": "inbound" if amount > 0 else "outbound",
                    "recurring_flag": False, "anomaly_flag": False, "anomaly_reason": None,
                }
            else:
                classification = categorize_payee(counterparty, amount, account)

            if EMERSON_KEYWORD in counterparty.lower() and classification["category"] == "Private Client Revenue":
                emerson_paid = True

            try:
                self.db.save_payment({
                    "date": tx["date"].isoformat(),
                    "account": account,
                    "direction": classification["direction"],
                    "counterparty": counterparty,
                    "amount": abs(amount),
                    "category": classification["category"],
                    "subcategory": classification["subcategory"],
                    "recurring_flag": classification["recurring_flag"],
                    "anomaly_flag": classification["anomaly_flag"],
                    "anomaly_reason": classification["anomaly_reason"],
                    "teller_transaction_id": tx.get("id"),
                    "notes": tx.get("notes"),
                })
                saved += 1
            except Exception as e:
                logging.error(f"sync_day: failed to save transaction {tx.get('id')}: {e}")

        self._recompute_luis_chain(date_str)
        self._check_emerson(date_str, emerson_paid)
        self._check_recurring_obligations(date_str)

        return {"success": True, "date": date_str, "transactions_saved": saved}

    def sync_day_via_banking_client(self, date_str: str) -> dict:
        """Cloud-side ingestion path: pulls `date_str`'s transactions directly
        from Teller via the existing BankingClient (mTLS, already deployed),
        maps accounts to '9776'/'2085' by last_four, then runs sync_day().

        Used by both the on-demand `POST /financials/payments/sync` route and
        the nightly `timer_payment_sync` safety-net job. Skips (rather than
        fails) on Teller 429s so a rate limit on one account doesn't abort
        the whole run.
        """
        import requests as _requests
        from .banking import BankingClient

        banking = BankingClient()
        accounts = banking.get_accounts()
        if not accounts:
            return {"success": False, "error": "No Teller accounts found", "date": date_str}

        transactions = []
        errors = []
        for acc in accounts:
            last_four = (acc.get("last_four") or "").strip()
            if last_four not in (BUSINESS_ACCOUNT, PERSONAL_ACCOUNT):
                continue
            try:
                raw_txs = banking.get_transactions(account_id=acc.get("id"), count=50)
            except _requests.exceptions.HTTPError as he:
                status = getattr(he.response, "status_code", None)
                if status == 429:
                    logging.warning(f"sync_day_via_banking_client: Teller 429 for account {last_four}, skipping")
                    errors.append(f"Rate limited on account {last_four} — will retry next sync")
                    continue
                raise

            for tx in raw_txs:
                if tx.get("date") != date_str:
                    continue
                transactions.append({
                    "id": tx.get("id"),
                    "account": last_four,
                    "amount": float(tx.get("amount") or 0),
                    "date": tx.get("date"),
                    "counterparty": tx.get("details", {}).get("counterparty", {}).get("name") or tx.get("description") or "",
                })

        result = self.sync_day(date_str, transactions)
        result["errors"] = errors
        return result

    def _recompute_luis_chain(self, start_date: str):
        """Recomputes Tier/DeferredAmount/RunningBalance for every day from
        start_date through today (inclusive), in chronological order — each
        day's running balance depends on the one before it, so any change
        to a single day (a fresh sync, or reassigning a late payment to a
        different day) must cascade forward through every day after it.

        Reads each day's real amount sent from Finance.Payments rather than
        an in-memory total, so it reflects whatever's actually on record —
        including edits made after the original sync.
        """
        prior_balance = self.db.get_luis_balance_before(start_date)
        current = datetime.date.fromisoformat(start_date)
        end = max(current, datetime.date.today())

        while current <= end:
            date_str = current.isoformat()
            amount_sent = self.db.get_luis_amount_sent_on(date_str)

            result = classify_luis_payment(amount_sent, prior_balance, date_str)

            if result["tier"] == "Missed":
                history = self.db.get_luis_balance_history(limit_days=14)
                prior_tiers = [h["tier"] for h in history["history"] if h["date"] < date_str]
                escalation = check_consecutive_missed(prior_tiers)
                if escalation:
                    result["anomaly_reason"] = escalation

            self.db.save_luis_log(
                date=date_str,
                amount_sent=amount_sent,
                tier=result["tier"],
                deferred_amount=result["deferred_amount"],
                running_balance=result["new_balance"],
                notes=result["anomaly_reason"],
            )

            self.db.clear_luis_summary_flag(date_str)
            if result["anomaly_flag"] or result["anomaly_reason"]:
                self.db.save_payment({
                    "date": date_str,
                    "account": BUSINESS_ACCOUNT,
                    "direction": "outbound",
                    "counterparty": "Luis Canales (daily summary)",
                    "amount": amount_sent,
                    "category": "Vehicle Financing",
                    "subcategory": result["tier"],
                    "recurring_flag": False,
                    "anomaly_flag": True,
                    "anomaly_reason": result["anomaly_reason"] or f"Luis tier: {result['tier']}",
                    "teller_transaction_id": f"luis-summary-{date_str}",
                    "notes": None,
                })

            prior_balance = result["new_balance"]
            current += datetime.timedelta(days=1)

    def reassign_luis_payment(self, payment_id: str, target_date: str) -> dict:
        """Moves a Luis Canales payment from the date Teller posted it to
        the date it actually covers — e.g. a $130 Zelle sent on 7/2 that's
        really the rough-day payment for 7/1 — then recomputes the balance
        chain from the earlier of the two dates forward so the running
        total stays correct on every day after it.
        """
        payment = self.db.get_payment_by_id(payment_id)
        if not payment:
            return {"success": False, "error": "Payment not found"}
        if payment["category"] != "Vehicle Financing":
            return {"success": False, "error": "Not a Luis Canales payment"}
        if (payment.get("teller_transaction_id") or "").startswith("luis-summary-"):
            return {"success": False, "error": "Cannot reassign a summary/flag row — reassign the real transaction instead"}

        original_date = payment["date"]
        if original_date == target_date:
            return {"success": False, "error": "Already assigned to that date"}
        try:
            datetime.date.fromisoformat(target_date)
        except ValueError:
            return {"success": False, "error": "Invalid target date"}

        updated = self.db.update_payment_date(
            payment_id, target_date,
            note=f"Reassigned from {original_date} — late payment for {target_date}",
        )
        if not updated:
            return {"success": False, "error": "Failed to update payment date"}

        self._recompute_luis_chain(min(original_date, target_date))

        return {"success": True, "original_date": original_date, "target_date": target_date}

    def _check_emerson(self, date_str: str, had_payment: bool):
        reason = should_flag_missing_emerson(date_str, had_payment)
        if not reason:
            return
        self.db.save_payment({
            "date": date_str,
            "account": BUSINESS_ACCOUNT,
            "direction": "inbound",
            "counterparty": "Emerson Jean Baptiste (expected)",
            "amount": 0.0,
            "category": "Private Client Revenue",
            "subcategory": None,
            "recurring_flag": False,
            "anomaly_flag": True,
            "anomaly_reason": reason,
            "teller_transaction_id": f"emerson-missing-{date_str}",
            "notes": None,
        })

    def _check_recurring_obligations(self, date_str: str):
        """Flags obligations due on date_str with no matching payment, plus
        the Chase MSF special case (flag if charged — waived is the normal state)."""
        check_date = datetime.date.fromisoformat(date_str)
        obligations = self.db.get_recurring_obligations()
        due_today = [ob for ob in obligations if ob["expected_day"] == check_date.day]
        if not due_today:
            return

        month_str = check_date.strftime("%Y-%m")
        calendar_by_id = {c["obligation_id"]: c for c in self.db.get_bill_calendar(month_str)}

        for ob in due_today:
            entry = calendar_by_id.get(ob["obligation_id"])
            if not entry:
                continue

            if ob["name"] == "Chase MSF":
                if entry["matched_amount"] is not None:
                    self.db.save_payment({
                        "date": date_str, "account": ob["account"], "direction": "outbound",
                        "counterparty": "Chase MSF", "amount": entry["matched_amount"],
                        "category": "Bank Fee", "subcategory": "MSF Waiver Check",
                        "recurring_flag": True, "anomaly_flag": True,
                        "anomaly_reason": "Chase MSF was charged — check waiver status",
                        "teller_transaction_id": f"chase-msf-check-{date_str}", "notes": None,
                    })
                continue

            if entry["status"] == "overdue":
                self.db.save_payment({
                    "date": date_str, "account": ob["account"], "direction": "outbound",
                    "counterparty": ob["name"], "amount": ob["expected_amount"],
                    "category": ob["category"], "subcategory": None,
                    "recurring_flag": True, "anomaly_flag": True,
                    "anomaly_reason": f"{ob['name']} expected on day {ob['expected_day']} — not found",
                    "teller_transaction_id": f"obligation-overdue-{ob['obligation_id']}-{date_str}",
                    "notes": None,
                })
            elif entry["status"] == "paid_variant":
                self.db.save_payment({
                    "date": date_str, "account": ob["account"], "direction": "outbound",
                    "counterparty": ob["name"], "amount": entry["matched_amount"],
                    "category": ob["category"], "subcategory": None,
                    "recurring_flag": True, "anomaly_flag": True,
                    "anomaly_reason": f"{ob['name']} amount varied from expected ${ob['expected_amount']:.2f}",
                    "teller_transaction_id": f"obligation-variant-{ob['obligation_id']}-{date_str}",
                    "notes": None,
                })

    # ── Read side ────────────────────────────────────────────────────────

    def get_scorecard(self, date_str: str) -> dict:
        window_start, window_end = get_operational_window(date_str)
        start_date = window_start.date().isoformat()
        end_date_exclusive = window_end.date().isoformat()

        payments = self.db.get_payments(date_from=start_date, date_to=end_date_exclusive, limit=1000)
        payments = [p for p in payments if p["date"] < end_date_exclusive]

        gross_earnings = sum(
            p["amount"] for p in payments
            if p["direction"] == "inbound" and p["category"] in REVENUE_CATEGORIES
        )
        supercharging = sum(p["amount"] for p in payments if p["category"] == "EV Charging")
        food_dining = sum(p["amount"] for p in payments if p["category"] == "Food & Dining")

        luis_history = self.db.get_luis_balance_history(limit_days=1)
        today_entry = luis_history["today"]
        luis_tier = today_entry["tier"] if today_entry and today_entry["date"] == date_str else "Pending"

        return {
            "date": date_str,
            "gross_earnings": {"actual": round(gross_earnings, 2), "target": DAILY_TARGETS["gross_earnings"]},
            "supercharging": {"actual": round(supercharging, 2), "target": DAILY_TARGETS["supercharging"]},
            "food_dining": {"actual": round(food_dining, 2), "target": DAILY_TARGETS["food_dining"]},
            "luis_tier": luis_tier,
            "luis_balance": luis_history["current_balance"],
        }
