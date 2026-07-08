"""J7b — Real-curve measurement with PROPER upstream pipeline (Step 0 fix).

The J7 script (j7_real_curve_measure.py) called BLSSearchEngine.search()
directly on the raw stitched flux, which the round-7 review correctly
flagged as a test-harness gap: the production path in
astraeus/analysis/detection.py:detect_transit_candidate applies
DetrendingEngine.estimate_stellar_rotation + DetrendingEngine.detrend
BEFORE handing flux to BLS. J7 bypassed both steps.

This script does it the right way:
  1. Stitch + remove_nans() on cached FITS (same as J7).
  2. estimate_stellar_rotation(time, flux)  -- rotation period days
  3. detrend(time, flux, rotation)          -- flatten long-term systematics
  4. BLSSearchEngine.search 3x with iterative known_periods alias-rejection
  5. Report per-iter wall, recovered periods, and which known planets hit

The J7 result (SNR=98.07 at P=517d, dur=0.4d winning at three unrelated
periods) is the textbook signature of an undetrended long-term trend
dominating the periodogram. Re-running with detrending will either:
  (a) recover Kepler-90d/h as the round-3 e2e test (synthetic) suggested,
      confirming the round-7 BLS changes are fine; or
  (b) still fail, pointing at a real recovery bug in the new code.

Either answer is what the round-7 gate needed. Network-free: reuses the
12 cached FITS files in $TEMP/astraeus_h1_kepler90_measurement/download_all.
"""
from __future__ import annotations

import json
import os
import sys
import time
import glob
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_TEMP_CACHE = os.path.join(
    os.environ.get("TEMP", "/tmp"),
    "astraeus_h1_kepler90_measurement",
    "download_all",
)

KNOWN_PERIODS = {
    "Kepler-90b": 7.0085,
    "Kepler-90c": 8.7194,
    "Kepler-90d": 59.7367,
    "Kepler-90e": 91.9391,
    "Kepler-90f": 124.9144,
    "Kepler-90g": 210.6069,
    "Kepler-90h": 331.6453,
    "Kepler-90i": 14.4491,
}
RECOVERY_TOL = 0.01  # 1% on period (matches test_j3_orchestrator_e2e_verified.py)


def _load_stitched_curve() -> tuple[np.ndarray, np.ndarray]:
    import lightkurve as lk
    fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
    print(f"[J7b] found {len(fits_files)} FITS files under {_TEMP_CACHE}", flush=True)
    if len(fits_files) < 12:
        raise FileNotFoundError(
            f"expected >=12 FITS files in {_TEMP_CACHE}, got {len(fits_files)}. "
            "Run scratch/h1_kepler90_measurement.py first to populate the cache."
        )
    lcs = []
    for fp in fits_files[:12]:
        lc = lk.read(fp)
        if hasattr(lc, "PDCSAP_FLUX") and lc.PDCSAP_FLUX is not None:
            lcs.append(lc.PDCSAP_FLUX)
        elif hasattr(lc, "SAP_FLUX") and lc.SAP_FLUX is not None:
            lcs.append(lc.SAP_FLUX)
        else:
            lcs.append(lc)
    stitched = lk.LightCurveCollection(lcs).stitch()
    flat = stitched.remove_nans()
    t = np.asarray(flat.time.value, dtype=np.float64)
    f = np.asarray(flat.flux.value, dtype=np.float64)
    return t, f


def _classify_recovery(period: float) -> str | None:
    for name, true_p in KNOWN_PERIODS.items():
        if abs(period - true_p) / true_p <= RECOVERY_TOL:
            return name
    return None


