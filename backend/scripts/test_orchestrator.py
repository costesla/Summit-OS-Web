import os
import sys
import logging
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.agent_orchestrator import SystemOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def test_modes():
    orchestrator = SystemOrchestrator()
    query = "Find an FSD segment with high normalized scores."
    
    print("\n================== [EVIDENCE MODE] ==================")
    print(orchestrator.process_query(query, "evidence"))
    
    print("\n================== [INSIGHT MODE] ===================")
    print(orchestrator.process_query(query, "insight"))
    
    print("\n================== [NARRATIVE MODE] =================")
    print(orchestrator.process_query(query, "narrative"))
    print("\n=====================================================")

if __name__ == "__main__":
    test_modes()
