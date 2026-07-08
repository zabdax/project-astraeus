"""J7 — Real-curve measurement of the J3 adaptive frequency_factor + widened
p_max on the ACTUAL 1240d / 45,853-cadence Kepler-90 stitch (KIC 11442793).

Round-7 review gate: the four calibration curves (10d/2000, 50d/1500,
200d/9795, 1500d/3000 cadences) used to fit the frequency_factor formula
are all projection stand-ins, not measurements of the real target's
combination of (T_baseline, n_cadences) = (~1240d, 45853). Round 1 H5
measured 161.3s on this exact curve with the OLD code (p_max=450d cap,
default astropy grid); round 7 needs a fresh measurement of the NEW code.

This script:
  1. Reuses the cached MAST FITS files at $TEMP/astraeus_h1_kepler90_measurement/
     (downloaded by scratch/h1_kepler90_measurement.py on 2026-07-06, 12 quarters
     for KIC 011442793 = Kepler-90). No re-download, network-free.
  2. Stitches and remove_nans() to get the same 1240d / 45,853-cadence curve
     the round-1 I0 and I5 measurements used.
  3. Iterates BLSSearchEngine.search() 3 times with the iterative
     known_periods alias-rejection loop the orchestrator actually runs
     (the same pattern detect_transit_candidate uses on successive
     calls), measuring per-iteration wall-time and the final list of
     accepted periods.
  4. Checks each accepted period against the known Kepler-90 planets
     (b..i) with a 1% tolerance and reports which were recovered.

Output: scratch/j7_real_curve_measure_result.json with timing + recovery
verdict, plus a per-iteration breakdown.

Run: python scratch/j7_real_curve_measure.py
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

# Background-launched python may not have the project root on sys.path.
# Add it explicitly (same pattern as h1_kepler90_measurement.py and
# i5_bls_kepler90_baseline.py).
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Use the exact cache path the H1 / I5 scripts used. h1_kepler90_measurement
# set this to %TEMP%/astraeus_h1_kepler90_measurement (Windows) which Git
# Bash maps to /tmp/astraeus_h1_kepler90_measurement on this system.
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
    """Read cached FITS files and stitch with lightkurve.

    Returns (t, f) as float64 arrays, NaN-stripped.
    Raises if <12 FITS files are present (i.e. the user needs to run
    h1_kepler90_measurement.py first).
    """
    import lightkurve as lk
    fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
    print(f"[J7] found {len(fits_files)} FITS files under {_TEMP_CACHE}", flush=True)
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
    """Return the Kepler-90 planet name if period matches within 1%, else None."""
    for name, true_p in KNOWN_PERIODS.items():
        if abs(period - true_p) / true_p <= RECOVERY_TOL:
            return name
    return None


def main() -> int:
    print("=" * 78, flush=True)
    print("[J7] Real-curve measurement — Kepler-90 (KIC 011442793) stitch, "
          "J3 adaptive frequency_factor + widened p_max", flush=True)
    print("=" * 78, flush=True)

    t0_load = time.perf_counter()
    t, f = _load_stitched_curve()
    load_s = time.perf_counter() - t0_load
    T_baseline = float(t.max() - t.min())
    n_cadences = int(len(t))
    print(f"[J7] stitched: T_baseline={T_baseline:.4f} d  n_cadences={n_cadences}  "
          f"load_s={load_s:.2f}", flush=True)
    print(f"[J7] expected adaptive frequency_factor = "
          f"max(1.0, T_baseline^2/4500) = max(1.0, {T_baseline**2/4500.0:.1f}) "
          f"capped at 500", flush=True)
    print(f"[J7] expected p_max = T_baseline/2 = {T_baseline/2.0:.1f} d "
          f"(was capped at 450 in round 1; new code uses T/2)", flush=True)

    # Lazy import so the load error surfaces before astropy import cost
    from astraeus.analysis.bls_search import BLSSearchEngine

    # Run the iterative first-accept loop with known_periods alias rejection.
    # This mirrors what detect_transit_candidate does on successive calls
    # when the orchestrator searches for multi-planet systems.
    n_iters = 3  # cap=3: enough to chase Kepler-90d (59d), then h (331d)
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
                f"[J7] iter={it}  wall={iter_s:6.2f}s  P={r.get('period'):.4f}d  "
                f"SNR={r.get('snr'):.2f}  dur={r.get('duration'):.4f}d  "
                f"conf={r.get('confidence_score'):.3f}",
                flush=True,
            )
            if r.get("period") is not None and r.get("snr", 0.0) > 0.0:
                accepted.append({"period": float(r["period"]), "snr": float(r["snr"])})
        except Exception as exc:
            iter_s = time.perf_counter() - t0_iter
            wall_total += iter_s
            iter_rows.append({
                "iteration": it,
                "wall_s": round(iter_s, 2),
                "error": repr(exc),
            })
            print(f"[J7] iter={it}  ERROR after {iter_s:.2f}s: {exc!r}", flush=True)
            break

    # Recovery verdict
    recovery: list[dict] = []
    recovered_names: set[str] = set()
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
            print(f"[J7] RECOVERED  {name}  P={a['period']:.4f}d  (truth={KNOWN_PERIODS[name]:.4f}d)", flush=True)
        else:
            print(f"[J7] candidate P={a['period']:.4f}d  snr={a['snr']:.2f}  (no known-planet match)", flush=True)

    # Round-1 baseline for comparison: 161.3s per call on this exact curve
    # with the OLD code (p_max=450 cap, default astropy grid).
    print("=" * 78, flush=True)
    print(f"[J7] TOTAL wall (sum of {n_iters} iterations): {wall_total:.2f}s  "
          f"({wall_total/60:.1f}min)", flush=True)
    print(f"[J7] round-1 reference: 161.3s per call (OLD code: p_max=450, default grid)", flush=True)
    print(f"[J7] recovered {len(recovered_names)}/{len(KNOWN_PERIODS)} known planets: "
          f"{sorted(recovered_names)}", flush=True)
    print("=" * 78, flush=True)

    # Verdict text
    recovered_d_or_h = recovered_names & {"Kepler-90d", "Kepler-90h"}
    verdict = {
        "verdict_text": (
            f"PASS: real 1240d/45853-cadence curve ran in {wall_total:.1f}s total "
            f"({n_iters} iters), recovered {sorted(recovered_names)}"
            if (recovered_d_or_h and wall_total < 1800.0)
            else f"FAIL: recovered_d_or_h={sorted(recovered_d_or_h)}  total_wall={wall_total:.1f}s"
        ),
        "total_wall_s": round(wall_total, 2),
        "n_iters": n_iters,
        "recovered_planets": sorted(recovered_names),
        "n_recovered": len(recovered_names),
        "recovered_d_or_h": sorted(recovered_d_or_h),
    }

    out = {
        "experiment": "j7_real_curve_measure — J3 adaptive frequency_factor + widened p_max on real Kepler-90 stitch",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cache_dir": _TEMP_CACHE,
        "curve": {
            "t_baseline_d": round(T_baseline, 4),
            "n_cadences": n_cadences,
            "load_s": round(load_s, 2),
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
    out_path = Path(__file__).resolve().parent / "j7_real_curve_measure_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[J7] wrote {out_path}", flush=True)
    print(f"[J7] VERDICT: {verdict['verdict_text']}", flush=True)
    return 0 if (recovered_d_or_h and wall_total < 1800.0) else 1


if __name__ == "__main__":
    sys.exit(main())
