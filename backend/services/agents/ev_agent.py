import logging
from typing import Dict, Any

class EVEfficiencyAgent:
    def __init__(self):
        self.battery_capacity = 82.0 # Model 3/Y LR standard

    def process(self, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Computes EV performance and efficiency metrics.
        """
        logging.info("EVEfficiencyAgent: Analyzing telemetry...")
        
        distance = trip_data.get('tessie_distance', trip_data.get('distance_miles', 0.0))
        energy_used = trip_data.get('energy_used', 0.0)
        start_soc = trip_data.get('start_soc_perc', 0.0)
        end_soc = trip_data.get('end_soc_perc', 0.0)
        soc_delta = start_soc - end_soc
        
        results = {
            'soc_delta': soc_delta,
            'energy_used': energy_used,
            'wh_mi': 0.0
        }

        if distance > 0:
            if energy_used > 0:
                results['wh_mi'] = (energy_used * 1000) / distance
            elif soc_delta > 0:
                est_energy = (soc_delta / 100.0) * self.battery_capacity
                results['wh_mi'] = (est_energy * 1000) / distance
                results['energy_used_estimated'] = est_energy
                results['energy_used'] = est_energy

        return results
