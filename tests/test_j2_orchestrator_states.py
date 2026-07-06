import time
import pytest
from astraeus.core.orchestrator import submit_multi_planet_search, get_job_status, cancel_job, JobState

def test_job_states():
    # 1. PENDING/RUNNING/DONE
    raw_lightcurve = {
        "time": [i * 0.1 for i in range(100)],
        "flux": [1.0] * 100,
        "target_name": "Test1"
    }
    
    # We will pass max_signals=1 to finish fast
    job_id = submit_multi_planet_search(raw_lightcurve, max_signals=1, snr_floor=3.0)
    
    status = get_job_status(job_id)
    assert status["status"] in [JobState.PENDING, JobState.RUNNING, JobState.DONE]
    
    # Wait for done
    timeout = 45
    start = time.time()
    while time.time() - start < timeout:
        status = get_job_status(job_id)
        if status["status"] in [JobState.DONE, JobState.FAILED, JobState.CANCELLED]:
            break
        time.sleep(0.5)
        
    assert status["status"] == JobState.DONE

def test_job_failed():
    # 2. FAILED state via malformed input
    raw_lightcurve = {
        "time": [1.0, 2.0],  # Insufficient data points
        "flux": [1.0, 1.0],
        "target_name": "Test2"
    }
    
    job_id = submit_multi_planet_search(raw_lightcurve, max_signals=1, snr_floor=3.0)
    
    timeout = 30
    start = time.time()
    while time.time() - start < timeout:
        status = get_job_status(job_id)
        if status["status"] in [JobState.FAILED, JobState.DONE]:
            break
        time.sleep(0.1)
        
    assert status["status"] == JobState.FAILED
    assert "Insufficient data points" in status["error"]

def test_job_cancelled():
    # 3. CANCELLED state
    raw_lightcurve = {
        "time": [i * 0.1 for i in range(1000)],
        "flux": [1.0] * 1000,
        "target_name": "Test3"
    }
    
    job_id = submit_multi_planet_search(raw_lightcurve, max_signals=10, snr_floor=3.0)
    
    cancel_job(job_id)
    
    timeout = 30
    start = time.time()
    while time.time() - start < timeout:
        status = get_job_status(job_id)
        if status["status"] == JobState.CANCELLED:
            break
        time.sleep(0.1)
        
    assert status["status"] == JobState.CANCELLED
