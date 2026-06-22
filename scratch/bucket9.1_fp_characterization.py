"""Throwaway script: characterize the false-positive rate of
``detect_transit_candidate`` on pure white noise.

Bucket 9.1 / Phase 1.3. Not a test — a diagnostic.

For each of N independent noise realizations, this script:
- Builds np.random.normal(0, sigma, n_samples) flux with seed ``s``
  on np.linspace(0, T, n_samples) time.
- Calls detect_transit_candidate with snr_threshold=5.0.
- Records: candidate_found, confidence_score, snr, period, depth.

The output (printed + written to scratch/bucket9.1_fp_characterization.json)
tells us:
- The false-positive RATE: what fraction of pure-noise runs trip
  candidate_found=True?
- The distribution of confidence_score and snr on the spurious peaks.
- Whether a single threshold change can separate noise from real signals.

The same noise parameters as test_noise_injection (seed=42, sigma=0.01,
n=500, T=10) are the seed for the first row; subsequent rows use
independent seeds 100..N+99.
"""

from __future__ import annotations

import json
import os
import sys
import time
from statistics import mean, median, stdev

import numpy as np

# Make the project importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astraeus.analysis.detection import detect_transit_candidate


def _noise_run(seed: int, sigma: float = 0.01, n: int = 500, T: float = 10.0) -> dict:
    """One pure-noise realization + detection call. Returns a flat row dict."""
    np.random.seed(seed)
    time = np.linspace(0, T, n)
    flux = 1.0 + np.random.normal(0, sigma, n)
    results = detect_transit_candidate(time, flux, snr_threshold=5.0)
    return {
        "seed": seed,
        "candidate_found": bool(results.get("candidate_found", results.get("is_candidate", False))),
        "is_candidate": bool(results.get("is_candidate", results.get("candidate_found", False))),
        "confidence_score": float(results.get("confidence_score", 0.0)),
        "snr": float(results.get("snr", 0.0)),
        "period": float(results.get("period", results.get("period_days", 0.0))),
        "transit_depth": float(results.get("transit_depth", 0.0)),
        "duration": float(results.get("duration", 0.0)),
    }


def _summarise(rows: list[dict]) -> dict:
    """Summary stats over a list of noise-run row dicts."""
    if not rows:
        return {}
    fp_rows = [r for r in rows if r["candidate_found"]]
    snr_all = [r["snr"] for r in rows]
    snr_fp = [r["snr"] for r in fp_rows]
    conf_all = [r["confidence_score"] for r in rows]
    conf_fp = [r["confidence_score"] for r in fp_rows]
    return {
        "n_total": len(rows),
        "n_false_positives": len(fp_rows),
        "false_positive_rate": len(fp_rows) / len(rows),
        "snr_all": {
            "min": min(snr_all), "max": max(snr_all),
            "mean": mean(snr_all), "median": median(snr_all),
            "stdev": stdev(snr_all) if len(snr_all) > 1 else 0.0,
        },
        "snr_false_positives": {
            "n": len(snr_fp),
            "min": min(snr_fp) if snr_fp else None,
            "max": max(snr_fp) if snr_fp else None,
            "mean": mean(snr_fp) if snr_fp else None,
            "median": median(snr_fp) if snr_fp else None,
        },
        "confidence_score_all": {
            "min": min(conf_all), "max": max(conf_all),
            "mean": mean(conf_all), "median": median(conf_all),
        },
        "confidence_score_false_positives": {
            "n": len(conf_fp),
            "min": min(conf_fp) if conf_fp else None,
            "max": max(conf_fp) if conf_fp else None,
            "mean": mean(conf_fp) if conf_fp else None,
            "median": median(conf_fp) if conf_fp else None,
        },
    }


def main() -> None:
    # Match the test_noise_injection fixture for the first row, then sweep
    # 49 more independent seeds so we have 50 realizations total.
    seeds = [42] + list(range(100, 100 + 49))  # 50 runs

    rows = []
    t0 = time.time()
    for s in seeds:
        row = _noise_run(s)
        rows.append(row)
        # Print a one-line summary per run so we can tail it interactively.
        flag = "FP" if row["candidate_found"] else "ok"
        print(
            f"seed={s:>4}  {flag}  snr={row['snr']:8.3f}  "
            f"conf={row['confidence_score']:8.3f}  "
            f"period={row['period']:8.4f}d  "
            f"depth={row['transit_depth']:.4f}",
            flush=True,
        )
    dt = time.time() - t0

    summary = _summarise(rows)
    summary["elapsed_seconds"] = dt

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bucket9.1_fp_characterization.json",
    )
    payload = {
        "noise_parameters": {
            "sigma": 0.01, "n_samples": 500, "duration_days": 10.0,
            "snr_threshold": 5.0,
        },
        "summary": summary,
        "rows": rows,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print()
    print("=" * 70)
    print(f"Total realizations: {summary['n_total']}")
    print(f"False positives:    {summary['n_false_positives']} "
          f"({summary['false_positive_rate'] * 100:.1f}%)")
    print(f"Elapsed:            {dt:.1f}s")
    print()
    print("SNR distribution (all runs):")
    print(f"  min={summary['snr_all']['min']:.3f}  "
          f"median={summary['snr_all']['median']:.3f}  "
          f"mean={summary['snr_all']['mean']:.3f}  "
          f"max={summary['snr_all']['max']:.3f}  "
          f"stdev={summary['snr_all']['stdev']:.3f}")
    print(f"SNR distribution (false positives only, n={summary['snr_false_positives']['n']}):")
    if summary["snr_false_positives"]["n"] > 0:
        print(f"  min={summary['snr_false_positives']['min']:.3f}  "
              f"median={summary['snr_false_positives']['median']:.3f}  "
              f"mean={summary['snr_false_positives']['mean']:.3f}  "
              f"max={summary['snr_false_positives']['max']:.3f}")
    print()
    print("confidence_score distribution (all runs):")
    print(f"  min={summary['confidence_score_all']['min']:.3f}  "
          f"median={summary['confidence_score_all']['median']:.3f}  "
          f"mean={summary['confidence_score_all']['mean']:.3f}  "
          f"max={summary['confidence_score_all']['max']:.3f}")
    print()
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
