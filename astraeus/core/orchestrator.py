import numpy as np
import json

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.core.capabilities import (
    SUBTRACTION_BACKEND_BATMAN,
    SUBTRACTION_BACKEND_TRAPEZOID,
    BackendId,
    BackendUnavailable,
    TlsOutcome,
    get_logger,
    is_backend_available,
)

logger = get_logger("orchestrator")


def subtract_planetary_signal(flux, time, period, epoch, duration, depth_ppm, metadata=None, record=None):
    """
    Subtracts the transit signal of a planet from the flux timeline without altering noise.
    Uses a hybrid approach: attempts batman-package high-precision subtraction first, 
    and falls back to a custom Trapezoidal model if batman fails or is unavailable.
    
    Args:
        flux (np.ndarray): The flux array.
        time (np.ndarray): The time array.
        period (float): The orbital period of the planet.
        epoch (float): The transit midpoint (t0).
        duration (float): The transit duration.
        depth_ppm (float): The transit depth in parts-per-million.
        metadata (dict, optional): Target metadata (stellar parameters, etc.).
        record (dict, optional): If given, populated with the subtraction
            provenance under ``subtraction_backend`` (``"batman"`` or
            ``"trapezoid"``) and ``subtraction_backend_available``. This
            is how Phase 0 makes a fallback execution distinguishable
            from the preferred scientific backend (PRD §10) without
            changing the function's return contract.
        
    Returns:
        np.ndarray: The new flux array with the transit signal subtracted.
    """
    cleaned_flux = flux.copy()

    def _record(backend: str, available: bool) -> None:
        if record is not None:
            record["subtraction_backend"] = backend
            record["subtraction_backend_available"] = available

    # Dynamic window scaling: Add 25% safety buffer on each wing (50% total increase)
    padded_duration = duration * 1.5
    logger.info(
        "Dynamically scaling subtraction window: BLS duration %.4fd -> %.4fd "
        "(25%% padding on wings)", duration, padded_duration,
    )
    duration = padded_duration

    # PHASE 0 (PRD v4.1 §10): batman availability is probed explicitly
    # so the two failure modes are distinguishable and observable:
    # "not installed" is an environment state; "installed but raised"
    # is a runtime failure. Previously a single broad `except Exception`
    # merged the two and hid both behind one message.
    batman_available = is_backend_available(BackendId.BATMAN)

    if batman_available:
        try:
            import batman
            logger.info("Initializing high-precision batman engine for period %.3f", period)

            # Initialize batman parameters
            params = batman.TransitParams()
            params.t0 = epoch
            params.per = period
            params.rp = np.sqrt(depth_ppm / 1e6)

            # Estimate semi-major axis 'a' from duration and period
            # Using small angle approximation: a = period / (pi * duration)
            params.a = max(1.0, period / (np.pi * duration))
            params.inc = 90.
            params.ecc = 0.
            params.w = 90.

            # Attempt to get limb darkening from metadata, else default
            if metadata and 'u' in metadata:
                params.u = metadata['u']
            else:
                params.u = [0.1, 0.3]

            params.limb_dark = "quadratic"

            # Generate model
            m = batman.TransitModel(params, time)
            transit_model = m.light_curve(params)

            # batman returns relative flux where out of transit is 1.0.
            # We need to add the dip (1.0 - transit_model) to our flux to flatten it.
            cleaned_flux += (1.0 - transit_model)
            _record(SUBTRACTION_BACKEND_BATMAN, True)
            return cleaned_flux

        except Exception as e:
            # INSTALLED-BUT-FAILING backend. This is not a silent
            # substitution: it is logged at ERROR, and the trapezoid
            # result is labelled as such via _record() so no caller can
            # mistake it for a batman subtraction (PRD §9 / §10).
            logger.error(
                "[BATMAN] Installed batman backend failed during signal "
                "subtraction (%s: %s). The trapezoid fallback differs "
                "scientifically (zero limb darkening, no curvature); the "
                "result is recorded as a trapezoid subtraction, NOT as "
                "batman.", type(e).__name__, e,
            )

    elif not batman_available:
        # batman is GPL-3.0 and its adoption is an unresolved user-level
        # licensing decision (PRD §13.3). It is therefore NOT a hard
        # runtime dependency, and its absence is not a failure -- but it
        # must be visible, because the trapezoid model is a scientific
        # regression, not a cosmetic fallback.
        logger.warning(
            "[BATMAN] batman is not installed; using the trapezoid "
            "subtraction model. This is a scientifically different model "
            "(zero limb darkening, hardcoded 10%% ingress ramps, no "
            "curvature) and is recorded as such. See PRD §13.3 for the "
            "licensing decision that would make batman mandatory."
        )

    # Fallback Countermeasure (Trapezoidal Engine)
    _record(SUBTRACTION_BACKEND_TRAPEZOID, batman_available)
    # Shift time by epoch to center the transit at phase 0
    phase = (time - epoch + 0.5 * period) % period - 0.5 * period
    abs_phase = np.abs(phase)

    # Compute linear ingress and egress ramps (defaulting to 10% of total transit duration)
    ramp_duration = 0.1 * duration
    flat_duration = duration - 2 * ramp_duration

    transit_dip = depth_ppm / 1e6
    trapezoid_model = np.zeros_like(flux)

    # Flat bottom
    in_flat = abs_phase <= (flat_duration / 2.0)
    trapezoid_model[in_flat] = transit_dip

    # Ingress / Egress ramps
    in_ramp = (abs_phase > (flat_duration / 2.0)) & (abs_phase <= (duration / 2.0))
    ramp_x = abs_phase[in_ramp] - (flat_duration / 2.0)
    trapezoid_model[in_ramp] = transit_dip * (1.0 - (ramp_x / ramp_duration))

    # Add the trapezoidal dip to flatten the transit
    cleaned_flux += trapezoid_model

    return cleaned_flux

