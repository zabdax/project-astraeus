"""Multi-planet recovery test: SYN-5P-small at 1/5 contract (round 7).

Companion to tests/test_j3_bls_single_signal_regression.py. The
single-signal test enforces the "doesn't get worse" contract on a
clean 50d curve. This test enforces a forward-looking multi-planet
recovery contract on the 1500d / 3000-cadence SYN-5P-small curve.

Curve parameters (canonical SYN-5P-small):
  - 1500d baseline, 3000 cadences, 500 ppm Gaussian noise, seed=42
  - 5 injected planets at 12/45/120/300/600d, depths 500/1000/800/1500/
    2000 ppm, durations 0.15/0.25/0.40/0.60/0.80d

What the J3 review measured (round 7, with the J3 fix + adaptive
``frequency_factor`` + widened ``p_max = T_baseline/2`` + boundary-
margin rejection in the alias loop):
  - BLSSearchEngine.search() on this curve takes ~3.6s per call
  - Iteration 1 (no known_periods): the alias-rejection loop
    correctly accepts p2 (45d) — verified
  - Subsequent iterations: the loop accepts noise peaks because
    integer-harmonic + window-alias checks don't catch them, even
    though the periodogram top-20 contains p3, p4, p5. This is a
    separate issue from the J3 fix; recovering 4/5 iteratively
    would require the orchestrator to use a top-K selection (not
    first-accept) or a stricter noise rejection in the alias loop.
  - p1 (12d) is noise-limited on this curve: the BLS power at the
    true 12d period is only 0.77x the noise-floor power at the same
    period, ranking #5966 in the periodogram. It is below the
    recovery threshold for this curve, not below the search threshold
    (verified by direct measurement in scratch/j3i_p1p5_noise_floor.py).

What this test asserts (the 1/5 contract, the post-fix baseline):
  1. Iteration 1 of ``BLSSearchEngine.search()`` recovers one of
     p2/p3/p4/p5 (i.e. not p1, not a noise peak, not a boundary
     artifact). This is the strongest contract that the current
     alias-rejection logic can meet on this curve, and it is
     already a strict improvement over the round-3 behavior (which
     returned 0.5002d on iteration 1 with no J3 fix).
  2. The recovered candidate is physical (duration < period * 0.2,
     period not within 5% of p_min or p_max).
  3. Wall time is under 30s for the single iteration.

Marked ``@pytest.mark.slow`` because ``search()`` on this curve
takes ~5-15s. NOT network: the curve is fully synthetic.

If a future change breaks iteration 1 recovery (e.g. J3 fix
removed, frequency_factor default too aggressive, p_max regression),
this test fails. Tightening to 4/5 would require either a different
recovery strategy in the orchestrator (top-K instead of first-accept)
or a higher-N / longer-baseline curve.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from astraeus.analysis.bls_search import BLSSearchEngine

# --- Curve parameters (canonical SYN-5P-small) -----------------------------
_N_SAMPLES = 3000
_T_SPAN = 1500.0
_NOISE_STD = 5e-4
_SEED = 42

INJECTED = [
    # (name, period_d, depth_ppm, t0_d, duration_d)
    ("p1",  12.0,  500,  5.0,   0.15),
    ("p2",  45.0,  1000, 22.0,  0.25),
    ("p3", 120.0,  800,  80.0,  0.40),
    ("p4", 300.0,  1500, 200.0,  0.60),
    ("p5", 600.0,  2000, 450.0,  0.80),
]
_PERIOD_TOLERANCE_FRAC = 0.02  # 2%
_BOUNDARY_MARGIN_FRAC = 0.05
_MAX_DUTY_CYCLE = 0.2
_RECOVERABLE_FIRST = ("p2", "p3", "p4", "p5")  # p1 is noise-limited
_MIN_RECOVERY = 1  # 1/5 is the post-fix baseline on iteration 1
_TOTAL_WALL_BUDGET_S = 30.0


def _build_synthetic_5p() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=_SEED)
    t = np.linspace(0, _T_SPAN, _N_SAMPLES)
    y = 1.0 + rng.normal(0, _NOISE_STD, size=_N_SAMPLES)
    for name, period, depth_ppm, t0, dur in INJECTED:
        phase = ((t - t0) % period) - period / 2.0
        y[np.abs(phase) < dur / 2.0] -= depth_ppm / 1e6
    return t, y


def _match_to_injected(recovered_period: float):
    """Return the injected (name, period) tuple whose period is within
    2% of the recovered period, or None if no match."""
    for (name, period, *_rest) in INJECTED:
        if abs(recovered_period - period) / period <= _PERIOD_TOLERANCE_FRAC:
            return (name, period)
    return None


def _all_injected_names():
    return [n for (n, *_r) in INJECTED]


@pytest.mark.slow
def test_synthetic_5p_first_iteration_recovers_a_strong_signal() -> None:
    """SYN-5P-small: iteration 1 of ``BLSSearchEngine.search()`` must
    recover one of p2/p3/p4/p5 (a strong signal), under 30s wall
    time, with the recovered candidate satisfying the physical
    duty-cycle guard and the boundary-margin guard. p1 (12d) is
    noise-limited on this curve and is excluded from the contract.
    """
    t, y = _build_synthetic_5p()
    p_min = 0.5
    p_max = _T_SPAN / 2.0

    t_start = time.perf_counter()
    result = BLSSearchEngine.search(t, y, known_periods=[])
    wall = time.perf_counter() - t_start

    recovered_p = float(result["period"])
    recovered_dur = float(result["duration"])

    # --- Forward-looking guards (must hold) ---
    duty = recovered_dur / recovered_p
    assert duty < _MAX_DUTY_CYCLE, (
        f"recovered duration/period = {duty:.4f} exceeds physical max "
        f"duty cycle {_MAX_DUTY_CYCLE}. This is the degenerate-peak "
        f"failure mode. Recovered: P={recovered_p:.4f}d, dur={recovered_dur:.3f}d."
    )
    assert abs(recovered_p - p_min) / p_min > _BOUNDARY_MARGIN_FRAC, (
        f"recovered period {recovered_p:.4f}d is within "
        f"{_BOUNDARY_MARGIN_FRAC*100:.0f}% of p_min={p_min}d."
    )
    assert abs(recovered_p - p_max) / p_max > _BOUNDARY_MARGIN_FRAC, (
        f"recovered period {recovered_p:.4f}d is within "
        f"{_BOUNDARY_MARGIN_FRAC*100:.0f}% of p_max={p_max:.0f}d."
    )

    # --- Recovery contract ---
    match = _match_to_injected(recovered_p)
    matched_name = match[0] if match is not None else None
    print(
        f"\n[5P] iteration 1: recovered {recovered_p:.4f}d "
        f"(matched: {matched_name}), wall={wall:.1f}s"
    )

    assert match is not None, (
        f"iteration 1 recovered period {recovered_p:.4f}d which is not "
        f"within 2% of any injected planet. This usually means a "
        f"noise peak (boundary artifact, sampling alias) won the "
        f"alias-rejection loop. The contract is that iteration 1 "
        f"recovers a strong signal (p2/p3/p4/p5) on this curve."
    )
    assert matched_name in _RECOVERABLE_FIRST, (
        f"iteration 1 recovered {matched_name}@{match[1]}d. p1 is "
        f"noise-limited on this 1500d / 3000-cadence curve (BLS power "
        f"at the true 12d period is 0.77x the noise-floor power, rank "
        f"#5966 in the periodogram). The contract is that iteration 1 "
        f"recovers one of p2/p3/p4/p5. If this test fails with p1, "
        f"the curve is too small for 12d/500ppm recovery; if it "
        f"fails with a non-injected period, the J3 fix or boundary-"
        f"margin check was removed."
    )
    assert wall <= _TOTAL_WALL_BUDGET_S, (
        f"BLSSearchEngine.search() took {wall:.1f}s, exceeds budget of "
        f"{_TOTAL_WALL_BUDGET_S:.0f}s."
    )
