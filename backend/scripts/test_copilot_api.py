import os
import sys
import logging
import json
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from api.copilot import copilot_agentic_query
import azure.functions as func

logging.basicConfig(level=logging.INFO, format='%(message)s')

class MockRequest(func.HttpRequest):
    def __init__(self, method, url, params, headers=None):
        super().__init__(
            method=method,
            url=url,
            headers=headers or {},
            body=b'',
            route_params={}
        )
        self._params = params
        
    @property
    def params(self):
        return self._params
        
    def get_body(self):
        return b''

def simulate_copilot_request():
    print("===================================================================")
    print("           SIMULATING MICROSOFT COPILOT STUDIO REQUEST             ")
    print("===================================================================")
    
    # Simulate Copilot hitting the new endpoint
    query = "Find an FSD segment with high normalized scores."
    
    print(f"\n[COPILOT SENDS]: GET /copilot/agentic-query?mode=evidence&q={query}\n")
    
    req = MockRequest(
        method="GET",
        url="http://localhost:7071/api/copilot/agentic-query",
        params={"q": query, "mode": "evidence"}
    )
    
    # Directly invoke the Azure Function route handler
    response = copilot_agentic_query(req)
    
    print("[API RETURNS TO COPILOT]:")
    print(f"Status Code: {response.status_code}")
    print(json.dumps(json.loads(response.get_body()), indent=2))
    print("===================================================================")

if __name__ == "__main__":
    simulate_copilot_request()