def run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1, on_event=None):
    """
    Orchestrator wrapper to perform a multi-planet search on a given lightcurve.
    This tracks the iteration count and maintains the 'current_working_flux' state.

    Args:
        raw_lightcurve (dict or object): Contains at least 'time' and 'flux' arrays.
        max_signals (int): Maximum number of planets/signals to search for.
        snr_floor (float): The minimum SNR threshold for considering a candidate valid.
        on_event (callable, optional): P1-F worker hook.  Called as
            ``on_event(event_type, **payload)`` at each lifecycle point using
            the stable JSONL vocabulary of ``astraeus.jobs.events``
            (running / iteration / candidate / warning / done).  The loop's
            behaviour is identical with or without a subscriber; the hook is
            how the worker subprocess reports *measured* progress instead of
            a fake bar (PRD v4.1 §5.1, §18).

    Returns:
        list: A list of discovered planetary properties (dictionaries).
    """
    def _emit(event_type, **payload):
        # No-op without a subscriber: the loop stays usable in-process.
        if on_event is not None:
            try:
                on_event(event_type, **payload)
            except Exception:  # pragma: no cover - telemetry must never break a run
                pass

    _emit("running", max_signals=max_signals, snr_floor=snr_floor)
    # Extract time and flux from raw_lightcurve
    if isinstance(raw_lightcurve, dict):
        time = np.asarray(raw_lightcurve.get('time', []), dtype=np.float64)
        flux = np.asarray(raw_lightcurve.get('flux', []), dtype=np.float64)
        target_name = raw_lightcurve.get('target_name', 'Unknown')
        data_source = raw_lightcurve.get('data_source', 'Unknown')
        metadata = raw_lightcurve.get('metadata', {})
    else:
        # Fallback assuming object notation
        time = np.asarray(getattr(raw_lightcurve, 'time', []), dtype=np.float64)
        flux = np.asarray(getattr(raw_lightcurve, 'flux', []), dtype=np.float64)
        target_name = getattr(raw_lightcurve, 'target_name', 'Unknown')
        data_source = getattr(raw_lightcurve, 'data_source', 'Unknown')
        metadata = getattr(raw_lightcurve, 'metadata', {})
        
    discovered_planetary_properties = []
    discovered_periods = []  # Track periods for duplicate detection
    
    # State tracking
    active_time = time.copy()
    current_working_flux = flux.copy()
    
    duplicate_retries = 0
    max_duplicate_retries = 3  # Max times we retry after finding a duplicate before giving up
    
    iteration = 0
    while len(discovered_planetary_properties) < max_signals:
        iteration += 1
        if iteration > max_signals + max_duplicate_retries:
            print(f"[Orchestrator] Maximum iteration budget exhausted ({iteration - 1} iterations). Stopping.")
            _emit("warning", code="ITERATION_BUDGET_EXHAUSTED",
                  message=f"iteration budget exhausted after {iteration - 1} iterations")
            break
            
        if len(active_time) < 10:
            print(f"[Orchestrator] Insufficient data points ({len(active_time)}). Stopping.")
            break
        
        print(f"\n{'='*70}")
        print(f"[Orchestrator] === ITERATION {iteration} === (Found {len(discovered_planetary_properties)}/{max_signals} candidates)")
        print(f"{'='*70}")
        # SEARCHING is the dominant cost (~150 s serial TLS on Kepler-90),
        # so iteration count is the one progress signal that is actually
        # meaningful (PRD §5.1 progress table).
        _emit("iteration", iteration=iteration,
              max_iterations=max_signals + max_duplicate_retries,
              found=len(discovered_planetary_properties), max_signals=max_signals)
            
        # We wrap the existing main pipeline execution function
        # detect_transit_candidate returns a dictionary with candidate information
        result = detect_transit_candidate(
            time=active_time,
            flux=current_working_flux,
            target_name=target_name,
            data_source=data_source,
            metadata=metadata,
            snr_threshold=snr_floor,
            known_periods=discovered_periods
        )
        
        # Read the returned dictionary from the run. Extract the calculated SNR and vetting status.
        snr = result.get('snr', 0.0)
        vetting_status = result.get('vetting_status', '')
        best_period = result.get('period', 0.0)
        transit_time = result.get('t0')
        duration = result.get('duration')
        depth = result.get('depth')
        
        print(f"[Orchestrator] Iteration {iteration} result: Period={best_period:.4f}d, SNR={snr:.2f}, Duration={duration:.4f}d, Depth={depth:.6f}, Status={vetting_status}")

        # PHASE 0 FAIL-CLOSED GATE (PRD v4.1 §4.2 / §4.3 / §7).
        # Before this, the orchestrator never read tls_environment_error
        # or tls_scientific_error, so an infrastructure failure ended the
        # run as DONE with `candidates: []` and `error: None` -- every
        # "no planets found" result was indistinguishable from a broken
        # pipeline. Now: if the required TLS gate could not EXECUTE, the
        # run fails closed with a structured reason. This is an
        # environment failure, not a scientific negative, and it must
        # never be reported as "zero candidates".
        if result.get('tls_outcome') == TlsOutcome.ENV_UNAVAILABLE.value:
            reason = result.get('tls_environment_error') or "TLS gate could not execute"
            logger.error(
                "[Orchestrator] The required TLS cross-validation gate "
                "could not execute (environment failure: %s). Halting and "
                "failing closed: this is NOT 'no candidates found'.", reason,
            )
            raise BackendUnavailable(BackendId.TLS, reason)

        # GUARDRAIL 1 (The SNR/Vetting Break)
        # R8 fix (2026-07-12): also require tls_valid=True on the accept
        # path. The VettingEngine's "Likely Planet" override in
        # detection.py:328 can still set vetting_status to "Verified Planet
        # Candidate" on TLS-rejected candidates (the R8 detector-level fix
        # in detection.py now also requires is_valid, but defense-in-depth
        # at the orchestrator level is the safer guarantee that the load-
        # bearing TLS gate cannot be bypassed by a future classifier
        # override reintroducing a "Verified Planet Candidate*" string).
        # This is the "option (b)" defense-in-depth described in
        # scratch/r8_repro_vetting_override.py:35-42.
        tls_valid = bool(result.get('tls_valid', False))
        if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate") or not tls_valid:
            if not tls_valid and vetting_status.startswith("Verified Planet Candidate"):
                print(f"[Orchestrator] TLS-rejected candidate bypassed the classifier gate (SNR={snr:.2f}, tls_valid={tls_valid}, status='{vetting_status}'). Halting to preserve the load-bearing TLS gate (R8 fix).")
                _emit("warning", code="TLS_REJECTED_BYPASS",
                      message="TLS-rejected candidate bypassed the classifier gate; halting")
            else:
                print(f"[Orchestrator] Signal significance floor reached (SNR={snr:.2f}, status='{vetting_status}'). Halting iterative search.")
                _emit("warning", code="SNR_FLOOR_REACHED",
                      message=f"significance floor reached (SNR={snr:.2f}, status='{vetting_status}')")
            break
        
        # GUARDRAIL 2 (Duplicate Period Detection)
        is_duplicate = False
        for prev_idx, prev_period in enumerate(discovered_periods):
            period_ratio = best_period / prev_period if prev_period > 0 else 0
            # Check if within 5% of a previous period OR a near-integer harmonic
            if abs(period_ratio - 1.0) < 0.05:
                print(f"[Orchestrator] DUPLICATE DETECTED: Period {best_period:.4f}d is within 5% of previously found {prev_period:.4f}d (candidate #{prev_idx + 1}). Skipping.")
                is_duplicate = True
                break
            # Also check half/double harmonics
            for harmonic in [0.5, 2.0]:
                if abs(period_ratio - harmonic) < 0.05:
                    print(f"[Orchestrator] HARMONIC DUPLICATE DETECTED: Period {best_period:.4f}d is a {harmonic}x harmonic of {prev_period:.4f}d. Skipping.")
                    is_duplicate = True
                    break
            if is_duplicate:
                break
        
        if is_duplicate:
            duplicate_retries += 1
            if duplicate_retries > max_duplicate_retries:
                print(f"[Orchestrator] Too many duplicate detections ({duplicate_retries}). Residual signal likely not erasable. Stopping.")
                break
            # Still subtract the signal to erode the residual, then continue
            if best_period is not None and transit_time is not None and duration is not None and depth is not None:
                depth_ppm = depth * 1e6
                current_working_flux = subtract_planetary_signal(
                    flux=current_working_flux,
                    time=active_time,
                    period=best_period,
                    epoch=transit_time,
                    duration=duration,
                    depth_ppm=depth_ppm,
                    metadata=metadata
                )
                print(f"[Orchestrator] Re-subtracted duplicate signal at {best_period:.4f}d to further erode residual.")
            continue
            
        # GUARDRAIL 3 (The Counter) - Accept unique candidate
        discovered_planetary_properties.append(result)
        discovered_periods.append(best_period)
        print(f"[Orchestrator] [OK] ACCEPTED candidate #{len(discovered_planetary_properties)}: Period={best_period:.4f}d")
        _emit("candidate", index=len(discovered_planetary_properties) - 1,
              period_days=float(best_period) if best_period is not None else None,
              snr=float(snr), vetting_status=str(vetting_status))

        # Subtract the transit out of the current_working_flux for the next iteration
        if best_period is not None and transit_time is not None and duration is not None and depth is not None:
            depth_ppm = depth * 1e6
            # `record=result` stamps the accepted candidate with which
            # subtraction backend actually ran (batman vs trapezoid),
            # so a fallback execution is never represented as the
            # preferred scientific backend (PRD §10).
            current_working_flux = subtract_planetary_signal(
                flux=current_working_flux,
                time=active_time,
                period=best_period,
                epoch=transit_time,
                duration=duration,
                depth_ppm=depth_ppm,
                metadata=metadata,
                record=result,
            )
        else:
            # If we don't have enough info to mask, we must break to prevent infinite loops finding the same signal
            print(f"[Orchestrator] Insufficient transit parameters to subtract. Stopping.")
            break
    
    # Final summary
    print(f"\n{'='*70}")
    print(f"[Orchestrator] SEARCH COMPLETE: {len(discovered_planetary_properties)} unique candidates found in {iteration} iterations.")
    print(f"{'='*70}")
    for idx, prop in enumerate(discovered_planetary_properties):
        print(f"  Candidate #{idx+1}: Period={prop.get('period', 0):.4f}d, SNR={prop.get('snr', 0):.2f}, Depth={prop.get('depth', 0):.6f}")
    
    # Print consolidated JSON
    # Build a serializable version (strip non-JSON-serializable fields like periodogram arrays)
    serializable_results = []
    for prop in discovered_planetary_properties:
        clean = {}
        for k, v in prop.items():
            if k == 'periodogram':
                continue  # Skip large array data
            elif k == 'ttv_data':
                continue  # Skip nested complex data
            elif isinstance(v, (np.integer,)):
                clean[k] = int(v)
            elif isinstance(v, (np.floating,)):
                clean[k] = float(v)
            elif isinstance(v, np.ndarray):
                continue
            else:
                clean[k] = v
        serializable_results.append(clean)
    
    print(f"\n[Orchestrator] Consolidated Discovery Payload:")
    print(json.dumps(serializable_results, indent=2))

    _emit("done", n_candidates=len(discovered_planetary_properties),
          n_iterations=iteration, all_peaks_rejected=len(discovered_planetary_properties) == 0)

    return discovered_planetary_properties

