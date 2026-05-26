#!/usr/bin/env python
"""
CLI helper script to scan OneDrive daily folders for expense receipts,
process them via Multi-Modal Vision AI, log to SQL and index in Vector Store.
"""

import sys
import os
import argparse
import datetime
from zoneinfo import ZoneInfo

# Add backend directory to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Initialize configuration
from services.config_loader import config_loader
try:
    config_loader.load()
except RuntimeError as e:
    print(f"FATAL CONFIG ERROR: {e}")
    sys.exit(1)

from services.cloud_watcher import CloudWatcherService

def main():
    parser = argparse.ArgumentParser(description="Scan daily OneDrive folders for expense receipts.")
    parser.add_argument(
        "--date",
        type=str,
        help="Target date in YYYY-MM-DD format. Defaults to today in America/Denver timezone."
    )
    parser.add_argument(
        "--path",
        type=str,
        help="Optional explicit OneDrive folder path to scan."
    )
    args = parser.parse_args()

    # Timezone consistency: America/Denver
    tz = ZoneInfo("America/Denver")
    if args.date:
        try:
            # Validate date format
            datetime.datetime.strptime(args.date, "%Y-%m-%d")
            date_str = args.date
        except ValueError:
            print(f"ERROR: Invalid date format '{args.date}'. Must be YYYY-MM-DD.")
            sys.exit(1)
    else:
        date_str = datetime.datetime.now(tz).strftime("%Y-%m-%d")

    print(f"============================================================")
    print(f"SummitOS Daily Expense Scanner Starting")
    print(f"Target Date: {date_str} (America/Denver)")
    if args.path:
        print(f"Explicit Path: {args.path}")
    print(f"============================================================")

    try:
        service = CloudWatcherService()
        result = service.scan_and_log_expenses(date_str, explicit_path=args.path)

        if not result.get("success"):
            print(f"\n[ERROR] SCAN FAILED: {result.get('error')}")
            if "logs" in result:
                print("\nDetailed Logs:")
                for log_line in result["logs"]:
                    print(f"  {log_line}")
            sys.exit(1)

        print(f"\n[SUCCESS] SCAN COMPLETED SUCCESSFULLY!")
        print(f"Date: {result.get('date')}")
        print(f"Expense Count: {result.get('expense_count', 0)}")
        print(f"Total Amount: ${result.get('total_amount', 0.0):.2f}")

        if result.get("expenses"):
            print("\nProcessed Expenses:")
            for exp in result["expenses"]:
                print(f"  - [{exp['expense_id']}] {exp['merchant']} - ${exp['amount']:.2f} ({exp['category']})")
                if exp.get("items"):
                    print(f"    Items: {', '.join(exp['items'])}")
                print(f"    File: {exp['filename']}")
                print(f"    Date/Time: {exp['date_time']}")
        else:
            print("\nNo new expense receipts processed/saved.")

        if "logs" in result:
            print("\nExecution Logs:")
            for log_line in result["logs"]:
                print(f"  {log_line}")

    except Exception as e:
        print(f"\n[CRITICAL] UNEXPECTED SYSTEM ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
