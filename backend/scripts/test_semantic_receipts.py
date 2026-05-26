import sys
import os

# Add backend directory to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.config_loader import config_loader
config_loader.load()

from services.vector_store import VectorStore

def test_search():
    vs = VectorStore()
    query = "Starbucks run"
    print(f"Searching for query: '{query}'...")
    results = vs.query_evidence_mode(query, n_results=5, confidence_threshold=0.40)
    
    print(f"\nFound {len(results)} results:")
    for i, r in enumerate(results, start=1):
        print(f"{i}. Confidence: {r.get('search_confidence') or 0.0:.4f}")
        print(f"   Pointer: {r.get('source_pointer')}")
        print(f"   Reason: {r.get('derivation_reason')}")
        print(f"   Source Type: {r.get('source_type')}")
        print()

if __name__ == "__main__":
    test_search()