import multiprocessing
import threading
import uuid
import time as _time
import queue

# Global Registry
JOB_REGISTRY = {}
JOB_LOCK = threading.Lock()


class JobState:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def get_job_status(job_id: str) -> dict:
    """Return a snapshot of a job's state, or None if job_id is unknown."""
    with JOB_LOCK:
        if job_id not in JOB_REGISTRY:
            return None
        entry = JOB_REGISTRY[job_id]
        return {k: v for k, v in entry.items() if not k.startswith("_")}


def cancel_job(job_id: str):
    """Hard-cancel a running or pending job by terminating its subprocess."""
    with JOB_LOCK:
        if job_id not in JOB_REGISTRY:
            return
        entry = JOB_REGISTRY[job_id]
        if entry["status"] not in (JobState.PENDING, JobState.RUNNING):
            return
        entry["status"] = JobState.CANCELLED
        proc = entry.get("_process")

    # Terminate outside the lock to avoid holding it during join()
    if proc is not None and proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)


# ---------------------------------------------------------------------------
# Subprocess worker  (module-level function — must be picklable)
# ---------------------------------------------------------------------------
def _subprocess_search_worker(result_queue, raw_lightcurve, max_signals, snr_floor):
    """
    Runs the multi-planet detection loop inside a child process, reporting
    progress over *result_queue*.

    P1-I (PRD v4.1 §2.5): this is an **adapter**, not a second copy of the
    search loop.  The sync and async paths had drifted apart -- most
    importantly GUARDRAIL 1, which retried marginal candidates with
    subtraction here while breaking immediately in
    ``run_multi_planet_search``.  Two copies of a load-bearing scientific
    guardrail is how a bypass silently reappears in one path and not the
    other (the exact R8 vetting-override class of bug this codebase has
    already been burned by).  Now there is one implementation, and this
    function only:

    * enforces the async path's own contract -- insufficient data is a
      FAILED job with a reason, not an empty result list (the sync loop
      treats it as "stop and return []"; ``_monitor_worker``'s callers
      depend on the distinction, see ``tests/test_j2_orchestrator_states``);
    * translates the single loop's ``on_event`` progress into the queue
      messages the monitor thread expects;
    * converts the sync loop's fail-closed exception (``BackendUnavailable``)
      back into the queue's terminal error message.

    The sync semantics are authoritative: they are the path real data and
    the P1-F worker use, so unifying onto them is what "retire the drift"
    means (PRD §2.5, §16).

    Communicates back to the parent via *result_queue*:
        {'type': 'running'}                     - worker has started
        {'type': 'iteration', 'iteration': int} - beginning iteration n
        {'type': 'candidate', 'data': dict}     - accepted candidate
        {'type': 'done'}                        - search finished normally
        {'type': 'error', 'error': str}         - search failed
    """
    try:
        if isinstance(raw_lightcurve, dict):
            time_arr = np.asarray(raw_lightcurve.get("time", []), dtype=np.float64)
            flux = np.asarray(raw_lightcurve.get("flux", []), dtype=np.float64)
        else:
            time_arr = np.asarray(getattr(raw_lightcurve, "time", []), dtype=np.float64)
            flux = np.asarray(getattr(raw_lightcurve, "flux", []), dtype=np.float64)

        # The sync loop treats short arrays as "stop and return []"; the
        # async contract is a FAILED job with a reason the monitor can show.
        if len(time_arr) < 10 or len(flux) < 10:
            raise ValueError("Insufficient data points")

        result_queue.put({"type": "running"})

        def _to_queue(event_type, **payload):
            # Forward only *measured* progress.  Candidate records are emitted
            # from the returned list below, which carries the full per-result
            # payload the monitor's callers expect; the loop's candidate
            # event is a progress signal, not the record.
            if event_type == "iteration":
                result_queue.put({"type": "iteration", "iteration": payload.get("iteration", 0)})

        # One implementation of the search loop.  Guardrails, the fail-closed
        # TLS gate and iteration accounting all live in
        # run_multi_planet_search; this process cannot and must not diverge
        # from them (P1-I).
        discovered = run_multi_planet_search(
            raw_lightcurve,
            max_signals=max_signals,
            snr_floor=snr_floor,
            on_event=_to_queue,
        )
        for result in discovered:
            result_queue.put({"type": "candidate", "data": result})

        result_queue.put({"type": "done"})

    except BackendUnavailable as exc:
        # The sync loop raises; the async contract reports a terminal error
        # with the reason.  Both mean FAILED, never "DONE / 0 candidates"
        # (PRD §4.2 / §4.3).
        result_queue.put({
            "type": "error",
            "error": (
                f"Required scientific backend unavailable: "
                f"{exc}. The cross-validation gate could not execute; this "
                f"job is FAILED, not 'no candidates found'."
            ),
        })
    except Exception as e:
        result_queue.put({"type": "error", "error": str(e)})


