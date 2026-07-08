"""Phase 1, J3c: Reconcile the 184s vs 147s gap.

The previous round measured BLSSearchEngine.search() = 184s on this
exact 200d / 9,795-cadence curve. The J3 decomposition summed its four
sections to 147.134s, with only 0.045s unaccounted. A 37s gap between
two claims of the same call is too large to leave unexplained; we
need to know whether:

  (a) the J3 decomposition is missing a section (e.g. an import cost
      inside search(), the binned_time/binned_flux = time/flux aliases,
      the empty-list guard, etc.),
  (b) the per-section timings and the end-to-end timing were taken on
      warm vs cold cache state, and the cold state is significantly
      more expensive (imports, autoperiod C-extension JIT, etc.),
  (c) the 184s number from the prior round was on a different curve or
      a different Python/numpy/bls build.

We will:
  1. Call BLSSearchEngine.search() three times in a row on the same
     curve and report each wall time. This shows warm/cold drift.
  2. Use the same curve builder as j3_decompose_bls.py (identical seed,
     parameters).
  3. Compare: first-call wall time vs subsequent calls.
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

from astraeus.analysis.bls_search import BLSSearchEngine

# --- Same curve as j3_decompose_bls.py and e2e_kepler90d_real_path.py -----
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
    print(f"[J3c] Curve: {N_CADENCES} cadences over {BASELINE_D}d "
          f"(cadence {CADENCE_D*24*60:.1f}min, seed={SEED})")
    print(f"[J3c] Python: {sys.version.split()[0]}, numpy: {np.__version__}")

    t, y = make_curve()

    n_repeats = 3
    times = []
    for i in range(n_repeats):
        t0 = time.perf_counter()
        result = BLSSearchEngine.search(t, y, scan_depth=1)
        dt = time.perf_counter() - t0
        times.append(dt)
        print(f"[J3c] call {i+1}/{n_repeats}: search() wall = {dt:.4f}s, "
              f"period={result['period']:.5f}d")

    print("\n[J3c] ===== SUMMARY =====")
    for i, dt in enumerate(times, 1):
        print(f"  call {i}: {dt:8.4f}s")
    print(f"  mean:  {np.mean(times):8.4f}s")
    print(f"  range: [{np.min(times):.4f}, {np.max(times):.4f}]s "
          f"(spread {np.max(times)-np.min(times):.4f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
