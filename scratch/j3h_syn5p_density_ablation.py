"""Phase 1, J3h: Coarse grid density ablation on SYN-5P-small.

Measures how many of the 5 injected signals are recovered as a function
of the coarse-grid period count. The reviewer requires that any
proposed fix be validated against SYN-5P before merge, not just on a
single-signal curve.

This is a measurement, not a recommendation. It is intended to inform
the design decision for the coarse->refine approach, not to approve or
reject any particular grid size.
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

INJECTED_5P = [
    ("p1",  12.0,  500,  5.0,   0.15),
    ("p2",  45.0,  1000, 22.0,  0.25),
    ("p3", 120.0,  800,  80.0,  0.40),
    ("p4", 300.0,  1500, 200.0,  0.60),
    ("p5", 600.0,  2000, 450.0,  0.80),
]
N_SAMPLES = 3000
T_SPAN = 1500.0
SEED = 42
DURATIONS = (0.05, 0.1, 0.2, 0.4, 0.6)
TOP_N_FOR_RECOVERY = 50
N_COARSE_OPTIONS = [2000, 5000, 10000, 20000, 50000, 100000, 200000]


def make_5p_curve():
    rng = np.random.default_rng(seed=SEED)
    t = np.linspace(0, T_SPAN, N_SAMPLES)
    y = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)
    for name, period, depth_ppm, t0, dur in INJECTED_5P:
        phase = ((t - t0) % period) - period / 2.0
        y[np.abs(phase) < dur / 2.0] -= depth_ppm / 1e6
    return t, y


def check_recovered(top_periods, tolerance_frac=0.02):
    """For each injected planet, return True if any top-N period is within tolerance."""
    found = []
    for (n, p, *_r) in INJECTED_5P:
        matched = any(abs(tp - p) / p <= tolerance_frac for tp in top_periods)
        if matched:
            found.append(f"{n}@{p}d")
    return found


def main() -> int:
    print(f"[J3h] SYN-5P-small: N={N_SAMPLES} T={T_SPAN}d")
    t, y = make_5p_curve()
    m = BoxLeastSquares(t, y)

    rows = []
    for n_coarse in N_COARSE_OPTIONS:
        periods = np.geomspace(0.5, 450.0, n_coarse)
        durs = np.array(DURATIONS)
        durs = durs[durs < periods.min()]

        t0 = time.perf_counter()
        res = m.power(periods, durs)
        dt = time.perf_counter() - t0

        pw = res.power.ravel()
        ps = res.period.ravel()
        top_idx = np.argsort(pw)[::-1][:TOP_N_FOR_RECOVERY]
        top_periods = ps[top_idx]
        found = check_recovered(top_periods)

        row = {
            'n_coarse': n_coarse,
            'n_durations': len(durs),
            'n_pairs': len(pw),
            'seconds': dt,
            'top_periods': [float(tp) for tp in top_periods[:10]],
            'top_powers': [float(pw[i]) for i in top_idx[:10]],
            'recovered_in_top50': found,
            'recovered_count': len(found),
        }
        rows.append(row)
        print(f"  n_coarse={n_coarse:>7}: {dt:7.2f}s  n_pairs={len(pw):>8}  "
              f"recovered {len(found)}/5  -> {found}")

    out_path = SCRIPT_DIR / "j3h_syn5p_density_ablation.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\n[J3h] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
