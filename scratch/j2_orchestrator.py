import concurrent.futures
import threading
import uuid
import numpy as np

# Global Executor and Registry
_executor = concurrent.futures.ProcessPoolExecutor(max_workers=4)
JOB_REGISTRY = {}
JOB_LOCK = threading.Lock()

class JobState:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

def get_job_status(job_id: str) -> dict:
    with JOB_LOCK:
        if job_id not in JOB_REGISTRY:
            return None
        return dict(JOB_REGISTRY[job_id])

def cancel_job(job_id: str):
    with JOB_LOCK:
        if job_id in JOB_REGISTRY:
            status = JOB_REGISTRY[job_id]["status"]
            if status in [JobState.PENDING, JobState.RUNNING]:
                JOB_REGISTRY[job_id]["status"] = JobState.CANCELLED

def submit_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1) -> str:
    job_id = str(uuid.uuid4())
    
    # Extract basic info quickly
    target = raw_lightcurve.get('target_name', 'Unknown') if isinstance(raw_lightcurve, dict) else getattr(raw_lightcurve, 'target_name', 'Unknown')
    
    with JOB_LOCK:
        JOB_REGISTRY[job_id] = {
            "status": JobState.PENDING,
            "target": target,
            "iteration": 0,
            "max_signals": max_signals,
            "candidates": [],
            "error": None
        }
        
    thread = threading.Thread(
        target=_async_search_worker,
        args=(job_id, raw_lightcurve, max_signals, snr_floor),
        daemon=True
    )
    thread.start()
    return job_id

def _async_search_worker(job_id, raw_lightcurve, max_signals, snr_floor):
    try:
        from astraeus.analysis.detection import detect_transit_candidate
        from astraeus.core.orchestrator import subtract_planetary_signal
        
        with JOB_LOCK:
            if JOB_REGISTRY[job_id]["status"] == JobState.CANCELLED:
                return
            JOB_REGISTRY[job_id]["status"] = JobState.RUNNING

        # Extract time and flux from raw_lightcurve
        if isinstance(raw_lightcurve, dict):
            time_arr = np.asarray(raw_lightcurve.get('time', []), dtype=np.float64)
            flux = np.asarray(raw_lightcurve.get('flux', []), dtype=np.float64)
            target_name = raw_lightcurve.get('target_name', 'Unknown')
            data_source = raw_lightcurve.get('data_source', 'Unknown')
            metadata = raw_lightcurve.get('metadata', {})
        else:
            time_arr = np.asarray(getattr(raw_lightcurve, 'time', []), dtype=np.float64)
            flux = np.asarray(getattr(raw_lightcurve, 'flux', []), dtype=np.float64)
            target_name = getattr(raw_lightcurve, 'target_name', 'Unknown')
            data_source = getattr(raw_lightcurve, 'data_source', 'Unknown')
            metadata = getattr(raw_lightcurve, 'metadata', {})
            
        # Simulating malformed input check for test_j2
        if len(time_arr) < 10 or len(flux) < 10:
            raise ValueError("Insufficient data points")
            
        discovered_planetary_properties = []
        discovered_periods = []
        
        active_time = time_arr.copy()
        current_working_flux = flux.copy()
        
        duplicate_retries = 0
        max_duplicate_retries = 3
        _GUARDRAIL1_MARGINAL_TOLERANCE = 3
        guardrail1_consecutive_marginal = 0
        iteration = 0
        
        while len(discovered_planetary_properties) < max_signals:
            iteration += 1
            if iteration > max_signals + max_duplicate_retries:
                break
                
            # Cancellation Check
            with JOB_LOCK:
                if JOB_REGISTRY[job_id]["status"] == JobState.CANCELLED:
                    return
                JOB_REGISTRY[job_id]["iteration"] = iteration
            
            # Offload heavy BLS/TLS to ProcessPoolExecutor
            future = _executor.submit(
                detect_transit_candidate,
                active_time, current_working_flux, target_name, data_source, metadata, snr_floor, discovered_periods
            )
            
            # Wait for future but check cancellation periodically
            while not future.done():
                with JOB_LOCK:
                    if JOB_REGISTRY[job_id]["status"] == JobState.CANCELLED:
                        # Process pool tasks can't always be cancelled if running, 
                        # but we can just walk away
                        return
                import time as t
                t.sleep(0.5)
                
            result = future.result()
            
            snr = result.get('snr', 0.0)
            vetting_status = result.get('vetting_status', '')
            best_period = result.get('period', 0.0)
            transit_time = result.get('t0')
            duration = result.get('duration')
            depth = result.get('depth')
            
            # --- SAME LOGIC AS run_multi_planet_search ---
            if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate"):
                guardrail1_consecutive_marginal += 1
                if (best_period is not None and transit_time is not None
                        and duration is not None and depth is not None
                        and guardrail1_consecutive_marginal < _GUARDRAIL1_MARGINAL_TOLERANCE):
                    depth_ppm = depth * 1e6
                    current_working_flux = subtract_planetary_signal(
                        current_working_flux, active_time, best_period, transit_time, duration, depth_ppm, metadata
                    )
                if guardrail1_consecutive_marginal >= _GUARDRAIL1_MARGINAL_TOLERANCE:
                    break
                continue
                
            guardrail1_consecutive_marginal = 0
            
            is_duplicate = False
            for prev_idx, prev_period in enumerate(discovered_periods):
                period_ratio = best_period / prev_period if prev_period > 0 else 0
                if abs(period_ratio - 1.0) < 0.05:
                    is_duplicate = True
                    break
                for harmonic in [0.5, 2.0]:
                    if abs(period_ratio - harmonic) < 0.05:
                        is_duplicate = True
                        break
                if is_duplicate:
                    break
                    
            if is_duplicate:
                duplicate_retries += 1
                if duplicate_retries > max_duplicate_retries:
                    break
                if best_period is not None and transit_time is not None and duration is not None and depth is not None:
                    depth_ppm = depth * 1e6
                    current_working_flux = subtract_planetary_signal(
                        current_working_flux, active_time, best_period, transit_time, duration, depth_ppm, metadata
                    )
                continue
                
            # Accept candidate
            discovered_planetary_properties.append(result)
            discovered_periods.append(best_period)
            
            with JOB_LOCK:
                JOB_REGISTRY[job_id]["candidates"].append(result)
                
            if best_period is not None and transit_time is not None and duration is not None and depth is not None:
                depth_ppm = depth * 1e6
                current_working_flux = subtract_planetary_signal(
                    current_working_flux, active_time, best_period, transit_time, duration, depth_ppm, metadata
                )
            else:
                break
                
        with JOB_LOCK:
            if JOB_REGISTRY[job_id]["status"] != JobState.CANCELLED:
                JOB_REGISTRY[job_id]["status"] = JobState.DONE

    except Exception as e:
        with JOB_LOCK:
            JOB_REGISTRY[job_id]["status"] = JobState.FAILED
            JOB_REGISTRY[job_id]["error"] = str(e)
