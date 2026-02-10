import logging
from typing import Dict, Any, List

class ComplianceAgent:
    def __init__(self):
        pass

    def verify(self, final_deliverables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforces 6-gate verification.
        """
        logging.info("ComplianceAgent: Running 6-gate verification...")
        
        gates = {
            "gate_1": False, # Address Presence
            "gate_2": False, # Financial Reconciliation
            "gate_3": False, # Telemetry Symmetry
            "gate_4": False, # Card Completeness
            "gate_5": False, # Sidecar Schema
            "gate_6": False  # BI Model Consistency
        }
        
        # Gate 1: Addresses
        if final_deliverables.get('pickup_address_full') and final_deliverables.get('dropoff_address_full'):
            gates["gate_1"] = True
        elif final_deliverables.get('start_location') and final_deliverables.get('end_location'):
            gates["gate_1"] = True

        # Gate 2: Financials
        rider = final_deliverables.get('rider_payment', 0)
        driver = final_deliverables.get('driver_total', 0)
        cut = final_deliverables.get('platform_cut_raw', 0)
        if abs(rider - (driver + cut)) < 0.01:
            gates["gate_2"] = True

        # Gate 3: EV Telemetry
        if final_deliverables.get('wh_mi', 0) > 0:
            gates["gate_3"] = True

        # Gate 4: SummitOS Cards (Internal check)
        # Assuming we check for required fields that usually populate cards
        required_fields = ['trip_id', 'classification', 'distance_miles', 'duration_minutes']
        if all(final_deliverables.get(f) for f in required_fields):
            gates["gate_4"] = True

        # Gate 5: Sidecar Schema
        if "agent_versions" in final_deliverables and "orchestration_timestamp" in final_deliverables:
            gates["gate_5"] = True

        # Gate 6: Power BI Spec
        pbi_spec = final_deliverables.get('powerbi_spec', {})
        if pbi_spec.get('blueprint') and pbi_spec.get('visual_spec'):
            gates["gate_6"] = True

        verdict = all(gates.values())
        final_deliverables['compliance_gates'] = gates
        final_deliverables['compliance_verdict'] = "PASS" if verdict else "FAIL"
        
        if not verdict:
            logging.warning(f"Compliance Check FAILED: {gates}")
        else:
            logging.info("Compliance Check PASSED.")

        return final_deliverables
