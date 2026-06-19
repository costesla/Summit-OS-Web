import logging
import datetime
import azure.functions as func
from zoneinfo import ZoneInfo

bp = func.Blueprint()

MDT = ZoneInfo("America/Denver")

# ─── Nightly Automatic Daily Sync ────────────────────────────────────────────
# Fires at 05:00 UTC = 11:00 PM MDT every night.
# Runs _execute_daily_sync for the current business day so the dashboard
# is fully built by the time the driver wakes up the next morning.
# Manual Rebuild Day in the dashboard is still available for corrections.
# ─────────────────────────────────────────────────────────────────────────────

@bp.schedule(
    schedule="0 0 5 * * *",   # 5:00 AM UTC = 11:00 PM MDT
    arg_name="nightlyTimer",
    run_on_startup=False,
    use_monitor=True          # Ensures exactly-once execution
)
def timer_nightly_sync(nightlyTimer: func.TimerRequest) -> None:
    if nightlyTimer.past_due:
        logging.warning("[NightlySync] Timer is past due — running now anyway.")

    # Determine today's and yesterday's date in Mountain Time
    now_mdt = datetime.datetime.now(tz=MDT)
    today_str = now_mdt.strftime("%Y-%m-%d")
    yesterday_str = (now_mdt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    logging.info(f"[NightlySync] Starting automatic Daily Sync lookback for {yesterday_str} and {today_str} (MDT: {now_mdt.strftime('%Y-%m-%d %H:%M %Z')})")

    # Run for yesterday
    try:
        from api.operations import _execute_daily_sync
        logging.info(f"[NightlySync] Running sync for yesterday ({yesterday_str})...")
        result_yesterday = _execute_daily_sync(target_date_str=yesterday_str)
        logs_y = result_yesterday.get("logs", [])
        for line in logs_y:
            logging.info(f"[NightlySync] [Yesterday] {line}")
        logging.info(f"[NightlySync] [Yesterday] Completed. Success={result_yesterday.get('success')}")
    except Exception as e:
        logging.error(f"[NightlySync] ❌ Yesterday Sync Failed: {e}", exc_info=True)

    # Run for today
    try:
        from api.operations import _execute_daily_sync
        logging.info(f"[NightlySync] Running sync for today ({today_str})...")
        result_today = _execute_daily_sync(target_date_str=today_str)
        logs_t = result_today.get("logs", [])
        for line in logs_t:
            logging.info(f"[NightlySync] [Today] {line}")
        logging.info(f"[NightlySync] [Today] Completed. Success={result_today.get('success')}")
    except Exception as e:
        logging.error(f"[NightlySync] ❌ Today Sync Failed: {e}", exc_info=True)


    # ── Earnings deduplication ─────────────────────────────────────────────────
    # Zero out Driver_Earnings on TESSIE-* / UBER-* rows that duplicate a
    # canonical TRIP-* record. Runs after the daily sync so any newly imported
    # drives are cleaned before morning reporting.
    try:
        from services.database import DatabaseClient
        result = DatabaseClient().dedup_earnings(lookback_days=7)
        if result.get("error"):
            logging.warning(f"[NightlyDedup] ⚠️ Error: {result['error']}")
        elif result["rows_zeroed"] > 0:
            logging.info(
                f"[NightlyDedup] ✅ Zeroed {result['rows_zeroed']} duplicate rows "
                f"(${result['amount_zeroed']:.2f} removed from TESSIE/UBER cross-refs)"
            )
        else:
            logging.info("[NightlyDedup] ✅ No duplicates found — data is clean.")
    except Exception as e:
        logging.error(f"[NightlyDedup] ❌ Failed: {e}", exc_info=True)
