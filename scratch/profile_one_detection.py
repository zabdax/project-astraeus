"""
profile_one_detection.py
========================

The e2e (orchestrator -> daemon worker -> detect_transit_candidate) is
hanging in the first iteration for >9 minutes on a 5k-cadence / 365d
synthetic curve with P=59.74d injected. We need to know which call
inside detect_transit_candidate is slow.

This script runs detect_transit_candidate *in-process* (no daemon, no
orchestrator) on the same synthetic curve and times each major step:

  1. DetrendingEngine.estimate_stellar_rotation
  2. DetrendingEngine.detrend
  3. BLSSearchEngine.search   (BLS autoperiod + power + alias rejection)
  4. TLS call                  (transitleastsquares + model.power)

The sum should match what the orchestrator's worker experiences in
iteration 1.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the same curve builder as the e2e script.
sys.path.insert(0, str(PROJECT_ROOT / "scratch"))
from e2e_kepler90d_real_path import (
    BASELINE_D,
    CADENCE_D,
    N_CADENCES,
    NOISE_PPM,
    KEPLER90D_PERIOD_D,
    KEPLER90D_DEPTH_PPM,
    KEPLER90D_DURATION_D,
    KEPLER90D_T0_BJD,
    make_kepler90d_curve,
)


def fmt(s: float) -> str:
    if s < 60:
        return f"{s:6.2f}s"
    return f"{s/60:6.2f}m"


def main() -> None:
    print(f"[profile] building curve ({N_CADENCES} cadences, {BASELINE_D}d baseline)")
    t0 = time.perf_counter()
    t, y = make_kepler90d_curve()
    print(f"[profile]   build took {fmt(time.perf_counter() - t0)}")

    from astraeus.analysis.detrending import DetrendingEngine
    from astraeus.analysis.bls_search import BLSSearchEngine
    from astraeus.analysis.detection import detect_transit_candidate

    # --- 1. estimate_stellar_rotation --------------------------------------
    t0 = time.perf_counter()
    stellar_rot = DetrendingEngine.estimate_stellar_rotation(t, y)
    s1 = time.perf_counter() - t0
    print(f"[profile] 1. estimate_stellar_rotation  = {fmt(s1)}   (returned {stellar_rot:.4f}d)")

    # --- 2. detrend --------------------------------------------------------
    t0 = time.perf_counter()
    flux_detrended = DetrendingEngine.detrend(t, y, stellar_rot)
    s2 = time.perf_counter() - t0
    print(f"[profile] 2. detrend                    = {fmt(s2)}   (len={len(flux_detrended)})")

    # --- 3. BLSSearchEngine.search ----------------------------------------
    t0 = time.perf_counter()
    bls_result = BLSSearchEngine.search(t, flux_detrended, known_periods=[])
    s3 = time.perf_counter() - t0
    print(f"[profile] 3. BLSSearchEngine.search     = {fmt(s3)}")
    print(f"[profile]    best_period={bls_result['period']:.4f}d  snr={bls_result['snr']:.2f}  "
          f"depth={bls_result['depth']:.6f}  duration={bls_result['duration']:.4f}d")

    # --- 4. Full detect_transit_candidate (includes TLS) -------------------
    metadata = {
        "st_rad": 1.2,
        "st_teff": 5930.0,
        "st_mass": 1.13,
        "sy_jmag": 12.49,
    }
    t0 = time.perf_counter()
    result = detect_transit_candidate(
        time=t, flux=y,
        target_name="profile-test",
        data_source="synthetic",
        metadata=metadata,
        snr_threshold=5.0,
        known_periods=[],
    )
    s4 = time.perf_counter() - t0
    print(f"[profile] 4. detect_transit_candidate   = {fmt(s4)}   (sum-of-steps should be < s4)")

    print()
    print(f"[profile] summary: stellar_rot={fmt(s1)} + detrend={fmt(s2)} + BLS={fmt(s3)} + (TLS) ≈ {fmt(s4)}")
    print(f"[profile] implied TLS + alias-rejection inner cost = {fmt(s4 - s1 - s2 - s3)}")
    print(f"[profile] candidate emitted: vetted={result.get('vetting_status')!r}  "
          f"snr={result.get('snr'):.2f}  tls_valid={result.get('tls_valid')}  "
          f"tls_sde={result.get('tls_sde')}")


if __name__ == "__main__":
    main()
