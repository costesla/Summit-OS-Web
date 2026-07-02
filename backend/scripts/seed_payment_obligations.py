"""One-time seed of the Monthly Fixed Obligations into Finance.RecurringObligations.

Idempotent — safe to re-run. Run once after deploying the Payment Tracker:

    python backend/scripts/seed_payment_obligations.py
"""

import os
import sys
import logging

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

from services.database import DatabaseClient


def run():
    db = DatabaseClient()
    inserted = db.seed_recurring_obligations()
    logging.info(f"Seed complete — {inserted} new obligation(s) inserted (existing rows left untouched).")


if __name__ == "__main__":
    run()
