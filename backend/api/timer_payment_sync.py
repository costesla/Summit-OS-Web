import logging
import datetime
import azure.functions as func
from zoneinfo import ZoneInfo

bp = func.Blueprint()

MDT = ZoneInfo("America/Denver")

# ─── Nightly Payment Tracker Safety-Net Sync ─────────────────────────────────
# Fires at 06:00 UTC = 12:00 AM MDT every night — after the local
# Teller-MCP-based sync (scripts/sync_payments_from_teller.py) is expected to
# have already run on Peter's machine. This is a cloud-side fallback using
# the existing BankingClient's direct Teller access, so the ledger still
# gets built even if the local machine was off. Both paths dedupe on
# TellerTransactionID, so this can never double-count.
# ─────────────────────────────────────────────────────────────────────────────

@bp.schedule(
    schedule="0 0 6 * * *",   # 6:00 AM UTC = 12:00 AM MDT
    arg_name="paymentSyncTimer",
    run_on_startup=False,
    use_monitor=True
)
def timer_payment_sync(paymentSyncTimer: func.TimerRequest) -> None:
    if paymentSyncTimer.past_due:
        logging.warning("[PaymentSync] Timer is past due — running now anyway.")

    now_mdt = datetime.datetime.now(tz=MDT)
    today_str = now_mdt.strftime("%Y-%m-%d")
    yesterday_str = (now_mdt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        from services.payment_tracker import PaymentTrackerService
        tracker = PaymentTrackerService()

        for target_date in (yesterday_str, today_str):
            try:
                result = tracker.sync_day_via_banking_client(target_date)
                logging.info(f"[PaymentSync] {target_date}: {result}")
            except Exception as e:
                logging.error(f"[PaymentSync] ❌ Sync failed for {target_date}: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"[PaymentSync] ❌ Fatal error: {e}", exc_info=True)