# ---------------------------------------------------------------------------
# Monitoring thread  (reads queue, updates registry)
# ---------------------------------------------------------------------------
def _monitor_worker(job_id, result_queue, process):
    """
    Daemon thread that drains *result_queue* and keeps JOB_REGISTRY in sync.
    Exits when a terminal message ('done' / 'error') is received or the
    subprocess dies unexpectedly.
    """
    try:
        while True:
            # If the process has died and the queue is empty, stop.
            try:
                msg = result_queue.get(timeout=1.0)
            except (queue.Empty, EOFError):
                if not process.is_alive():
                    with JOB_LOCK:
                        entry = JOB_REGISTRY.get(job_id)
                        if entry and entry["status"] in (JobState.PENDING, JobState.RUNNING):
                            entry["status"] = JobState.FAILED
                            entry["error"] = "Worker process exited unexpectedly"
                    return
                continue

            msg_type = msg.get("type")

            if msg_type == "running":
                with JOB_LOCK:
                    entry = JOB_REGISTRY.get(job_id)
                    if entry and entry["status"] == JobState.PENDING:
                        entry["status"] = JobState.RUNNING

            elif msg_type == "iteration":
                with JOB_LOCK:
                    entry = JOB_REGISTRY.get(job_id)
                    if entry:
                        entry["iteration"] = msg["iteration"]

            elif msg_type == "candidate":
                with JOB_LOCK:
                    entry = JOB_REGISTRY.get(job_id)
                    if entry:
                        entry["candidates"].append(msg["data"])

            elif msg_type == "done":
                with JOB_LOCK:
                    entry = JOB_REGISTRY.get(job_id)
                    if entry and entry["status"] not in (JobState.CANCELLED,):
                        entry["status"] = JobState.DONE
                return

            elif msg_type == "error":
                with JOB_LOCK:
                    entry = JOB_REGISTRY.get(job_id)
                    if entry and entry["status"] not in (JobState.CANCELLED,):
                        entry["status"] = JobState.FAILED
                        entry["error"] = msg.get("error", "Unknown error")
                return

    except Exception:
        # Safety net — mark as failed so callers never hang.
        with JOB_LOCK:
            entry = JOB_REGISTRY.get(job_id)
            if entry and entry["status"] in (JobState.PENDING, JobState.RUNNING):
                entry["status"] = JobState.FAILED
                entry["error"] = "Monitor thread crashed"


