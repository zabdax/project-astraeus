"""Phase 0: the real scientific failure chain, end to end.

PRD v4.1 §29 defines the core scientific-correctness requirement of
Phase 0:

    backend unavailable
        -> TLS cannot validate
        -> candidate cannot be accepted as validated
        -> execution state reflects failure/unavailability
        -> caller can distinguish this from "zero candidates"

Before Phase 0, an infrastructure failure terminated as DONE with
`candidates: []` and `error: None` -- every "no planets found" result
was indistinguishable from a broken pipeline (PRD §4.3, audit A3-F5).

These tests prove the chain across BOTH search loops:
`run_multi_planet_search` (sync -- the one real data uses) and
`_subprocess_search_worker` (async). The sync/async loops have already
drifted once (PRD §2.5), so a guardrail fix must be proven on both.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from astraeus.core.capabilities import BackendId, BackendUnavailable, TlsOutcome
from astraeus.core.orchestrator import (
    JobState,
    _subprocess_search_worker,
    run_multi_planet_search,
    get_job_status,
)


def _synthetic_lightcurve(n: int = 300, seed: int = 20260917) -> dict:
    rng = np.random.default_rng(seed=seed)
    t = np.arange(n, dtype=np.float64) * 0.02
    flux = 1.0 + 1e-3 * rng.standard_normal(n)
    period, t0, duration, depth = 1.2, 0.3, 0.05, 0.008
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    flux[np.abs(phase) < 0.5 * duration] -= depth
    return {
        "time": t,
        "flux": flux,
        "target_name": "phase0-failclosed",
        "data_source": "synthetic",
        "metadata": {},
    }


def _block_tls(monkeypatch) -> None:
    """Make the TLS backend unavailable for the duration of the test."""
    monkeypatch.setitem(sys.modules, "transitleastsquares", None)


# ---------------------------------------------------------------------------
# Sync path -- run_multi_planet_search (the one real data uses)
# ---------------------------------------------------------------------------


def test_sync_loop_fails_closed_on_missing_tls(monkeypatch):
    """A missing TLS backend must raise a structured BackendUnavailable,
    not return an empty candidate list masquerading as 'no planets'."""
    _block_tls(monkeypatch)
    lightcurve = _synthetic_lightcurve()

    with pytest.raises(BackendUnavailable) as excinfo:
        run_multi_planet_search(lightcurve, max_signals=2, snr_floor=7.1)

    assert excinfo.value.backend is BackendId.TLS


def test_sync_loop_env_failure_is_not_zero_candidates(monkeypatch):
    """The error reason must explicitly say the gate could not execute,
    so a caller cannot read it as a valid negative result."""
    _block_tls(monkeypatch)
    lightcurve = _synthetic_lightcurve()

    with pytest.raises(BackendUnavailable) as excinfo:
        run_multi_planet_search(lightcurve, max_signals=2)

    message = str(excinfo.value)
    assert "transitleastsquares" in message
    # The orchestrator's own gate contributes the environment reason.
    assert "could not execute" in message or "not installed" in message


# ---------------------------------------------------------------------------
# Async path -- _subprocess_search_worker (job-state propagation)
# ---------------------------------------------------------------------------


def _drain_queue(queue, timeout: float = 30.0):
    """Collect queue messages until a terminal one arrives."""
    import queue as queue_mod

    messages = []
    while True:
        try:
            messages.append(queue.get(timeout=timeout))
        except queue_mod.Empty:
            break
        if messages[-1].get("type") in ("done", "error"):
            break
    return messages


def _patch_worker_detection_to_env_failure(monkeypatch):
    """Force every detection inside the worker to report an environment
    failure.  Since P1-I unified the search loops, the async worker
    delegates to ``run_multi_planet_search``, which resolves
    ``detect_transit_candidate`` from the *orchestrator's* namespace, so
    that is the binding we must patch for an in-process run.  The detection
    module attribute is patched too so the helper stays correct for any
    caller that resolves the name lazily."""
    from astraeus.analysis import detection as detection_mod
    from astraeus.core import orchestrator as orchestrator_mod

    real_detection = detection_mod.detect_transit_candidate

    def _env_failing_detection(*args, **kwargs):
        result = real_detection(*args, **kwargs)
        result["tls_outcome"] = TlsOutcome.ENV_UNAVAILABLE.value
        result["tls_valid"] = False
        result["tls_environment_error"] = (
            "transitleastsquares is not installed; the TLS "
            "cross-validation gate could not execute"
        )
        return result

    monkeypatch.setattr(detection_mod, "detect_transit_candidate", _env_failing_detection)
    monkeypatch.setattr(orchestrator_mod, "detect_transit_candidate", _env_failing_detection)


def test_async_worker_reports_error_not_done(monkeypatch):
    """The async worker must emit an 'error' event (job FAILED) rather
    than 'done' (job COMPLETED) when the TLS gate cannot execute."""
    import multiprocessing

    _patch_worker_detection_to_env_failure(monkeypatch)
    queue = multiprocessing.Queue()
    lightcurve = _synthetic_lightcurve()

    _subprocess_search_worker(queue, lightcurve, max_signals=2, snr_floor=7.1)
    messages = _drain_queue(queue)

    types_ = [m.get("type") for m in messages]
    assert "error" in types_, f"expected an error event, got {types_}"
    assert "done" not in types_, (
        "A TLS environment failure must NOT terminate as 'done' -- that "
        "is the exact DONE/0-candidates ambiguity PRD §4.3 requires fixed."
    )


def test_async_worker_error_names_the_backend(monkeypatch):
    """The FAILED reason must identify the missing backend and state that
    it is not a zero-candidate result (PRD definition of done, Phase 1)."""
    import multiprocessing

    _patch_worker_detection_to_env_failure(monkeypatch)
    queue = multiprocessing.Queue()
    _subprocess_search_worker(queue, _synthetic_lightcurve(), 2, 7.1)
    messages = _drain_queue(queue)

    error_event = next(m for m in messages if m.get("type") == "error")
    reason = error_event.get("error", "")
    assert "transitleastsquares" in reason
    assert "FAILED" in reason or "could not execute" in reason


def test_monitor_marks_job_failed_on_error_event():
    """The monitor thread must translate a worker 'error' event into a
    FAILED registry entry with a reason. This is the last hop of the
    chain: worker emits error -> monitor marks FAILED -> caller sees a
    diagnosable state instead of '0 candidates'.

    Exercised directly (rather than via submit_multi_planet_search)
    because a spawned subprocess does not inherit the parent's
    monkeypatched modules on Windows, which would make the test
    platform-dependent. The worker-side behaviour is covered by the two
    tests above; this one covers the registry-side propagation.
    """
    import multiprocessing
    import threading

    import astraeus.core.orchestrator as orch

    queue = multiprocessing.Queue()
    queue.put({"type": "running"})
    queue.put({"type": "error", "error": "Required scientific backend unavailable: transitleastsquares"})

    job_id = "phase0-monitor-probe"
    fake_proc = type("Proc", (), {"is_alive": lambda self: False})()
    with orch.JOB_LOCK:
        orch.JOB_REGISTRY[job_id] = {
            "status": JobState.RUNNING,
            "target": "probe",
            "iteration": 1,
            "max_signals": 2,
            "candidates": [],
            "error": None,
            "_process": fake_proc,
            "_queue": queue,
        }

    monitor = threading.Thread(
        target=orch._monitor_worker,
        args=(job_id, queue, fake_proc),
        daemon=True,
    )
    monitor.start()
    monitor.join(timeout=10.0)

    status = get_job_status(job_id)
    assert status["status"] == JobState.FAILED
    assert "transitleastsquares" in status["error"]
