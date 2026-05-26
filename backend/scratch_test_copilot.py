import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from services.agent_orchestrator import SystemOrchestrator

orchestrator = SystemOrchestrator()

# Let's test a few queries that the user might have run
queries = [
    "what were my charging sessions on 5.20.26?",
    "charges on 2026-05-20",
    "charging sessions on May 20, 2026",
    "charging sessions yesterday" # Yesterday relative to May 21, 2026 (today)
]

for q in queries:
    print(f"\nQUERY: {q}")
    try:
        # We can use 'insight' mode which returns the direct structure
        res = orchestrator.process_query(q, mode="insight")
        import json
        print(json.dumps(res, indent=2, default=str))
    except Exception as e:
        print(f"Error: {e}")
