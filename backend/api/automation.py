import logging
import azure.functions as func
import os
import json
from datetime import datetime, timedelta, timezone

bp = func.Blueprint()
mdt = timezone(timedelta(hours=-6))

@bp.timer_trigger(schedule="0 0 2 * * *", arg_name="mytimer", run_on_startup=False, use_monitor=False) 
def tessie_daily_sync(mytimer: func.TimerRequest) -> None:
    """Timer trigger: Runs daily at 2:00 AM MDT to sync Tessie data."""
    utc_timestamp = datetime.now(timezone.utc).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Tessie daily sync timer function started at %s', utc_timestamp)
    
    try:
        from services.tessie_sync import TessieSyncService
        service = TessieSyncService()
        # Sync yesterday's data
        target_date = (datetime.now(mdt) - timedelta(days=1)).strftime('%Y-%m-%d')
        results = service.sync_day(target_date)
        logging.info(f"Tessie Sync Success for {target_date}: {json.dumps(results)}")
    except Exception as e:
        logging.error(f"Tessie Sync Failed: {str(e)}")

@bp.blob_trigger(arg_name="myblob", path="driver-uploads/{name}", connection="AzureWebJobsStorage")
def uber_card_processor(myblob: func.InputStream):
    """Blob trigger: Processes new Uber trip card screenshots uploaded to Blob Storage."""
    logging.info(f"Uber card processor triggered by blob: {myblob.name} ({myblob.length} bytes)")
    
    try:
        from services.uber_matcher import UberMatcherService
        service = UberMatcherService()
        filename = os.path.basename(myblob.name)
        image_bytes = myblob.read()
        
        result = service.process_image_bytes(image_bytes, filename)
        logging.info(f"Uber Match Result for {filename}: {json.dumps(result)}")
    except Exception as e:
        logging.error(f"Uber Card Processing Failed for {myblob.name}: {str(e)}")
@bp.timer_trigger(schedule="0 */30 * * * *", arg_name="mytimer", run_on_startup=False, use_monitor=False)
def autonomous_cloud_router(mytimer: func.TimerRequest) -> None:
    """Timer trigger: Runs every 30 minutes to scan Camera Roll and route Uber trips."""
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logging.info('Autonomous Cloud Router timer function started at %s', utc_timestamp)

    try:
        from services.cloud_watcher import CloudWatcherService
        service = CloudWatcherService()
        results = service.scan_and_route()
        logging.info(f"Cloud Routing Results: {json.dumps(results)}")
    except Exception as e:
        logging.error(f"Cloud Routing Failed: {str(e)}")
