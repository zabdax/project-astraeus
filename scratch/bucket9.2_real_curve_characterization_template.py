"""Throwaway script TEMPLATE — characterize detect_transit_candidate
on REAL Kepler/TESS light curves.

Bucket 9.2 / Item 4 (OPTIONAL). Not a test — a stub for a future
real-curve characterization bucket.

The bucket 9.1 audit's "clean gap" claim (and the
DETECTION_CONFIDENCE_FLOOR = 7.0 threshold chosen inside it) was
measured against SYNTHETIC fixtures only:
- 50 pure-noise realizations (sigma=0.01, n=500, T=10d).
- 5 synthetic real-signal guardrail scenarios from
  tests/test_pipeline_smoke.py, tests/test_vetting_threshold_hardening.py,
  and tests/test_agent_detective.py::test_signal_recovery.

Real Kepler/TESS marginal detections (shallow transits, grazing
geometries, noisy giant-star photometry, non-Gaussian noise,
instrument systematics) can legitimately produce SNR /
confidence_score values below the synthetic floor and would be
silently rejected by the 7.0 confidence_score floor. The rejection
rate on real marginal detections is UNCHARACTERIZED.

This file is a TEMPLATE only — it does NOT fetch real curves and does
NOT exercise the detector on them. The future bucket should:

1. Curate a set of known Kepler/TESS marginal detections. Suggested
   sources:
   - Kepler "Earth-like candidate" working list
     (https://exoplanetarchive.ipac.caltech.edu/)
   - TESS TOI catalog at the low-confidence end (TOI confidence
     "1.0 - 0.5" bin)
   - Known eclipsing binaries with shallow / grazing geometries
     (to test the false-negative side)

2. For each, load the light curve, run detect_transit_candidate, and
   record:
   - candidate_found (True/False — was the planet caught?)
   - confidence_score (the load-bearing gate value)
   - snr (the secondary check)
   - period (the recovered period)
   - vetting_status (the post-bls verdict)
   - expected_period (the catalog period, for comparison)

3. Compute the rejection rate:
   - TP = candidate_found=True AND expected_period within tolerance
   - FN = candidate_found=False AND catalog has a known planet
   - FP = candidate_found=True AND catalog has no planet
   - TN = candidate_found=False AND catalog has no planet
   - rejection_rate = FN / (TP + FN)

4. If rejection_rate > 0.10 (more than 10% of marginal detections
   rejected), recommend lowering DETECTION_CONFIDENCE_FLOOR. If
   rejection_rate < 0.05, the current value is empirically validated
   for real data too.

The structure below mirrors scratch/bucket9.1_real_signal_characterization.py
so the future bucket can drop in real-curve loading with minimal
churn.
"""

from __future__ import annotations

import json
import os
import sys
import time
from statistics import mean, median
from typing import Any

import numpy as np

# Future bucket: replace this import with a real-curve loader.
# from astraeus.core.ingestion import RemoteDiscoveryEngine, DataAdapter
# from astraeus.core.archive import load_kepler_target, load_tess_toi

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astraeus.analysis.detection import detect_transit_candidate


