import logging
import os
import concurrent.futures
from typing import Dict, Any, Optional
from datetime import datetime

class OrchestratorHub:
    def __init__(self):
        from services.agents.accounting_agent import AccountingAgent
        from services.agents.ev_agent import EVEfficiencyAgent
        from services.agents.geo_agent import GeoAgent
        from services.powerbi_agent import PowerBIAgent
        from services.agents.compliance_agent import ComplianceAgent
        from services.agents.summarization_agent import SummarizationAgent
        from services.agents.sidecar_agent import SidecarAgent
        
        self.accounting = AccountingAgent()
        self.ev = EVEfficiencyAgent()
        self.geo = GeoAgent()
        self.pbi = PowerBIAgent()
        self.compliance = ComplianceAgent()
        self.summarizer = SummarizationAgent()
        self.sidecar = SidecarAgent()

    def orchestrate(self, extraction_data: Dict[str, Any], previous_trip: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes agents in parallel and consolidates results.
        """
        logging.info(f"Orchestrator: Starting parallel execution for {extraction_data.get('trip_id')}")
        
        # 1. Parallel Analytics Phase
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_accounting = executor.submit(self.accounting.process, extraction_data, previous_trip)
            future_ev = executor.submit(self.ev.process, extraction_data)
            future_geo = executor.submit(self.geo.process, extraction_data)
            future_pbi = executor.submit(self.pbi.process, extraction_data)

            accounting_metrics = future_accounting.result()
            ev_metrics = future_ev.result()
            geo_summary = future_geo.result()
            pbi_spec = future_pbi.result()

        # 2. Consolidation & Metadata
        final_deliverables = extraction_data.copy()
        final_deliverables.update(accounting_metrics)
        final_deliverables.update(ev_metrics)
        final_deliverables.update(geo_summary)
        final_deliverables['powerbi_spec'] = pbi_spec
        final_deliverables['orchestration_timestamp'] = datetime.now().isoformat()
        
        # 3. Compliance Verification Gate
        final_deliverables = self.compliance.verify(final_deliverables)
        
        # 4. Human-Readable Summarization
        final_deliverables['summit_cards_markdown'] = self.summarizer.generate(final_deliverables)
        
        # 5. Asset Finalization (Sidecar & Canonical Routing)
        output_path = self.sidecar.process(final_deliverables)
        final_deliverables['output_path'] = output_path
        
        # Write the human-readable report to the same path
        report_path = os.path.join(output_path, "Trip_Summary.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(final_deliverables['summit_cards_markdown'])

        return final_deliverables
