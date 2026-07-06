"""Phase 1, H5: Profile BLSSearchEngine.search() wall-clock cost vs baseline length.

Reports seconds_per_sample scaling. No astraeus/ source changes; pure diagnostic.
"""
import time
import sys
import os

# Ensure project root is on sys.path so astraeus imports work when run from scratch/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import numpy as np
from astraeus.analysis.bls_search import BLSSearchEngine

# Hard cap on a single .search() call: 300 seconds.
PER_CALL_TIMEOUT_S = 300.0
BASELINES = [30, 90, 365, 1460]
SAMPLES_PER_DAY = 48  # 30-min cadence
NOISE_STD = 5e-4
FLUX_LEVEL = 1.0
SEED = 42


def run_one(baseline_days: int, scan_depth: int = 1) -> dict:
    n_samples = baseline_days * SAMPLES_PER_DAY
    rng = np.random.default_rng(SEED)
    time_arr = np.linspace(0.0, float(baseline_days), n_samples, endpoint=False)
    flux = FLUX_LEVEL + rng.normal(0.0, NOISE_STD, size=n_samples)

    t_start = time.perf_counter()
    timed_out = False
    error_msg = None
    try:
        result = BLSSearchEngine.search(time_arr, flux, scan_depth=scan_depth)
        elapsed = time.perf_counter() - t_start
    except Exception as e:
        elapsed = time.perf_counter() - t_start
        error_msg = f"{type(e).__name__}: {e}"
        result = None

    if elapsed > PER_CALL_TIMEOUT_S:
        timed_out = True
        print(f"[H5] TIMEOUT at baseline_days={baseline_days} "
              f"(elapsed={elapsed:.2f}s exceeded {PER_CALL_TIMEOUT_S}s cap)")
        return {
            "baseline_days": baseline_days,
            "n_samples": n_samples,
            "bls_seconds": float("nan"),
            "seconds_per_sample": float("nan"),
            "timed_out": True,
            "error": error_msg,
        }

    print(f"[H5] baseline_days={baseline_days} n_samples={n_samples} "
          f"bls_seconds={elapsed:.4f}"
          + (f" ERROR={error_msg}" if error_msg else ""))
    return {
        "baseline_days": baseline_days,
        "n_samples": n_samples,
        "bls_seconds": elapsed,
        "seconds_per_sample": elapsed / n_samples,
        "timed_out": False,
        "error": error_msg,
    }


def main() -> int:
    print(f"[H5] Starting BLS profiling. "
          f"Per-call timeout = {PER_CALL_TIMEOUT_S}s, scan_depth=1 (default).")
    print(f"[H5] Project root: {PROJECT_ROOT}")
    print(f"[H5] Python: {sys.version.split()[0]}, numpy: {np.__version__}")

    rows = []
    for b in BASELINES:
        row = run_one(b, scan_depth=1)
        rows.append(row)
        if row["timed_out"]:
            # Don't continue to longer baselines once we've hit timeout on
            # the current one - they will be even slower.
            print(f"[H5] Aborting remaining baselines after timeout on "
                  f"baseline_days={b}.")
            break

    # Coarse-mode call on 1460-day dataset for comparison, if it completed.
    coarse_row = None
    last_completed = next((r for r in reversed(rows) if not r["timed_out"]), None)
    if last_completed and last_completed["baseline_days"] >= 1460 and not last_completed["timed_out"]:
        print("[H5] Running coarse-mode (scan_depth=0) on 1460-day dataset...")
        coarse_row = run_one(1460, scan_depth=0)

    # Summary table.
    print("\n[H5] ===== SUMMARY =====")
    header = f"{'baseline_days':>14} | {'n_samples':>10} | {'bls_seconds':>12} | {'seconds_per_sample':>18}"
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["timed_out"] or r["bls_seconds"] != r["bls_seconds"]:  # NaN check
            print(f"{r['baseline_days']:>14} | {r['n_samples']:>10} | "
                  f"{'TIMEOUT':>12} | {'TIMEOUT':>18}")
        else:
            print(f"{r['baseline_days']:>14} | {r['n_samples']:>10} | "
                  f"{r['bls_seconds']:>12.4f} | {r['seconds_per_sample']:>18.6e}")
    if coarse_row is not None:
        tag = "1460 (coarse, scan_depth=0)"
        if coarse_row["timed_out"]:
            print(f"{tag:>14} | {coarse_row['n_samples']:>10} | "
                  f"{'TIMEOUT':>12} | {'TIMEOUT':>18}")
        else:
            print(f"{tag:>14} | {coarse_row['n_samples']:>10} | "
                  f"{coarse_row['bls_seconds']:>12.4f} | "
                  f"{coarse_row['seconds_per_sample']:>18.6e}")

    # Verdict: compare seconds_per_sample at 30 vs 1460.
    by_baseline = {r["baseline_days"]: r for r in rows if not r["timed_out"]}
    verdict = "indeterminate (missing endpoint data)"
    if 30 in by_baseline and 1460 in by_baseline:
        sps_30 = by_baseline[30]["seconds_per_sample"]
        sps_1460 = by_baseline[1460]["seconds_per_sample"]
        growth = sps_1460 / sps_30 if sps_30 > 0 else float("inf")
        print(f"\n[H5] seconds_per_sample growth 30d -> 1460d: {growth:.2f}x")
        if growth > 2.0:
            verdict = "algorithmic_change_needed"
        else:
            verdict = "infrastructure_change_needed"
    print(f"[H5] VERDICT: {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
