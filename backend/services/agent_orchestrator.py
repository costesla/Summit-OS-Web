import logging
from typing import Any
from services.vector_store import VectorStore
from services.database import DatabaseClient
from services.agents.summit_intelligence import (
    GovernedQueryRouter,
    TripsAgent,
    ChargingAgent,
    ExpensesAgent,
    VehicleAgent,
    MasterOrchestrator
)

class SystemOrchestrator:
    """
    Central brain of the Agentic SQL Vector System.
    Enforces the Prime Directive: Truth over convenience.
    Governs multi-agent execution domains and enforces schemas.
    """
    def __init__(self):
        self.vector_store = VectorStore()
        self.db = DatabaseClient()
        self.router = GovernedQueryRouter()
        self.orchestrator = MasterOrchestrator(self.db)
        
    def process_query(self, query: str, mode: str) -> Any:
        """
        Routes the query based on parsed domain intent first.
        If the query maps to governed business tables, runs under strict domain isolation.
        Otherwise falls back to vector store retrieval modes.
        """
        mode = mode.lower()
        logging.info(f"SystemOrchestrator: Processing query under {mode.upper()} mode: {query}")
        
        # 1. Parse intent & extract date filters via GovernedQueryRouter
        routing = self.router.parse_query(query)
        target = routing.get("target_agent")
        date_str = routing.get("date_str")
        start_date = routing.get("start_date")
        end_date = routing.get("end_date")
        
        logging.info(f"SystemOrchestrator: Parsed target_agent={target}, date={date_str}, range=[{start_date}, {end_date}]")
        
        # 2. Execute Isolated Governed Agents / Orchestrated aggregation
        if target == "orchestrator":
            data = self.orchestrator.aggregate_dashboard(date_str, start_date, end_date)
            return {
                "source": "orchestrator",
                "schema": "dashboard_schema",
                "data": data
            }
        elif target == "trips":
            agent = TripsAgent(self.db)
            data = agent.query(date_str, start_date, end_date)
            return {
                "source": "trips",
                "schema": "trip_schema",
                "data": data if data else "No data available"
            }
        elif target == "charging":
            agent = ChargingAgent(self.db)
            data = agent.query(date_str, start_date, end_date)
            return {
                "source": "charging",
                "schema": "charging_schema",
                "data": data if data else "No data available"
            }
        elif target == "expenses":
            agent = ExpensesAgent(self.db)
            data = agent.query(date_str, start_date, end_date)
            return {
                "source": "expenses",
                "schema": "expenses_schema",
                "data": data if data else "No data available"
            }
        elif target == "vehicle":
            agent = VehicleAgent(self.db)
            data = agent.query(date_str, start_date, end_date)
            return {
                "source": "vehicle",
                "schema": "vehicle_schema",
                "data": data if data else "No data available"
            }
            
        # 3. Fallback to classic Vector Store Retrieval Modes if no structured agent matches
        logging.info("SystemOrchestrator: No isolated business agent matched; falling back to Vector Store.")
        if mode == "evidence":
            results = self.vector_store.query_evidence_mode(query)
            if not results:
                return "Evidence Mode: No supporting verifiable data found. Hypothesis rejected."
            formatted = ["VERIFIABLE EVIDENCE FOUND:"]
            for r in results:
                formatted.append(f"- [Source: {r['source_pointer']}, Confidence: {r['search_confidence']:.2f}] {r['derivation_reason']}")
            return "\n".join(formatted)
            
        elif mode == "insight":
            return self.vector_store.query_insight_mode(query)
            
        elif mode == "narrative":
            return self.vector_store.query_narrative_mode(query)
            
        else:
            return "ERROR: Invalid mode. Must be 'evidence', 'insight', or 'narrative'."

