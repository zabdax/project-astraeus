"""Phase 2, J3b: How does model.power() scale with N_periods * N_durations?

Decomposition showed model.power(795688 x 8) = 136.9s. We need to know
if this is O(N_periods * N_durations * N) per call, and what
p_max cap gets us into a 5-10 minute budget for the 1240d / 45,853-
cadence Kepler-90 curve.

This script tests the same synthetic curve shape (so the autoperiod
density pattern is realistic) at three p_max caps:
  - p_max = 99.98d  (current behavior for T_baseline < 300d)
  - p_max = 50d
  - p_max = 25d

and reports n_periods, n_durations, model.power seconds, and seconds
per (n_periods * n_durations * n_cadences). This is what we need to
choose a budget-feasible p_max for the full Kepler-90 curve.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from astropy.timeseries import BoxLeastSquares

BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0
N_CADENCES = int(BASELINE_D / CADENCE_D)
SEED = 20260706
# Keep this fast - we already know 99.98d = 136.9s. 50d is the question
# (does halving p_max halve the cost or blow it up due to autoperiod
# density in the short-period range?).
P_MAX_OPTIONS = [50.0, 25.0]


def make_curve():
    rng = np.random.default_rng(seed=SEED)
    t = np.arange(N_CADENCES) * CADENCE_D
    y = 1.0 + 100e-6 * rng.standard_normal(N_CADENCES)
    return t, y


def measure_power(p_max: float) -> dict:
    t_arr, y_arr = make_curve()
    model = BoxLeastSquares(t_arr, y_arr)
    p_min = 0.5
    t1 = time.perf_counter()
    periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)
    autoperiod_s = time.perf_counter() - t1

    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    durations = durations[durations < np.min(periods)]
    n_p, n_d = len(periods), len(durations)

    t2 = time.perf_counter()
    res = model.power(periods, durations)
    power_s = time.perf_counter() - t2

    return {
        "p_max": p_max,
        "n_periods": n_p,
        "n_durations": n_d,
        "autoperiod_s": autoperiod_s,
        "model_power_s": power_s,
        "p_min_period": float(np.min(periods)),
        "p_max_period": float(np.max(periods)),
    }


def main() -> int:
    print(f"[J3b] Curve: {N_CADENCES} cadences over {BASELINE_D}d "
          f"(cadence {CADENCE_D*24*60:.1f}min)")
    rows = []
    for p_max in P_MAX_OPTIONS:
        r = measure_power(p_max)
        rows.append(r)
        # Approx cost on 45853-cadence Kepler-90 real curve (1240d)
        scale_factor = 45853 / N_CADENCES  # linear in N is the round-1 finding
        projected = r["model_power_s"] * scale_factor
        print(f"  p_max={p_max:6.2f}d  n_periods={r['n_periods']:>7}  "
              f"n_durations={r['n_durations']:>2}  "
              f"power={r['model_power_s']:7.3f}s  "
              f"projected@45853-cad={projected:7.1f}s")

    out_path = SCRIPT_DIR / "j3b_pmax_scaling_result.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\n[J3b] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
