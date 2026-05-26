import os
import sys
import pytest

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.job_tracker import JobTracker

def test_job_tracker_singleton():
    tracker1 = JobTracker()
    tracker2 = JobTracker()
    assert tracker1 is tracker2

def test_create_and_get_job():
    tracker = JobTracker()
    job_id = tracker.create_job("Test Tool", target_path="test/path")
    
    assert job_id is not None
    assert job_id.startswith("job_")
    
    job_data = tracker.get_job(job_id)
    assert job_data is not None
    assert job_data["jobId"] == job_id
    assert job_data["operation"] == "Test Tool"
    assert job_data["targetPath"] == "test/path"
    assert job_data["status"] == "queued"  # B1: queued is the initial state

def test_job_lifecycle_transitions():
    tracker = JobTracker()
    job_id = tracker.create_job("Test Lifecycle")
    
    # 1. Start Job -> Transition to running
    tracker.start_job(job_id)
    job_data = tracker.get_job(job_id)
    assert job_data["status"] == "running"
    assert job_data["startedAt"] is not None
    assert len(job_data["logs"]) == 2  # initial + started logs
    
    # 2. Update Progress
    tracker.update_job_progress(job_id, "running", ["Progress log 1"])
    job_data = tracker.get_job(job_id)
    assert job_data["status"] == "running"
    assert "Progress log 1" in job_data["logs"]
    
    # 3. Complete Job -> Transition to completed
    result_payload = {"success": True, "trip_count": 5}
    tracker.update_job_progress(job_id, "completed", ["Success done!"], result=result_payload)
    job_data = tracker.get_job(job_id)
    assert job_data["status"] == "completed"
    assert job_data["finishedAt"] is not None
    assert job_data["durationMs"] is not None
    assert job_data["result"] == result_payload
    assert job_data["errorType"] is None

def test_job_failure_state():
    tracker = JobTracker()
    job_id = tracker.create_job("Test Failure")
    
    tracker.start_job(job_id)
    tracker.update_job_progress(job_id, "failed", ["Failing now!"], error="Timeout Connection Error")
    
    job_data = tracker.get_job(job_id)
    assert job_data["status"] == "failed"
    assert job_data["finishedAt"] is not None
    assert job_data["errorType"] == "ExecutionError"
    assert job_data["message"] == "Timeout Connection Error"
