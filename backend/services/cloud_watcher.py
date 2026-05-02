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

    def scan_and_route(self, target_date: str = None) -> dict:
        """
        Scans OneDrive for new Uber screenshots and routes matched files.

        Args:
            target_date: ISO date string (YYYY-MM-DD). If provided, also scans
                         the specific Uber Driver folder for that date in addition
                         to Camera Roll / Screenshots.
        """
        scan_paths = [self.camera_roll_path, "Pictures/Screenshots"]
        
        # Calculate target folder for the date if provided
        target_folder = None
        if target_date:
            try:
                dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
                year = dt.strftime("%Y")
                month = dt.strftime("%B")
                day = dt.strftime("%d")
                week_num = (dt.day - 1) // 7 + 1
                week = f"Week {week_num}"
                target_folder = f"{self.target_root}/{year}/{month}/{week}/{day}"
                if target_folder not in scan_paths:
                    scan_paths.append(target_folder)
            except Exception as e:
                log.error(f"Error parsing target_date {target_date}: {e}")

        all_results = {
            "success": True,
            "scanned": 0,
            "processed": 0,
            "matched": 0,
            "errors": 0,
            "logs": []
        }

        all_results["logs"].append(f"START: Cloud Scan (Target: {target_date or 'Today'})")

        for path in scan_paths:
            all_results["logs"].append(f"SCAN: Checking OneDrive path '{path}'...")
            try:
                files = self.graph.list_folder_files(path)
                if not files:
                    all_results["logs"].append(f"INFO: Folder '{path}' is empty or not found.")
                    continue
                
                all_results["logs"].append(f"INFO: Found {len(files)} items in '{path}'.")
                all_results["scanned"] += len(files)
                self._process_files(files, path, all_results, target_date)
            except Exception as e:
                log.warning(f"Could not list folder {path}: {e}")
                all_results["logs"].append(f"WARN: Could not access '{path}': {str(e)}")

        return all_results

    def _process_files(self, files: list, source_path: str, results: dict, target_date: str):
        # Use Denver time for default path organization if no target_date
        denver_tz = ZoneInfo("America/Denver")
        now = datetime.datetime.now(denver_tz)
        if target_date:
            try:
                now = datetime.datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=denver_tz)
            except:
                pass

        for file in files:
            name = file.get("name", "")
            results["logs"].append(f"FILE: Evaluating '{name}'...")
            
            if not name.lower().endswith(('.jpg', '.jpeg', '.png')):
                results["logs"].append(f"SKIP: '{name}' is not an image.")
                continue
            
            item_id = file.get("id")
            results["processed"] += 1

            try:
                content = self.graph.get_file_content(item_id)
                results["logs"].append(f"OCR: Analyzing '{name}' ({len(content)} bytes)...")
                process_result = self.uber.process_image_bytes(content, name)
                
                status = process_result.get("status")
                if status == "MATCHED":
                    results["matched"] += 1
                    results["logs"].append(f"MATCH: '{name}' -> Ride {process_result.get('ride_id')} ($ {process_result.get('driver_earnings')})")

                    # Only move if it's NOT already in a target folder
                    if source_path in [self.camera_roll_path, "Pictures/Screenshots"]:
                        year = now.strftime("%Y")
                        month = now.strftime("%B")
                        week_num = (now.day - 1) // 7 + 1
                        week = f"Week {week_num}"
                        day = now.strftime("%d")
                        
                        target_dir = f"{self.target_root}/{year}/{month}/{week}/{day}"
                        results["logs"].append(f"MOVE: Routing '{name}' to {target_dir}...")
                        target_id = self.graph.ensure_path_exists(target_dir)
                        self.graph.move_file(item_id, target_id)
                        results["logs"].append(f"DONE: Moved '{name}' to organization tree.")
                else:
                    reason = process_result.get("reason") or process_result.get("message", "No reason provided")
                    results["logs"].append(f"SKIP: '{name}' status: {status} ({reason})")

            except Exception as e:
                results["errors"] += 1
                results["logs"].append(f"ERROR: Failed processing '{name}': {str(e)}")
                log.error(f"Error processing {name}: {e}")

