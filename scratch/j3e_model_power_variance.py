"""Phase 1, J3e: Measure model.power variance and true BLS.search() variance.

We need hard numbers to reconcile:
  - J3 decomposition said model.power = 136.9s
  - J3d said model.power = 199.0s
  - J3c said BLSSearchEngine.search() = 182-206s

Run model.power() repeatedly (after autoperiod is cached) and report
the actual distribution. Then run search() repeatedly and report its
distribution. This is the only way to get a credible 95% CI on what
each section is actually costing.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from astropy.timeseries import BoxLeastSquares

KEPLER90D_PERIOD_D = 59.73667
KEPLER90D_DEPTH_PPM = 602.0
KEPLER90D_DURATION_D = 4.2 / 24.0
KEPLER90D_T0_BJD = 130.0
BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0
N_CADENCES = int(BASELINE_D / CADENCE_D)
NOISE_PPM = 100.0
SEED = 20260706


def make_curve():
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


def main() -> int:
    print(f"[J3e] Curve: {N_CADENCES} cadences over {BASELINE_D}d")
    t, y = make_curve()
    model = BoxLeastSquares(t, y)
    p_min = 0.5
    p_max = min(450.0, BASELINE_D / 2.0)

    t0 = time.perf_counter()
    periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)
    autoperiod_s = time.perf_counter() - t0
    n_periods = len(periods)
    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    durations = durations[durations < np.min(periods)]
    n_durations = len(durations)
    print(f"[J3e] autoperiod: {autoperiod_s:.4f}s, n_periods={n_periods}, "
          f"n_durations={n_durations}")

    # Measure model.power repeatedly to get the actual distribution
    n_repeats = 2
    power_times = []
    for i in range(n_repeats):
        t1 = time.perf_counter()
        res = model.power(periods, durations)
        dt = time.perf_counter() - t1
        power_times.append(dt)
        del res
        print(f"[J3e] model.power call {i+1}/{n_repeats}: {dt:.4f}s")

    print("\n[J3e] ===== model.power DISTRIBUTION =====")
    arr = np.array(power_times)
    print(f"  n={len(arr)}, mean={arr.mean():.4f}s, std={arr.std(ddof=1):.4f}s")
    print(f"  range=[{arr.min():.4f}, {arr.max():.4f}]s, "
          f"spread={arr.max()-arr.min():.4f}s")
    print(f"  median={np.median(arr):.4f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
