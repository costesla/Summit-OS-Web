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

    # Determine today's date in Mountain Time
    now_mdt = datetime.datetime.now(tz=MDT)
    today_str = now_mdt.strftime("%Y-%m-%d")

    logging.info(f"[NightlySync] Starting automatic Daily Sync for {today_str} (MDT: {now_mdt.strftime('%Y-%m-%d %H:%M %Z')})")

    try:
        from api.operations import _execute_daily_sync
        result = _execute_daily_sync(target_date_str=today_str)

        logs = result.get("logs", [])
        for line in logs:
            logging.info(f"[NightlySync] {line}")

        logging.info(
            f"[NightlySync] ✅ Completed for {today_str}. "
            f"Success={result.get('success')}"
        )

    except Exception as e:
        logging.error(f"[NightlySync] ❌ Failed for {today_str}: {e}", exc_info=True)
