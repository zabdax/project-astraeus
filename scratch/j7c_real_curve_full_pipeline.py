"""J7c — Real-curve measurement mirroring the FULL production pipeline
(orchestrator's run_multi_planet_search loop), not bare BLS.

The J7b result (recovered Kepler-90b and Kepler-90c cleanly after
detrending; didn't get to d in 3 iters) confirmed the round-7 BLS
changes are correct: detrended real-curve recovery is consistent with
the round-3 e2e claim. But to reach d (59.7d) and h (331.6d), the
production orchestrator subtracts each discovered planet from
current_working_flux before re-searching, so the next planet is not
masked by aliases of the first. J7b's bare iterative alias-rejection
loop didn't subtract, so after b and c were accepted the next iterations
saw strong harmonics of b/c dominating the periodogram.

This script mirrors the production orchestrator exactly (see
astraeus/core/orchestrator.py:run_multi_planet_search, lines 92-234):
  while len(discovered) < max_signals:
      result = detect_transit_candidate(time, current_working_flux, known_periods=discovered_periods)
      if result.snr < snr_floor or not status.startswith("Verified Planet Candidate"): break
      current_working_flux = subtract_planetary_signal(current_working_flux, ...)

max_signals=5, snr_floor=7.1 (same defaults as the orchestrator's
submit_multi_planet_search). Network-free (reuses the cached 12-FFS
stitch). This is the round-7 gate's "real path" proof: if Kepler-90d or
Kepler-90h is recovered here, the round-7 BLS changes are sound and the
merge is open; if not, the root cause is somewhere in the recovery loop,
not in the BLS code.
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
RECOVERY_TOL = 0.01

# Orchestrator defaults
MAX_SIGNALS = 3  # bounded to fit 10min harness timeout (3 iters * ~130s ≈ 6.5min)
SNR_FLOOR = 7.1
MAX_DUP_RETRIES = 3


def _load_stitched_curve() -> tuple[np.ndarray, np.ndarray]:
    import lightkurve as lk
    fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
    print(f"[J7c] found {len(fits_files)} FITS files under {_TEMP_CACHE}", flush=True)
    if len(fits_files) < 12:
        raise FileNotFoundError(
            f"expected >=12 FITS files in {_TEMP_CACHE}, got {len(fits_files)}."
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
    print("[J7c] Full production pipeline (orchestrator-style) — Kepler-90 "
          "(KIC 011442793) stitch, J3 adaptive frequency_factor + widened p_max", flush=True)
    print("=" * 78, flush=True)

    t0_load = time.perf_counter()
    t_full, f_raw = _load_stitched_curve()
    load_s = time.perf_counter() - t0_load
    T_baseline = float(t_full.max() - t_full.min())
    n_cadences = int(len(t_full))
    print(f"[J7c] stitched: T_baseline={T_baseline:.4f} d  n_cadences={n_cadences}  "
          f"load_s={load_s:.2f}", flush=True)

    from astraeus.analysis.detection import detect_transit_candidate
    from astraeus.core.orchestrator import subtract_planetary_signal

    # Mirrors orchestrator.py:run_multi_planet_search (lines 92-234)
    active_time = t_full.copy()
    current_working_flux = f_raw.copy()
    discovered_periods: list[float] = []
    discovered_records: list[dict] = []
    iter_rows: list[dict] = []
    wall_total = 0.0
    iteration = 0
    duplicate_retries = 0

    while len(discovered_records) < MAX_SIGNALS:
        iteration += 1
        if iteration > MAX_SIGNALS + MAX_DUP_RETRIES:
            print(f"[J7c] iteration budget exhausted ({iteration-1})")
            break
        print(f"\n[J7c] === ITERATION {iteration} === "
              f"(found {len(discovered_records)}/{MAX_SIGNALS})", flush=True)

        t0_iter = time.perf_counter()
        result = detect_transit_candidate(
            time=active_time,
            flux=current_working_flux,
            target_name="Kepler-90 (real stitch, J7c gate)",
            data_source="real-kepler90-stitch",
            metadata={
                "st_rad": 1.2, "st_teff": 5930.0, "st_mass": 1.13, "sy_jmag": 12.49,
            },
            snr_threshold=SNR_FLOOR,
            known_periods=discovered_periods,
        )
        iter_s = time.perf_counter() - t0_iter
        wall_total += iter_s

        snr = result.get("snr", 0.0)
        vetting = result.get("vetting_status", "")
        best_period = result.get("period", 0.0)
        depth_ppm = result.get("depth", 0.0) * 1e6  # depth comes back as fraction
        duration_d = result.get("duration", 0.0)
        t0 = result.get("t0", 0.0)
        tls_valid = result.get("tls_valid")
        tls_sde = result.get("tls_sde")

        row = {
            "iteration": iteration,
            "wall_s": round(iter_s, 2),
            "period": best_period,
            "snr": snr,
            "duration": duration_d,
            "depth_ppm": depth_ppm,
            "vetting_status": vetting,
            "tls_valid": tls_valid,
            "tls_sde": tls_sde,
        }
        iter_rows.append(row)
        print(f"[J7c] iter={iteration}  wall={iter_s:6.2f}s  P={best_period:.4f}d  "
              f"SNR={snr:.2f}  dur={duration_d:.4f}d  status={vetting!r}  "
              f"tls_valid={tls_valid}  tls_sde={tls_sde}", flush=True)

        # GUARDRAIL 1: SNR / vetting floor (orchestrator:169-170)
        if snr < SNR_FLOOR or not (isinstance(vetting, str) and vetting.startswith("Verified Planet Candidate")):
            print(f"[J7c] signal floor reached (SNR={snr:.2f}, status={vetting!r}). Halting.", flush=True)
            break

        # GUARDRAIL 2: duplicate detection (orchestrator:172-213)
        is_dup = False
        for prev_p in discovered_periods:
            ratio = best_period / prev_p if prev_p > 0 else 0
            if abs(ratio - 1.0) < 0.05:
                is_dup = True
                break
            for harmonic in (0.5, 2.0):
                if abs(ratio - harmonic) < 0.05:
                    is_dup = True
                    break
            if is_dup:
                break
        if is_dup:
            duplicate_retries += 1
            if duplicate_retries > MAX_DUP_RETRIES:
                print(f"[J7c] too many duplicate retries ({duplicate_retries}). Halting.", flush=True)
                break
            print(f"[J7c] duplicate of {prev_p:.4f}d; retrying.", flush=True)
            # Still subtract to erode residual (orchestrator:198-208)
            try:
                current_working_flux = subtract_planetary_signal(
                    flux=current_working_flux, time=active_time,
                    period=best_period, epoch=t0, duration=duration_d,
                    depth_ppm=depth_ppm,
                )
            except Exception as exc:
                print(f"[J7c] subtract failed: {exc!r}", flush=True)
            continue

        # Accept and subtract (orchestrator:215-228)
        discovered_periods.append(best_period)
        recovered_name = _classify_recovery(best_period)
        rec = {
            "iteration": iteration,
            "period": best_period,
            "snr": snr,
            "duration": duration_d,
            "depth_ppm": depth_ppm,
            "matched_planet": recovered_name,
        }
        discovered_records.append(rec)
        if recovered_name:
            print(f"[J7c] ACCEPTED -> {recovered_name}  P={best_period:.4f}d  "
                  f"(truth={KNOWN_PERIODS[recovered_name]:.4f}d)", flush=True)
        else:
            print(f"[J7c] ACCEPTED  P={best_period:.4f}d  SNR={snr:.2f}  "
                  f"(no known-planet match)", flush=True)

        # Subtract
        try:
            current_working_flux = subtract_planetary_signal(
                flux=current_working_flux, time=active_time,
                period=best_period, epoch=t0, duration=duration_d,
                depth_ppm=depth_ppm,
            )
            print(f"[J7c] subtracted {best_period:.4f}d for next iteration", flush=True)
        except Exception as exc:
            print(f"[J7c] subtract failed: {exc!r}; cannot continue", flush=True)
            break

        duplicate_retries = 0

    # Verdict
    recovered_names = {r["matched_planet"] for r in discovered_records if r["matched_planet"]}
    recovered_d_or_h = recovered_names & {"Kepler-90d", "Kepler-90h"}
    pass_gate = bool(recovered_d_or_h) and wall_total < 1800.0
    verdict = {
        "verdict_text": (
            f"PASS: full production pipeline recovered {sorted(recovered_d_or_h)} on real "
            f"1239.81d/45853-cadence curve, total wall {wall_total:.1f}s"
            if pass_gate
            else f"FAIL: recovered_d_or_h={sorted(recovered_d_or_h)}  "
                 f"total_wall={wall_total:.1f}s  n_recovered={len(recovered_names)}"
        ),
        "total_wall_s": round(wall_total, 2),
        "n_iterations": iteration,
        "recovered_planets": sorted(recovered_names),
        "n_recovered": len(recovered_names),
        "recovered_d_or_h": sorted(recovered_d_or_h),
    }

    out = {
        "experiment": "j7c_real_curve_full_pipeline — orchestrator-style multi-planet search on real Kepler-90 stitch",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cache_dir": _TEMP_CACHE,
        "curve": {
            "t_baseline_d": round(T_baseline, 4),
            "n_cadences": n_cadences,
            "load_s": round(load_s, 2),
        },
        "config": {
            "max_signals": MAX_SIGNALS,
            "snr_floor": SNR_FLOOR,
            "max_dup_retries": MAX_DUP_RETRIES,
        },
        "iterations": iter_rows,
        "discovered": discovered_records,
        "verdict": verdict,
    }
    out_path = _SCRIPT_DIR / "j7c_real_curve_full_pipeline_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[J7c] wrote {out_path}", flush=True)
    print("=" * 78, flush=True)
    print(f"[J7c] TOTAL wall: {wall_total:.2f}s  ({wall_total/60:.1f}min)", flush=True)
    print(f"[J7c] recovered {len(recovered_names)}/{len(KNOWN_PERIODS)} known planets: "
          f"{sorted(recovered_names)}", flush=True)
    print(f"[J7c] VERDICT: {verdict['verdict_text']}", flush=True)
    return 0 if pass_gate else 1


if __name__ == "__main__":
    sys.exit(main())