def main() -> int:
    print("=" * 78, flush=True)
    print("[J7b] Real-curve measurement w/ PROPER detrending — Kepler-90 "
          "(KIC 011442793) stitch, J3 adaptive frequency_factor + widened p_max", flush=True)
    print("=" * 78, flush=True)

    t0_load = time.perf_counter()
    t, f_raw = _load_stitched_curve()
    load_s = time.perf_counter() - t0_load
    T_baseline = float(t.max() - t.min())
    n_cadences = int(len(t))
    print(f"[J7b] stitched: T_baseline={T_baseline:.4f} d  n_cadences={n_cadences}  "
          f"load_s={load_s:.2f}", flush=True)

    # ── Production-path upstream pipeline ─────────────────────────────────
    # detect_transit_candidate calls these in this order:
    #   stellar_rotation_period_days = estimate_stellar_rotation(time, flux)
    #   flux = detrend(time, flux, stellar_rotation_period_days)
    from astraeus.analysis.detrending import DetrendingEngine
    from astraeus.analysis.bls_search import BLSSearchEngine

    t0_rot = time.perf_counter()
    rotation = DetrendingEngine.estimate_stellar_rotation(t, f_raw)
    rot_s = time.perf_counter() - t0_rot
    print(f"[J7b] estimate_stellar_rotation = {rotation:.3f} d  ({rot_s:.2f}s)", flush=True)

    t0_detrend = time.perf_counter()
    f = DetrendingEngine.detrend(t, f_raw, rotation)
    detrend_s = time.perf_counter() - t0_detrend
    # Detrending usually returns 1 + delta. Report both.
    f_med = float(np.nanmedian(f))
    f_std = float(np.nanstd(f))
    print(f"[J7b] detrend: median={f_med:.6f}  std={f_std:.2e}  ({detrend_s:.2f}s)", flush=True)
    f_raw_std = float(np.nanstd(f_raw))
    print(f"[J7b] (raw flux std for comparison: {f_raw_std:.2e}; "
          f"ratio detrended/raw = {f_std/f_raw_std:.3f})", flush=True)

    # ── Iterative BLS search ─────────────────────────────────────────────
    n_iters = 3
    print(f"[J7b] expected adaptive frequency_factor = "
          f"max(1.0, T_baseline^2/4500) = max(1.0, {T_baseline**2/4500.0:.1f}) "
          f"capped at 500", flush=True)
    print(f"[J7b] expected p_max = T_baseline/2 = {T_baseline/2.0:.1f} d", flush=True)

    accepted: list[dict] = []
    iter_rows: list[dict] = []
    wall_total = 0.0
    for it in range(n_iters):
        t0_iter = time.perf_counter()
        try:
            r = BLSSearchEngine.search(t, f, known_periods=[a["period"] for a in accepted])
            iter_s = time.perf_counter() - t0_iter
            wall_total += iter_s
            row = {
                "iteration": it,
                "wall_s": round(iter_s, 2),
                "period": r.get("period"),
                "snr": r.get("snr"),
                "depth": r.get("depth"),
                "duration": r.get("duration"),
                "confidence_score": r.get("confidence_score"),
            }
            iter_rows.append(row)
            print(
                f"[J7b] iter={it}  wall={iter_s:6.2f}s  P={r.get('period'):.4f}d  "
                f"SNR={r.get('snr'):.2f}  dur={r.get('duration'):.4f}d  "
                f"conf={r.get('confidence_score'):.3f}",
                flush=True,
            )
            if r.get("period") is not None and r.get("snr", 0.0) > 0.0:
                accepted.append({"period": float(r["period"]), "snr": float(r["snr"])})
        except Exception as exc:
            iter_s = time.perf_counter() - t0_iter
            wall_total += iter_s
            iter_rows.append({"iteration": it, "wall_s": round(iter_s, 2), "error": repr(exc)})
            print(f"[J7b] iter={it}  ERROR after {iter_s:.2f}s: {exc!r}", flush=True)
            break

    # Recovery verdict
    recovered_names: set[str] = set()
    recovery: list[dict] = []
    for a in accepted:
        name = _classify_recovery(a["period"])
        if name is not None:
            recovered_names.add(name)
        recovery.append({
            "period": a["period"],
            "snr": a["snr"],
            "matched_planet": name,
        })
    for a in accepted:
        name = _classify_recovery(a["period"])
        if name:
            print(f"[J7b] RECOVERED  {name}  P={a['period']:.4f}d  "
                  f"(truth={KNOWN_PERIODS[name]:.4f}d)", flush=True)
        else:
            print(f"[J7b] candidate P={a['period']:.4f}d  snr={a['snr']:.2f}  "
                  f"(no known-planet match)", flush=True)

    print("=" * 78, flush=True)
    print(f"[J7b] TOTAL wall (3 iters): {wall_total:.2f}s  ({wall_total/60:.1f}min)", flush=True)
    print(f"[J7b] round-1 I5 reference: 161.3s per call (OLD code, also undetrended)", flush=True)
    print(f"[J7b] recovered {len(recovered_names)}/{len(KNOWN_PERIODS)} known planets: "
          f"{sorted(recovered_names)}", flush=True)
    print("=" * 78, flush=True)

    recovered_d_or_h = recovered_names & {"Kepler-90d", "Kepler-90h"}
    pass_gate = bool(recovered_d_or_h) and wall_total < 1800.0
    verdict = {
        "verdict_text": (
            f"PASS: detrended real curve recovered {sorted(recovered_d_or_h)} in "
            f"{wall_total:.1f}s total (3 iters)"
            if pass_gate
            else f"FAIL: recovered_d_or_h={sorted(recovered_d_or_h)}  "
                 f"total_wall={wall_total:.1f}s"
        ),
        "total_wall_s": round(wall_total, 2),
        "n_iters": n_iters,
        "rotation_d": rotation,
        "recovered_planets": sorted(recovered_names),
        "n_recovered": len(recovered_names),
        "recovered_d_or_h": sorted(recovered_d_or_h),
    }

    out = {
        "experiment": "j7b_real_curve_measure_detrended — J3 fix on real Kepler-90 stitch WITH detrend",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cache_dir": _TEMP_CACHE,
        "curve": {
            "t_baseline_d": round(T_baseline, 4),
            "n_cadences": n_cadences,
            "load_s": round(load_s, 2),
        },
        "upstream": {
            "rotation_d": round(rotation, 4),
            "rotation_s": round(rot_s, 2),
            "detrend_s": round(detrend_s, 2),
            "flux_raw_std": f_raw_std,
            "flux_detrended_median": f_med,
            "flux_detrended_std": f_std,
        },
        "expected": {
            "frequency_factor": min(500.0, max(1.0, T_baseline ** 2 / 4500.0)),
            "p_max_d": T_baseline / 2.0,
        },
        "iterations": iter_rows,
        "accepted": accepted,
        "recovery": recovery,
        "verdict": verdict,
        "round1_baseline_wall_s": 161.3,
    }
    out_path = _SCRIPT_DIR / "j7b_real_curve_measure_detrended_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[J7b] wrote {out_path}", flush=True)
    print(f"[J7b] VERDICT: {verdict['verdict_text']}", flush=True)
    return 0 if pass_gate else 1


if __name__ == "__main__":
    sys.exit(main())