def _load_real_curve(target_id: str, source: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """TODO: replace with real-curve loader.

    Returns: (time, flux, metadata) for the given target.

    Suggested backends per source:
      - "kepler": astraeus.core.archive.load_kepler_target(target_id)
      - "tess":   astraeus.core.archive.load_tess_toi(target_id)
      - "manual": astraeus.core.ingestion.RemoteDiscoveryEngine.fetch(target_id)
    """
    raise NotImplementedError(
        "Real-curve loader not implemented in this bucket. "
        "The 7.0 confidence floor's real-world rejection rate is "
        "UNCHARACTERIZED — see reports/bucket9.1_summary.md §6.5."
    )


def _real_curve_run(target_id: str, source: str, expected_period_days: float) -> dict:
    """One real-curve target + detection call. Returns a flat row dict."""
    time, flux, metadata = _load_real_curve(target_id, source)
    res = detect_transit_candidate(time, flux, metadata=metadata, snr_threshold=5.0)
    candidate = bool(res.get("candidate_found", res.get("is_candidate", False)))
    recovered_period = float(res.get("period", res.get("period_days", 0.0)))
    return {
        "target_id": target_id,
        "source": source,
        "expected_period_days": expected_period_days,
        "candidate_found": candidate,
        "is_candidate": candidate,
        "confidence_score": float(res.get("confidence_score", 0.0)),
        "snr": float(res.get("snr", 0.0)),
        "recovered_period_days": recovered_period,
        "period_error_fraction": (
            abs(recovered_period - expected_period_days) / expected_period_days
            if expected_period_days > 0 else None
        ),
        "vetting_status": str(res.get("vetting_status", "")),
    }


def _summarise(rows: list[dict]) -> dict:
    """Rejection / acceptance summary across the real-curve set."""
    if not rows:
        return {}
    conf = [r["confidence_score"] for r in rows]
    snr = [r["snr"] for r in rows]
    # True positive: candidate_found AND period within 5% of expected.
    tp = [r for r in rows if r["candidate_found"] and
          r["period_error_fraction"] is not None and
          r["period_error_fraction"] <= 0.05]
    # False negative: candidate NOT found AND expected_period > 0.
    fn = [r for r in rows if not r["candidate_found"] and r["expected_period_days"] > 0]
    return {
        "n_total": len(rows),
        "n_true_positive": len(tp),
        "n_false_negative": len(fn),
        "rejection_rate": len(fn) / max(1, len(tp) + len(fn)),
        "snr": {
            "min": min(snr), "max": max(snr),
            "median": median(snr), "mean": mean(snr),
        },
        "confidence_score": {
            "min": min(conf), "max": max(conf),
            "median": median(conf), "mean": mean(conf),
        },
    }


# Suggested starting target list — TODO: curate from the Kepler/TESS
# catalogs above. Each tuple is (target_id, source, expected_period_days).
_CURATED_TARGETS: list[tuple[str, str, float]] = [
    # (target_id, "kepler"|"tess", expected_period_days)
    # TODO: populate with 20-50 known marginal detections.
]


def main() -> None:
    if not _CURATED_TARGETS:
        print("=" * 70)
        print("Bucket 9.2 Item 4 template — no targets configured yet.")
        print()
        print("To enable real-curve characterization:")
        print("1. Populate _CURATED_TARGETS with 20-50 known marginal detections.")
        print("2. Implement _load_real_curve() to fetch from Kepler/TESS archives.")
        print("3. Re-run. Report will be written to")
        print("   scratch/bucket9.2_real_curve_characterization.json.")
        print()
        print("Until then, the 7.0 confidence floor's real-world rejection")
        print("rate remains UNCHARACTERIZED — see reports/bucket9.1_summary.md")
        print("§6.5 for the limitation note.")
        print("=" * 70)
        return

    rows: list[dict[str, Any]] = []
    t0 = time.time()
    for target_id, source, expected_period in _CURATED_TARGETS:
        row = _real_curve_run(target_id, source, expected_period)
        rows.append(row)
        flag = "OK" if row["candidate_found"] else "MISS"
        print(
            f"{target_id:<30}  {source:<8}  {flag}  "
            f"snr={row['snr']:8.3f}  conf={row['confidence_score']:8.3f}  "
            f"recovered={row['recovered_period_days']:.4f}d  "
            f"expected={expected_period:.4f}d",
            flush=True,
        )
    dt = time.time() - t0

    summary = _summarise(rows)
    summary["elapsed_seconds"] = dt

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bucket9.2_real_curve_characterization.json",
    )
    payload = {
        "summary": summary,
        "rows": rows,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print()
    print("=" * 70)
    print(f"Total targets: {summary['n_total']}")
    print(f"True positives: {summary['n_true_positive']}")
    print(f"False negatives: {summary['n_false_negative']}")
    print(f"Rejection rate: {summary['rejection_rate'] * 100:.1f}%")
    print()
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
