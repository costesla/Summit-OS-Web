import logging
from typing import Dict, Any, Optional

class AccountingAgent:
    def __init__(self):
        pass

    def process(self, trip_data: Dict[str, Any], previous_trip: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Computes business financials and audit-ready metrics.
        """
        logging.info("AccountingAgent: Processing financials...")
        
        rider_payment = trip_data.get('rider_payment', 0.0)
        driver_earnings = trip_data.get('driver_total', 0.0)
        
        results = {}
        if rider_payment > 0:
            results['platform_cut_raw'] = rider_payment - driver_earnings
            results['platform_cut_percent'] = (results['platform_cut_raw'] / rider_payment) * 100
            results['margin_percent'] = (driver_earnings / rider_payment) * 100
        else:
            results['platform_cut_raw'] = 0.0
            results['platform_cut_percent'] = 0.0
            results['margin_percent'] = 100.0

        # Idle Time calculation
        if previous_trip:
            prev_end = previous_trip.get('end_time_epoch')
            curr_start = trip_data.get('start_time_epoch')
            if prev_end and curr_start:
                idle_seconds = curr_start - prev_end
                results['idle_time_min'] = max(0, idle_seconds / 60.0)
        else:
             results['idle_time_min'] = 0.0

        return results