# ---------------------------------------------------------------------------
# Public submission entry-point
# ---------------------------------------------------------------------------
def submit_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1) -> str:
    """Submit an async multi-planet search.  Returns a job_id string."""
    job_id = str(uuid.uuid4())

    target = (
        raw_lightcurve.get("target_name", "Unknown")
        if isinstance(raw_lightcurve, dict)
        else getattr(raw_lightcurve, "target_name", "Unknown")
    )

    result_queue = multiprocessing.Queue()

    # ARCHITECTURAL CONSTRAINT (J2c nested-pool fix, 2026-07-06):
    # The worker is spawned daemon=True. On Windows, multiprocessing
    # forbids daemonic processes from spawning their own children. Any
    # code that runs inside _subprocess_search_worker (and transitively
    # inside detect_transit_candidate) MUST NOT itself call
    # multiprocessing.Pool(...) or multiprocessing.Process(...). In
    # particular, transitleastsquares' default use_threads=cpu_count()
    # path instantiates multiprocessing.Pool(processes=use_threads) and
    # raises AssertionError("daemonic processes are not allowed to have
    # children") when invoked from inside this worker. detection.py
    # forces use_threads=1 on its TLS call to honour this constraint.
    # See logs/nested_pool_check_2026-07-06T145219Z.json and tests/
    # characterize/test_tls_call_path_contract.py for the experimental
    # confirmation and the contract tests. If you ever set daemon=False
    # here (or remove the constraint in detection.py), you must
    # explicitly update the characterization tests and the call path
    # comment in detection.py.
    proc = multiprocessing.Process(
        target=_subprocess_search_worker,
        args=(result_queue, raw_lightcurve, max_signals, snr_floor),
        daemon=True,
    )

    with JOB_LOCK:
        JOB_REGISTRY[job_id] = {
            "status": JobState.PENDING,
            "target": target,
            "iteration": 0,
            "max_signals": max_signals,
            "candidates": [],
            "error": None,
            "_process": proc,        # stored for hard-kill
            "_queue": result_queue,   # stored for cleanup
        }

    proc.start()

    # Launch a daemon monitor thread that reads the queue
    monitor = threading.Thread(
        target=_monitor_worker,
        args=(job_id, result_queue, proc),
        daemon=True,
    )
    monitor.start()

    return job_id
