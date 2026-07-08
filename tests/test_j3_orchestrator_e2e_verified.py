"""Permanent characterization test for the orchestrator -> Verified path.

Regression class: a real, well-known planet (Kepler-90d) running through
the FULL production call stack (orchestrator -> daemon worker ->
BLSSearchEngine -> TLS with use_threads=1) must be emitted as
'Verified Planet Candidate' with a real TLS SDE >= 5.0 and no TLS
environment error.

This regression class previously bit us hard: the silent-AssertionError
bug folded environment failures into ``tls_valid=False`` since
2026-06-09, and the prior "recovery" numbers were produced by direct
calls to the alias-checker that bypassed the orchestrator. The bucket
J2c fix (use_threads=1 in detection.py + distinct except-Exception
branches) is what makes this test pass. If the test ever fails, the
gate is broken at exactly the layer the J2c review flagged.

Independent of the BLS performance decision (J3 decompose/pick-a-fix):
this characterization test is about correctness, not speed, and runs
the same synthetic 200d / 9,795-cadence curve that the perf scripts use.

Marked ``@pytest.mark.slow`` because the round-2 e2e logged a
wall-time of ~217s for this curve through the real call stack (TLS
narrow-window validation dominates); opt in with::

    pytest tests/test_j3_orchestrator_e2e_verified.py -m slow -v

NOT network: the curve is fully synthetic, no NASA / MAST / TLS service
calls. The TLS SDE comes from the real ``transitleastsquares`` library
running on the synthetic light curve in-process.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from astraeus.core.orchestrator import (
    JobState,
    cancel_job,
    get_job_status,
    submit_multi_planet_search,
)

# --- Kepler-90d physical parameters (must match e2e_kepler90d_real_path.py) -
KEPLER90D_PERIOD_D = 59.73667
KEPLER90D_DEPTH_PPM = 602.0
KEPLER90D_DURATION_D = 4.2 / 24.0
KEPLER90D_T0_BJD = 130.0

# --- Curve parameters (same as e2e_kepler90d_real_path.py) ------------------
BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0  # Kepler long cadence
N_CADENCES = int(BASELINE_D / CADENCE_D)  # ~ 9,795
NOISE_PPM = 100.0
SEED = 20260706

# --- Test budget (must comfortably exceed the ~217s round-2 wall time) -----
HARD_TIMEOUT_S = 600.0
POLL_S = 2.0
PERIOD_TOLERANCE = 0.01  # |recovered - 59.73667| / 59.73667 <= 1%
TLS_SDE_FLOOR = 5.0


def _make_kepler90d_curve() -> tuple[np.ndarray, np.ndarray]:
    """Trapezoidal transit model (linear ingress/egress). Same shape
    ``subtract_planetary_signal`` falls back to, so this exercises
    realistic transit geometry. No second signal, no variability.
    """
    rng = np.random.default_rng(seed=SEED)
    t = np.arange(N_CADENCES) * CADENCE_D
    y = 1.0 + (NOISE_PPM * 1e-6) * rng.standard_normal(N_CADENCES)

    period = KEPLER90D_PERIOD_D
    t0 = KEPLER90D_T0_BJD
    duration = KEPLER90D_DURATION_D
    depth = KEPLER90D_DEPTH_PPM * 1e-6

    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    abs_phase = np.abs(phase)
    ramp_duration = 0.1 * duration
    flat_duration = duration - 2 * ramp_duration

    in_flat = abs_phase <= (flat_duration / 2.0)
    in_ramp = (abs_phase > (flat_duration / 2.0)) & (abs_phase <= (duration / 2.0))
    ramp_x = abs_phase[in_ramp] - (flat_duration / 2.0)
    y[in_flat] -= depth
    y[in_ramp] -= depth * (1.0 - (ramp_x / ramp_duration))

    return t, y


def _wait_for_terminal(job_id: str) -> dict:
    """Poll the orchestrator job until DONE/FAILED/CANCELLED or timeout.

    Mirrors the polling loop in ``scratch/e2e_kepler90d_real_path.py``
    so this test is a regression witness for the same control flow.
    """
    deadline = time.perf_counter() + HARD_TIMEOUT_S
    last = {}
    while time.perf_counter() < deadline:
        last = get_job_status(job_id)
        st = last.get("status")
        if st in (JobState.DONE, JobState.FAILED, JobState.CANCELLED):
            return last
        time.sleep(POLL_S)
    # Timed out: cancel and return the last snapshot.
    try:
        cancel_job(job_id)
    finally:
        last = get_job_status(job_id)
    return last


@pytest.mark.slow
def test_orchestrator_emits_kepler90d_as_verified_with_real_tls() -> None:
    """End-to-end: orchestrator must emit Kepler-90d as 'Verified Planet
    Candidate' with a real TLS SDE >= 5.0 and no TLS environment error.

    Contract (must hold for the J2c fix to be considered end-to-end
    functional):
      (a) job terminates in DONE
      (b) at least one candidate has ``vetting_status`` starting with
          "Verified Planet Candidate"
      (c) that candidate has ``tls_valid is True``
      (d) that candidate has ``tls_sde >= 5.0``
      (e) that candidate has ``tls_environment_error is None``
      (f) the recovered period is within 1% of the injected 59.73667d
    """
    t, y = _make_kepler90d_curve()
    raw = {
        "time": t.tolist(),
        "flux": y.tolist(),
        "target_name": "Kepler-90 (synthetic, d-only)",
        "data_source": "synthetic-e2e-characterization",
        "metadata": {
            "st_rad": 1.2,
            "st_teff": 5930.0,
            "st_mass": 1.13,
            "sy_jmag": 12.49,
        },
    }

    job_id = submit_multi_planet_search(raw, max_signals=1, snr_floor=5.0)
    try:
        final = _wait_for_terminal(job_id)
    finally:
        # If the job is still RUNNING after the wait loop's cancel attempt,
        # make sure we always release the worker.
        st = get_job_status(job_id).get("status")
        if st == JobState.RUNNING:
            cancel_job(job_id)

    # (a) terminal state
    assert final.get("status") == JobState.DONE, (
        f"orchestrator job did not finish DONE: status={final.get('status')!r} "
        f"error={final.get('error')!r}"
    )

    candidates = final.get("candidates", []) or []
    assert len(candidates) >= 1, (
        f"expected >=1 candidate, got {len(candidates)}; final={final!r}"
    )

    # Find a candidate that satisfies the four-field conjunction.
    matched = None
    for c in candidates:
        vetting = c.get("vetting_status")
        if not (isinstance(vetting, str) and vetting.startswith("Verified Planet Candidate")):
            continue
        if c.get("tls_valid") is not True:
            continue
        if c.get("tls_sde") is None or float(c["tls_sde"]) < TLS_SDE_FLOOR:
            continue
        if c.get("tls_environment_error") is not None:
            continue
        matched = c
        break

    assert matched is not None, (
        "no candidate satisfied (Verified Planet Candidate) AND "
        "tls_valid=True AND tls_sde>=5.0 AND tls_environment_error=None. "
        f"candidates={candidates!r}"
    )

    # (f) period within 1% of injected truth
    recovered_period = float(matched.get("period"))
    rel_err = abs(recovered_period - KEPLER90D_PERIOD_D) / KEPLER90D_PERIOD_D
    assert rel_err <= PERIOD_TOLERANCE, (
        f"recovered period {recovered_period:.5f}d is "
        f"{rel_err*100:.4f}% off injected {KEPLER90D_PERIOD_D}d (>1%)"
    )
