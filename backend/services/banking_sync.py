import logging
from datetime import datetime
from .banking import BankingClient
from .semantic_ingestion import SemanticIngestionService
from .database import DatabaseClient

# Teller transaction types/descriptions that are INCOME, not expenses.
# These are skipped during expense sync to avoid polluting the ledger.
INCOME_SKIP_PATTERNS = [
    "uber", "lyft", "doordash", "instacart", "stripe",
    "square", "paypal", "venmo", "zelle", "direct dep",
    "direct deposit", "ach credit", "transfer in", "refund",
    "cashback", "interest paid", "dividend"
]

# Teller `details.category` values that indicate income, not spending
INCOME_CATEGORIES = {
    "income", "transfer", "payroll", "interest", "dividend", "refund"
}


def _is_expense(tx: dict) -> tuple[bool, str]:
    """
    Returns (is_expense: bool, reason: str).
    A transaction is an expense if:
      - amount is negative (debit)
      - type is not a known income type
      - description does not match income patterns
    """
    amount = float(tx.get("amount", 0))
    description = (tx.get("description") or "").lower()
    tx_type = (tx.get("type") or "").lower()
    category = (
        tx.get("details", {}).get("category") or
        tx.get("category") or ""
    ).lower()

    # Teller: negative amount = debit (money leaving account)
    if amount >= 0:
        return False, f"SKIP (credit/income): amount=${amount:.2f}"

    # Skip if category is income
    if category in INCOME_CATEGORIES:
        return False, f"SKIP (income category): {category}"

    # Skip if description matches known income patterns
    for pattern in INCOME_SKIP_PATTERNS:
        if pattern in description:
            return False, f"SKIP (income pattern '{pattern}'): {description[:40]}"

    return True, "OK"


class BankingSyncService:
    def __init__(self):
        self.banking = BankingClient()
        self.semantic = SemanticIngestionService()
        self.db = DatabaseClient()

    def sync_recent(self, count=50, since_date=None):
        """
        Pulls expense-only transactions (debits) for all connected accounts.
        Skips all income, credits, and known rideshare deposits.
        Includes both posted and pending transactions so receipt screenshots
        can be matched against same-day pending items.
        """
        logs = []
        try:
            target_date = since_date or datetime.now().strftime('%Y-%m-%d')
            logs.append(f"START: Expense-only Banking Sync (Since: {target_date})")

            accounts = self.banking.get_accounts()
            if not accounts:
                logs.append("WARN: No accounts found from Teller API.")
                return {"success": False, "error": "No accounts found", "logs": logs}

            logs.append(f"INFO: Found {len(accounts)} accounts.")
            synced_count = 0
            skipped_count = 0
            total_tx = 0

            for acc in accounts:
                acc_id = acc.get('id')
                acc_name = acc.get('name', 'Unknown Account')

                logs.append(f"SYNC: Fetching transactions for '{acc_name}'...")
                transactions = self.banking.get_transactions(account_id=acc_id, count=count)
                total_tx += len(transactions)

                acc_synced = 0
                for tx in transactions:
                    # Date filter
                    tx_date = tx.get('date')
                    if tx_date and tx_date < target_date:
                        continue

                    # ── Expense filter ────────────────────────────────────────
                    is_exp, reason = _is_expense(tx)
                    if not is_exp:
                        logs.append(reason)
                        skipped_count += 1
                        continue
                    # ─────────────────────────────────────────────────────────

                    amount = abs(float(tx.get("amount", 0)))
                    status = tx.get("status", "posted")   # posted | pending
                    description = tx.get("description") or ""
                    category = (
                        tx.get("details", {}).get("category") or
                        tx.get("category") or "General"
                    )

                    logs.append(
                        f"EXPENSE [{status.upper()}]: ${amount:.2f} — {description[:40]} ({category})"
                    )

                    # 1. Semantic vectorization
                    success = self.semantic.ingest_teller_transaction(tx)
                    if success:
                        synced_count += 1
                        acc_synced += 1

                    # 2. SQL persistence for Dashboard + reconciliation matching
                    try:
                        expense_data = {
                            "id": tx.get("id"),
                            "category": category,
                            "amount": amount,
                            "note": f"[{status.upper()}] {description}",
                            "timestamp": tx_date
                        }
                        self.db.save_manual_expense(expense_data)
                    except Exception as de:
                        logging.error(f"Failed to save expense to SQL: {de}")

                logs.append(f"INFO: Saved {acc_synced} expenses from '{acc_name}'.")

            logs.append(
                f"DONE: {synced_count} expenses synced, {skipped_count} income/credits skipped."
            )
            return {
                "success": True,
                "transactions_processed": total_tx,
                "expenses_synced": synced_count,
                "income_skipped": skipped_count,
                "accounts_synced": len(accounts),
                "logs": logs
            }
        except Exception as e:
            logs.append(f"ERROR: {str(e)}")
            logging.error(f"Banking Sync Error: {e}")
            return {"success": False, "error": str(e), "logs": logs}

    def get_pending_expenses(self, date_str: str = None) -> list:
        """
        Returns all PENDING debit transactions for a given date.
        Used by the receipt OCR matching flow — when you upload a receipt
        screenshot, we match it against today's pending items.
        """
        target_date = date_str or datetime.now().strftime('%Y-%m-%d')
        pending = []

        try:
            accounts = self.banking.get_accounts()
            for acc in accounts:
                acc_id = acc.get('id')
                transactions = self.banking.get_transactions(account_id=acc_id, count=50)
                for tx in transactions:
                    tx_date = tx.get('date', '')
                    status = tx.get('status', '')

                    # Only today's pending debits
                    if tx_date != target_date:
                        continue
                    if status != 'pending':
                        continue

                    is_exp, _ = _is_expense(tx)
                    if not is_exp:
                        continue

                    pending.append({
                        "id": tx.get("id"),
                        "date": tx_date,
                        "status": status,
                        "amount": abs(float(tx.get("amount", 0))),
                        "description": tx.get("description") or "",
                        "category": (
                            tx.get("details", {}).get("category") or
                            tx.get("category") or "General"
                        ),
                        "account_name": acc.get("name", "Unknown")
                    })

        except Exception as e:
            logging.error(f"get_pending_expenses error: {e}")

        return pending
