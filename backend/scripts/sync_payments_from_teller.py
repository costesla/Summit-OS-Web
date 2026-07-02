"""Nightly local sync: Teller (via the personal-finance-mcp package) -> Azure SQL Finance.Payments.

This is the PRIMARY ingestion path for the Payment Tracker. It runs on Peter's
machine (not in Azure) because the Teller MCP server it reuses
(`backend/finance_mcp`) keeps its own SQLite cache at
~/.finance_mcp/finance.db and is only reachable locally — MCP servers are
stdio subprocesses spoken to by an interactive AI host, not a network
service a cloud Azure Function could call.

We import personal_finance_mcp's `config`/`db`/`teller` modules directly
(no `mcp` SDK dependency required — only `server.py` needs that package,
and we deliberately don't import it) to reuse the same Teller sync logic
as the MCP server's `sync` tool, then classify and push the results into
Azure SQL the same way `summit_sync/scripts/sync_today.py` already does for
the Tessie/OCR pipeline (SQL_CONNECTION_STRING from a local .env).

A cloud-side safety net (`api/timer_payment_sync.py`) covers the case where
this machine is off overnight; both paths dedupe on TellerTransactionID.

Schedule this nightly via Windows Task Scheduler, separate from
Run-Daily-Sync.bat (which drives the unrelated legacy Tessie/OCR pipeline).
"""

import os
import sys
import asyncio
import logging
import datetime
from datetime import timedelta

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINANCE_MCP_SRC = os.path.join(BACKEND_DIR, "finance_mcp", "src")
for path in (BACKEND_DIR, FINANCE_MCP_SRC):
    if path not in sys.path:
        sys.path.append(path)

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

from personal_finance_mcp.config import Config, TellerConfigError
from personal_finance_mcp.db import Database
from personal_finance_mcp.teller import TellerClient, TellerAPIError

from services.payment_tracker import PaymentTrackerService
from services.payment_categorizer import BUSINESS_ACCOUNT, PERSONAL_ACCOUNT


async def refresh_finance_cache(config: Config, db: Database) -> dict:
    """Mirrors personal_finance_mcp.server._handle_sync's logic directly
    against TellerClient/Database (skipping server.py so this script never
    needs the `mcp` SDK installed — only httpx/dotenv, already used
    elsewhere in this repo). 429s are retried with backoff inside
    TellerClient; if still rate-limited after retries, that account is
    skipped and logged rather than aborting the whole sync."""
    try:
        config.validate_teller()
    except TellerConfigError as e:
        logging.error(f"Teller not configured: {e}")
        return {"status": "error", "error": str(e)}

    client = TellerClient(config.teller_certificate, config.teller_private_key)
    enrollments = db.get_active_enrollments()
    if not enrollments:
        return {"status": "error", "error": "No active enrollments — run enroll_account first"}

    total_accounts = 0
    total_transactions = 0
    errors = []
    last_sync = db.get_last_sync_date("teller")
    from_date = (datetime.datetime.fromisoformat(last_sync) - timedelta(days=3)).strftime("%Y-%m-%d") if last_sync else None
    sync_id = db.start_sync_log("teller")

    for enrollment in enrollments:
        token = enrollment["access_token"]
        try:
            accounts = await client.get_accounts(token)
            for account in accounts:
                db.upsert_account(
                    id=account["id"], source="teller", institution=account["institution"],
                    name=account["name"], type=account["type"], subtype=account.get("subtype"),
                    last_four=account.get("last_four"), enrollment_id=account.get("enrollment_id"),
                    status=account.get("status", "open"),
                )
                total_accounts += 1
                try:
                    balance = await client.get_account_balances(token, account["id"])
                    db.save_balance(account["id"], available=balance.get("available"), ledger=balance.get("ledger"))
                except TellerAPIError as e:
                    errors.append(f"Balance fetch failed for {account['name']}: {e}")
                try:
                    transactions = await client.get_transactions(token, account["id"], from_date=from_date)
                    if account.get("type") == "credit":
                        for t in transactions:
                            t["amount"] = -t["amount"]
                    total_transactions += db.insert_transactions(transactions)
                except TellerAPIError as e:
                    if e.status_code == 429:
                        logging.warning(f"Rate limited on {account['name']} — will retry next sync cycle")
                    errors.append(f"Transaction fetch failed for {account['name']}: {e}")
        except TellerAPIError as e:
            if e.status_code == 401:
                db.disconnect_enrollment(enrollment["id"])
                errors.append(f"Enrollment {enrollment['id']} disconnected — reconnect via enroll_account")
            else:
                errors.append(f"Error syncing enrollment {enrollment['id']}: {e}")

    status = "success" if not errors else "partial"
    db.complete_sync_log(
        sync_id, accounts_synced=total_accounts, transactions_synced=total_transactions,
        status=status, error="; ".join(errors) if errors else None,
    )
    return {
        "status": status,
        "accounts_synced": total_accounts,
        "new_transactions": total_transactions,
        "errors": errors,
    }


def build_account_map(db: Database) -> dict:
    """Maps finance_mcp account_id -> '9776' / '2085' via last_four."""
    mapping = {}
    for acc in db.get_accounts(source="teller"):
        last_four = (acc.get("last_four") or "").strip()
        if last_four in (BUSINESS_ACCOUNT, PERSONAL_ACCOUNT):
            mapping[acc["id"]] = last_four
    return mapping


def collect_transactions_for_date(db: Database, account_map: dict, date_str: str) -> list:
    result = db.get_transactions(start_date=date_str, end_date=date_str, limit=0)
    transactions = []
    for tx in result["transactions"]:
        account = account_map.get(tx["account_id"])
        if not account:
            continue  # not one of the two tracked Chase accounts
        transactions.append({
            "id": tx["id"],
            "account": account,
            "amount": float(tx["amount"]),
            "date": tx["date"],
            "counterparty": tx.get("counterparty") or tx.get("description") or "",
        })
    return transactions


def run():
    logging.info("--- STARTING PAYMENT TRACKER SYNC (Teller MCP -> Azure SQL) ---")
    config = Config()
    db = Database(config.db_path)

    sync_result = asyncio.run(refresh_finance_cache(config, db))
    logging.info(f"Teller cache refresh: {sync_result}")

    account_map = build_account_map(db)
    if not account_map:
        logging.warning("No mapped 9776/2085 accounts found in finance.db — nothing to sync.")
        db.close()
        return

    tracker = PaymentTrackerService()
    today = datetime.date.today()
    for offset in (1, 0):  # yesterday first, then today (catches late-posting transactions)
        date_str = (today - datetime.timedelta(days=offset)).isoformat()
        transactions = collect_transactions_for_date(db, account_map, date_str)
        result = tracker.sync_day(date_str, transactions)
        logging.info(f"Synced {date_str}: {result}")

    db.close()
    logging.info("--- PAYMENT TRACKER SYNC FINISHED ---")


if __name__ == "__main__":
    run()
