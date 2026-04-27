import logging
import datetime
from zoneinfo import ZoneInfo
from services.graph import GraphClient
from services.uber_matcher import UberMatcherService

log = logging.getLogger(__name__)

class CloudWatcherService:
    def __init__(self):
        self.graph = GraphClient()
        self.uber = UberMatcherService()
        self.camera_roll_path = "Pictures/Camera Roll"
        self.target_root = "Uber Driver"

    def scan_and_route(self) -> dict:
        """
        Scans the OneDrive Camera Roll for new screenshots, 
        identifies Uber cards, ingests data, and routes files to organized folders.
        """
        log.info(f"Starting cloud scan of '{self.camera_roll_path}'...")
        
        try:
            files = self.graph.list_folder_files(self.camera_roll_path)
        except Exception as e:
            log.error(f"Failed to list camera roll: {e}")
            return {"success": False, "error": str(e)}
        
        results = {
            "success": True,
            "scanned": len(files),
            "processed": 0,
            "matched": 0,
            "errors": 0,
            "logs": []
        }

        # Use Denver time for path organization
        denver_tz = ZoneInfo("America/Denver")
        now = datetime.datetime.now(denver_tz)

        for file in files:
            name = file.get("name", "")
            # Basic filter for screenshots
            if not name.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            
            item_id = file.get("id")
            log.info(f"Analyzing cloud file: {name} (ID: {item_id})")
            results["processed"] += 1

            try:
                # 1. Download bytes for OCR
                content = self.graph.get_file_content(item_id)
                
                # 2. Process via UberMatcher (Matches to SQL, returns result)
                process_result = self.uber.process_image_bytes(content, name)
                
                if process_result.get("status") == "MATCHED":
                    results["matched"] += 1
                    ride_id = process_result.get("ride_id")
                    earnings = process_result.get("driver_earnings")
                    results["logs"].append(f"MATCH: {name} -> Ride {ride_id} (${earnings})")

                    # 3. Calculate destination path
                    # Format: Uber Driver / 2026 / April / Week N / M.D.YY
                    year = now.strftime("%Y")
                    month = now.strftime("%B")
                    week_num = (now.day - 1) // 7 + 1
                    week = f"Week {min(week_num, 4)}" 
                    date_str = now.strftime("%#m.%#d.%y").replace("/", ".") # Windows style or similar
                    # Safety override for date_str to match M.D.YY
                    date_str = f"{now.month}.{now.day}.{now.year % 100:02d}"
                    
                    target_dir = f"{self.target_root}/{year}/{month}/{week}/{date_str}"
                    
                    # 4. Ensure destination exists and MOVE
                    log.info(f"Routing {name} to {target_dir}...")
                    target_id = self.graph.ensure_path_exists(target_dir)
                    self.graph.move_file(item_id, target_id)
                    results["logs"].append(f"ROUTED: {name} -> {target_dir}")
                else:
                    msg = f"SKIP: {name} ({process_result.get('status')})"
                    results["logs"].append(msg)
                    log.info(msg)

            except Exception as e:
                results["errors"] += 1
                msg = f"ERROR: {name}: {str(e)}"
                results["logs"].append(msg)
                log.error(msg)

        return results
