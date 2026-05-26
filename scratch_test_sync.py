import os
import sys
import json
import logging
from datetime import datetime

# Setup logging to stdout
logging.basicConfig(level=logging.INFO)

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    print(f"Loading environment from {settings_path}")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

# Add backend to sys.path
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# Mock azure.functions.HttpRequest
class MockHttpRequest:
    def __init__(self, body, method='POST', params=None):
        self._body = json.dumps(body).encode('utf-8')
        self.method = method
        self.params = params or {}
        self.headers = {'Origin': 'http://localhost:3000'}

    def get_body(self):
        return self._body

    def get_json(self):
        return json.loads(self._body.decode('utf-8'))

try:
    from api.operations import daily_sync
    
    # Let's run daily_sync for a sample date, say '2026-05-19'
    req = MockHttpRequest(body={'date': '2026-05-19'})
    print("Invoking daily_sync locally...")
    response = daily_sync(req)
    
    print("\n--- Response ---")
    print(f"Status Code: {response.status_code}")
    print(f"MimeType: {response.mimetype}")
    print("Body:")
    print(response.get_body().decode('utf-8'))
except Exception as e:
    import traceback
    traceback.print_exc()
