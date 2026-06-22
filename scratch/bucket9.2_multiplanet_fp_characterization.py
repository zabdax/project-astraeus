"""Throwaway script: characterize the false-positive rate of
``run_multi_planet_search`` on pure white noise.

Bucket 9.2 / Item 1 (decision gate). Not a test — a diagnostic.

This mirrors scratch/bucket9.1_fp_characterization.py but routes the
50 noise realizations through ``run_multi_planet_search`` (the multi-
planet path that detective.py:284-292 takes in "Multi-Planet Search
Deep-Dive" mode) instead of ``detect_transit_candidate``.

Goal: confirm whether the unconditional DETECTION_CONFIDENCE_FLOOR
applied in detection.py:48-51 also protects the multi-planet path
(transitively, via orchestrator's delegation to detect_transit_candidate).
"""

from __future__ import annotations

import json
import os
import sys
import time
from statistics import mean, median, stdev

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astraeus.core.orchestrator import run_multi_planet_search


def _noise_run(seed: int, sigma: float = 0.01, n: int = 500, T: float = 10.0) -> dict:
    """One pure-noise realization + run_multi_planet_search call."""
    np.random.seed(seed)
    time = np.linspace(0, T, n)
    flux = 1.0 + np.random.normal(0, sigma, n)
    raw_lc = {
        "time": time,
        "flux": flux,
        "target_name": f"NOISE-{seed}",
        "data_source": "synthetic",
        "metadata": {},
    }
    # The orchestrator's snr_floor default is 7.1 (orchestrator.py:92).
    # Use the default to test the realistic path the Detective UI takes.
    discovered = run_multi_planet_search(raw_lc, max_signals=5)

    n_found = len(discovered) if discovered else 0
    fp = n_found > 0
    # Pull SNR / confidence from the first discovered candidate if any.
    snr = float(discovered[0].get("snr", 0.0)) if fp else 0.0
    conf = float(discovered[0].get("confidence_score", 0.0)) if fp else 0.0
    period = float(discovered[0].get("period", 0.0)) if fp else 0.0
    return {
        "seed": seed,
        "candidate_found": fp,
        "n_candidates_found": n_found,
        "confidence_score": conf,
        "snr": snr,
        "period": period,
    }


def _summarise(rows: list[dict]) -> dict:
    if not rows:
        return {}
    fp_rows = [r for r in rows if r["candidate_found"]]
    n_per_fp = [r["n_candidates_found"] for r in fp_rows]
    snr_fp = [r["snr"] for r in fp_rows]
    conf_fp = [r["confidence_score"] for r in fp_rows]
    return {
        "n_total": len(rows),
        "n_runs_with_any_candidate": len(fp_rows),
        "false_positive_rate_any": len(fp_rows) / len(rows),
        "total_false_candidates": sum(n_per_fp),
        "n_candidates_per_fp_run": {
            "n": len(n_per_fp),
            "min": min(n_per_fp) if n_per_fp else None,
            "max": max(n_per_fp) if n_per_fp else None,
            "mean": mean(n_per_fp) if n_per_fp else None,
            "median": median(n_per_fp) if n_per_fp else None,
        },
        "snr_first_fp_candidate": {
            "n": len(snr_fp),
            "min": min(snr_fp) if snr_fp else None,
            "max": max(snr_fp) if snr_fp else None,
            "mean": mean(snr_fp) if snr_fp else None,
            "median": median(snr_fp) if snr_fp else None,
        },
        "confidence_score_first_fp_candidate": {
            "n": len(conf_fp),
            "min": min(conf_fp) if conf_fp else None,
            "max": max(conf_fp) if conf_fp else None,
            "mean": mean(conf_fp) if conf_fp else None,
            "median": median(conf_fp) if conf_fp else None,
        },
    }


def main() -> None:
    seeds = [42] + list(range(100, 100 + 49))  # 50 runs

    rows = []
    t0 = time.time()
    for s in seeds:
        row = _noise_run(s)
        rows.append(row)
        flag = "FP" if row["candidate_found"] else "ok"
        print(
            f"seed={s:>4}  {flag}  n_found={row['n_candidates_found']}  "
            f"snr={row['snr']:8.3f}  conf={row['confidence_score']:8.3f}  "
            f"period={row['period']:8.4f}d",
            flush=True,
        )
    dt = time.time() - t0

    summary = _summarise(rows)
    summary["elapsed_seconds"] = dt

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bucket9.2_multiplanet_fp_characterization.json",
    )
    payload = {
        "noise_parameters": {
            "sigma": 0.01, "n_samples": 500, "duration_days": 10.0,
            "snr_floor": 7.1, "max_signals": 5,
        },
        "summary": summary,
        "rows": rows,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print()
    print("=" * 70)
    print(f"Total realizations: {summary['n_total']}")
    print(f"Runs with any FP:   {summary['n_runs_with_any_candidate']} "
          f"({summary['false_positive_rate_any'] * 100:.1f}%)")
    print(f"Total FP candidates: {summary['total_false_candidates']}")
    if summary["n_candidates_per_fp_run"]["n"] > 0:
        s = summary["n_candidates_per_fp_run"]
        print(f"FP candidates per run: min={s['min']}  med={s['median']}  max={s['max']}  mean={s['mean']:.2f}")
        s = summary["snr_first_fp_candidate"]
        print(f"SNR (first FP): min={s['min']:.3f}  med={s['median']:.3f}  max={s['max']:.3f}  mean={s['mean']:.3f}")
        s = summary["confidence_score_first_fp_candidate"]
        print(f"conf (first FP): min={s['min']:.3f}  med={s['median']:.3f}  max={s['max']:.3f}  mean={s['mean']:.3f}")
    print()
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
