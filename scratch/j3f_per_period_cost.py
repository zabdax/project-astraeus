"""Phase 1, J3f: Per-period cost non-uniformity in model.power().

The p_max ablation showed: n_periods barely moves (795688 -> 791691
-> 783694, ~1.5% change) while model.power time drops 29% (136.9s
-> 97.5s) as p_max shrinks. If cost were purely N_periods * N_dur *
N_cad, time should track period count, not diverge from it by this
much.

Hypothesis: longer periods are more expensive per evaluation because
the inner kernel scales with the number of in-transit cadences,
which scales with duration/period (or with the folding period
itself in some implementations). Test by evaluating model.power on
N=10000 uniformly-spaced periods sampled from three non-overlapping
period bands: 0.5-2d (short), 20-50d (mid), 50-100d (long).

If the per-period cost is uniform, all three should take ~ the same
time (2000x fewer periods than the full grid, so ~0.4s each).
If the hypothesis holds, the long band will be measurably slower.
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

BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0
N_CADENCES = int(BASELINE_D / CADENCE_D)
SEED = 20260706
N_PER_BAND = 10000
PERIOD_BANDS = [
    ("short (0.5-2d)", 0.5, 2.0),
    ("mid   (20-50d)", 20.0, 50.0),
    ("long  (50-100d)", 50.0, 100.0),
]
DURATIONS = np.array([0.1])


def make_curve():
    rng = np.random.default_rng(seed=SEED)
    t = np.arange(N_CADENCES) * CADENCE_D
    y = 1.0 + 100e-6 * rng.standard_normal(N_CADENCES)
    return t, y


def measure_band(t, y, p_lo: float, p_hi: float, n_periods: int) -> dict:
    model = BoxLeastSquares(t, y)
    periods = np.linspace(p_lo, p_hi, n_periods)
    t0 = time.perf_counter()
    res = model.power(periods, DURATIONS)
    dt = time.perf_counter() - t0
    del res
    return {
        "n_periods": n_periods,
        "p_lo": p_lo,
        "p_hi": p_hi,
        "seconds": dt,
        "us_per_period": 1e6 * dt / n_periods,
    }


def main() -> int:
    print(f"[J3f] Curve: {N_CADENCES} cadences over {BASELINE_D}d")
    t, y = make_curve()
    rows = []
    for name, p_lo, p_hi in PERIOD_BANDS:
        r = measure_band(t, y, p_lo, p_hi, N_PER_BAND)
        r["band"] = name
        rows.append(r)
        print(f"  {name}: {r['seconds']:.4f}s "
              f"({r['us_per_period']:.2f} us/period)")

    print("\n[J3f] ===== PER-PERIOD COST BY BAND =====")
    short_us = rows[0]["us_per_period"]
    for r in rows:
        ratio = r["us_per_period"] / short_us if short_us > 0 else float("nan")
        print(f"  {r['band']:>18}: {r['us_per_period']:7.2f} us/period  "
              f"(ratio to short: {ratio:.2f}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
