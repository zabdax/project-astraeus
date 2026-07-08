"""Single-signal CI-feasible regression test for BLSSearchEngine.search().

The "doesn't get worse" gate the bucket-J3 review cycle produced. The
goal: lock in the current correct behavior of BLSSearchEngine.search()
on a synthetic single-signal curve that completes in under 30s on
modest hardware, and add forward-looking guards for the
degenerate-peak bug found in the same review.

Curve parameters (chosen for budget + signal dominance):
  - 50d baseline, 1500 cadences (30-min cadence approx)
  - Single injected transit at P=10.0d, depth=1% (10,000 ppm), t0=2.0d,
    duration=0.15d. 5 transits fit in the 50d baseline, so the signal
    is dominant in the periodogram and the test exercises the path
    the team has historically relied on for fast verification.

What this test asserts (today's contract):
  1. BLSSearchEngine.search() returns a non-empty result.
  2. Recovered period is within 1% of the injected 10.0d.
  3. Recovered duration is within a factor of 2 of the injected 0.15d.
  4. Wall time is under 30s (the CI-feasible budget; if a future
     change blows this budget, the test fails and forces the change
     to be marked slow or fixed).

What this test guards against (forward-looking):
  5. Recovered period is NOT within 5% of the search bounds
     (p_min=0.5d, p_max=25d on this curve). The J3 review found that
     astropy.autoperiod produces degenerate peaks at p_min and p_max
     where unphysical (period, duration) pairs (e.g. dur=0.6d, P=0.5d,
     i.e. duration > period) can spike the periodogram and dominate
     np.argmax. This assertion catches a regression to that mode even
     on a curve where it doesn't fire today.
  6. Recovered duration is strictly less than the recovered period
     times 0.2 (the physical transit duty-cycle cap, ~20% of an
     orbit for grazing/contact binaries; real transits are well
     under 5%). This is the actual root-cause guard for the
     degenerate-peak class, not just a boundary-mask patch.

Marker: NOT @pytest.mark.network, NOT @pytest.mark.slow. The curve
is fully synthetic and BLSSearchEngine.search() runs in ~8s on this
curve on the current machine. If the budget test ever fails, the
fix is either to optimize or to mark this @pytest.mark.slow; do
not silently widen the tolerance.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from astraeus.analysis.bls_search import BLSSearchEngine

# --- Curve parameters (50d / 1500 cadences, single 10d signal) --------------
_INJECTED_PERIOD_DAYS = 10.0
_INJECTED_DEPTH_FRACTION = 0.01
_INJECTED_DURATION_DAYS = 0.15
_INJECTED_T0_DAYS = 2.0
_BASELINE_DAYS = 50.0
_N_CADENCES = 1500
_NOISE_STD = 5e-4
_SEED = 20260708

# --- Tolerances (the contract this test enforces) ---------------------------
_PERIOD_TOLERANCE_FRAC = 0.01  # 1%
_DURATION_TOLERANCE_FACTOR = 2.0  # within 2x of injected
_BOUNDARY_MARGIN_FRAC = 0.05  # within 5% of p_min or p_max is degenerate
_MAX_DUTY_CYCLE = 0.2  # duration/period <= 0.2 for physical transits
_WALL_BUDGET_S = 30.0


def _build_single_signal_curve():
    """Trapezoidal transit on a flat light curve, single injected planet."""
    rng = np.random.default_rng(seed=_SEED)
    t = np.linspace(0.0, _BASELINE_DAYS, _N_CADENCES)
    y = 1.0 + _NOISE_STD * rng.standard_normal(_N_CADENCES)
    period = _INJECTED_PERIOD_DAYS
    t0 = _INJECTED_T0_DAYS
    duration = _INJECTED_DURATION_DAYS
    depth = _INJECTED_DEPTH_FRACTION
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    in_tr = np.abs(phase) < 0.5 * duration
    y[in_tr] -= depth
    return t, y


def test_bls_search_recovers_single_signal_under_budget():
    """BLSSearchEngine.search() must recover a single injected transit
    within 1% period tolerance, within 2x duration tolerance, under
    30s wall time, and must not return a degenerate boundary peak
    or an unphysical duration/period ratio.
    """
    t, y = _build_single_signal_curve()

    t0 = time.perf_counter()
    result = BLSSearchEngine.search(t, y)
    wall = time.perf_counter() - t0

    # --- Today's contract ---
    assert result, "BLSSearchEngine.search() returned empty result"
    for key in ("period", "duration", "snr", "depth"):
        assert key in result, f"missing key in result: {key!r}"

    recovered_period = float(result["period"])
    recovered_duration = float(result["duration"])

    # Period within 1% of injected
    period_rel_err = abs(recovered_period - _INJECTED_PERIOD_DAYS) / _INJECTED_PERIOD_DAYS
    assert period_rel_err <= _PERIOD_TOLERANCE_FRAC, (
        f"recovered period {recovered_period:.5f}d is "
        f"{period_rel_err*100:.4f}% off injected {_INJECTED_PERIOD_DAYS}d "
        f"(>{_PERIOD_TOLERANCE_FRAC*100:.1f}%)"
    )

    # Duration within 2x of injected (BLS duration is approximate)
    assert (
        _INJECTED_DURATION_DAYS / _DURATION_TOLERANCE_FACTOR
        <= recovered_duration
        <= _INJECTED_DURATION_DAYS * _DURATION_TOLERANCE_FACTOR
    ), (
        f"recovered duration {recovered_duration:.4f}d is outside "
        f"[{_INJECTED_DURATION_DAYS/_DURATION_TOLERANCE_FACTOR:.4f}, "
        f"{_INJECTED_DURATION_DAYS*_DURATION_TOLERANCE_FACTOR:.4f}]d"
    )

    # Wall time under budget
    assert wall <= _WALL_BUDGET_S, (
        f"BLSSearchEngine.search() took {wall:.1f}s, exceeds "
        f"budget of {_WALL_BUDGET_S:.0f}s. If a future change legitimately "
        f"slows this down, mark this test @pytest.mark.slow rather than "
        f"silently widening the budget."
    )

    # --- Forward-looking guards (degenerate-peak bug class) ---
    # The search bounds for this curve: p_min=0.5, p_max=25 (T_baseline/2).
    p_min = 0.5
    p_max = min(450.0, _BASELINE_DAYS / 2.0)
    not_near_pmin = abs(recovered_period - p_min) / p_min > _BOUNDARY_MARGIN_FRAC
    not_near_pmax = abs(recovered_period - p_max) / p_max > _BOUNDARY_MARGIN_FRAC
    assert not_near_pmin, (
        f"recovered period {recovered_period:.4f}d is within "
        f"{_BOUNDARY_MARGIN_FRAC*100:.0f}% of p_min={p_min}d. "
        f"This is the degenerate-peak failure mode: astropy.autoperiod "
        f"produces a high-power degenerate point at p_min (duration > period), "
        f"and np.argmax returns it instead of the real signal."
    )
    assert not_near_pmax, (
        f"recovered period {recovered_period:.4f}d is within "
        f"{_BOUNDARY_MARGIN_FRAC*100:.0f}% of p_max={p_max:.2f}d. "
        f"Same degenerate-peak failure mode at p_max."
    )

    # Physical duration < period * max_duty_cycle
    duty_cycle = recovered_duration / recovered_period
    assert duty_cycle < _MAX_DUTY_CYCLE, (
        f"recovered duration/period = {duty_cycle:.4f} exceeds "
        f"physical max duty cycle {_MAX_DUTY_CYCLE}. This means the "
        f"transit duration is unphysical for the recovered period; the "
        f"candidate is almost certainly a degenerate boundary peak."
    )
