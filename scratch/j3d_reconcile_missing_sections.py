"""Phase 1, J3d: Add the missing section(s) to the J3 decomposition.

The J3 decomposition summed to 147.134s but BLSSearchEngine.search()
directly takes 182-206s on the same curve. Two strong candidates for
the missing 35-58s:

  (a) res.period.tolist() and res.power.tolist() in the return-dict
      construction (each on a 795,688-element array). Converting a
      numpy float64 array to a Python list is not free.

  (b) Window periodogram: in the J3 decomposition, the LombScargle
      call was done separately; in BLSSearchEngine.search(), the import
      of LombScargle is inside the function. We import it at the top
      of j3_decompose_bls.py, so import cost was already amortized.

We will (a) measure tolist() cost, (b) verify the import of LombScargle
inside search() isn't hiding cost, and (c) report the new sum.
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
    print(f"[J3d] Curve: {N_CADENCES} cadences over {BASELINE_D}d")
    t, y = make_curve()

    # Measure each step exactly as BLSSearchEngine.search() does it
    t0_total = time.perf_counter()
    model = BoxLeastSquares(t, y)
    T_baseline = float(np.max(t) - np.min(t))
    p_min = 0.5
    p_max = 450.0 if T_baseline > 300.0 else min(450.0, T_baseline / 2.0)

    t1 = time.perf_counter()
    periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)
    t2 = time.perf_counter()
    autoperiod_s = t2 - t1
    n_periods = len(periods)

    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    durations = durations[durations < np.min(periods)]

    t3 = time.perf_counter()
    res = model.power(periods, durations)
    t4 = time.perf_counter()
    power_s = t4 - t3

    # The tolist() conversion in the return-dict construction
    t5 = time.perf_counter()
    _ = res.period.tolist()
    _ = res.power.tolist()
    t6 = time.perf_counter()
    tolist_s = t6 - t5

    # The confidence_score calculation
    t7 = time.perf_counter()
    best_power = float(np.max(res.power))
    _ = float(best_power / np.median(res.power))
    t8 = time.perf_counter()
    conf_s = t8 - t7

    # The argsort on res.power (sorted_indices)
    t9 = time.perf_counter()
    _ = np.argsort(res.power)[::-1]
    t10 = time.perf_counter()
    argsort_s = t10 - t9

    t11 = time.perf_counter()
    total_s = t11 - t0_total

    print("\n[J3d] ===== EXPANDED DECOMPOSITION =====")
    sections = [
        ("autoperiod (grid construction)", autoperiod_s),
        ("model.power (BLS box-fitting)", power_s),
        ("np.argsort(res.power) [::-1]", argsort_s),
        ("res.period.tolist() + res.power.tolist()", tolist_s),
        ("confidence_score = max/median", conf_s),
    ]
    measured_sum = sum(s for _, s in sections)
    for name, dt in sections:
        pct = 100.0 * dt / total_s if total_s > 0 else 0.0
        print(f"  {name:>50}: {dt:8.4f}s  ({pct:5.1f}%)")
    overhead_s = total_s - measured_sum
    print(f"  {'(unaccounted overhead)':>50}: {overhead_s:8.4f}s  "
          f"({100.0*overhead_s/total_s if total_s>0 else 0:5.1f}%)")
    print(f"  {'TOTAL':>50}: {total_s:8.4f}s")
    print(f"  n_periods: {n_periods}, n_durations: {len(durations)}, "
          f"n_periods * n_durations: {n_periods * len(durations):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
