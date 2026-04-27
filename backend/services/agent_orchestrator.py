import logging
from services.vector_store import VectorStore

class SystemOrchestrator:
    """
    Central brain of the Agentic SQL Vector System.
    Enforces the Prime Directive: Truth over convenience.
    """
    def __init__(self):
        self.vector_store = VectorStore()
        
    def process_query(self, query: str, mode: str) -> str:
        """
        Routes the query based on the explicit retrieval mode.
        """
        mode = mode.lower()
        logging.info(f"Processing query under {mode.upper()} mode: {query}")
        
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
