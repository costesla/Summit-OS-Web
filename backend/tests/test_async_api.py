import os
import sys
import json
import pytest
from unittest.mock import MagicMock

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from api.operations import run_async_job, get_job_status, sync_folders, trigger_cloud_scan
from services.job_tracker import JobTracker

class MockHttpRequest:
    def __init__(self, method="GET", body=b"", route_params=None, params=None, headers=None):
        self.method = method
        self._body = body
        self.route_params = route_params or {}
        self.params = params or {}
        self.headers = headers or {}

    def get_body(self):
        return self._body

    def get_json(self):
        return json.loads(self._body.decode("utf-8"))

def test_run_async_job_schema():
    # Test that run_async_job conforms to C1 standard async response schema
    def dummy_task(arg1, kwarg1=None):
        return {"logs": ["dummy step done"]}
        
    res = run_async_job("Dummy Tool", dummy_task, "arg1_val", kwarg1="kwarg1_val")
    
    assert res["status"] == "accepted"
    assert res["execution"] == "async"
    assert "jobId" in res
    assert res["jobId"].startswith("job_")
    assert res["errorType"] is None

def test_get_job_status_c2_schema():
    tracker = JobTracker()
    job_id = tracker.create_job("C2 Schema Test")
    
    # Mock HttpRequest for job-status/{job_id}
    req = MockHttpRequest(method="GET", route_params={"job_id": job_id})
    resp = get_job_status(req)
    
    assert resp.status_code == 200
    data = json.loads(resp.get_body().decode("utf-8"))
    
    # Assert C2 Schema keys
    assert data["jobId"] == job_id
    assert data["status"] == "queued"
    assert "startedAt" in data
    assert "finishedAt" in data
    assert "errorType" in data
    assert "message" in data
    assert "logs" in data
    assert "result" in data

def test_endpoint_sync_folders_async_trigger():
    # Mock HttpRequest for operations/sync-folders
    body_data = json.dumps({"processDate": "2026-05-22", "dryRun": True})
    req = MockHttpRequest(method="POST", body=body_data.encode("utf-8"))
    
    resp = sync_folders(req)
    
    # C1: Returns HTTP 202 accepted for background operations
    assert resp.status_code == 202
    data = json.loads(resp.get_body().decode("utf-8"))
    
    assert data["status"] == "accepted"
    assert data["execution"] == "async"
    assert "jobId" in data
    assert data["errorType"] is None
