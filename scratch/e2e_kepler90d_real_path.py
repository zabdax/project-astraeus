"""
e2e_kepler90d_real_path.py
==========================

Closes the loop on the J2c reviewer's concern: confirm that the full
production code path — submit_multi_planet_search -> daemon worker ->
detect_transit_candidate -> BLSSearchEngine -> tls.transitleastsquares(...).power(...)
-> result back through the queue — actually emits a real candidate as
'Verified Planet Candidate' with a real TLS SDE on a known real
short-period planet. NOT the isolated TLS control arm; the real path.

The reviewer flagged that the silent-AssertionError bug has been folding
environment failures into tls_valid=False since 2026-06-09, and that
prior "recovery" numbers were produced by direct calls to the alias-
checker that bypassed the orchestrator. This script is the proof that
the full pipeline, with the J2c fix (use_threads=1 in detection.py
+ distinct except-Exception branches) in place, is once again capable
of accepting a real planet.

Target: Kepler-90d
  P = 59.73667 d
  depth ~ 602 ppm
  duration ~ 4.2 h
  short period -> fast BLS, narrow TLS window, finishes well under
  10 minutes even on a 1500d / 30k-cadence synthetic curve.

Synthetic input keeps the test deterministic and network-free.
"""
from __future__ import annotations

import json
import multiprocessing
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# --- Kepler-90d physical parameters ----------------------------------------
KEPLER90D_PERIOD_D = 59.73667
KEPLER90D_DEPTH_PPM = 602.0
KEPLER90D_DURATION_D = 4.2 / 24.0
KEPLER90D_T0_BJD = 130.0  # arbitrary; just gives a clear phase

# --- Curve parameters ------------------------------------------------------
# Diagnostic-grade small curve. We are testing whether the gate is
# functional, not the full per-iteration perf. 200d / 2000 cadences /
# ~3 transits is enough for BLS to recover P=59.74d on a clean signal
# and for TLS to validate it inside a few-minute budget.
BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0  # Kepler long cadence
N_CADENCES = int(BASELINE_D / CADENCE_D)  # ~ 9,795
NOISE_PPM = 100.0  # per-cadence


def make_kepler90d_curve() -> tuple[np.ndarray, np.ndarray]:
    """Reproducible synthetic curve with a single Kepler-90d-like transit
    signal injected. Trapezoidal model (linear ingress/egress) — same
    shape the orchestrator's subtract_planetary_signal uses as a fallback,
    so this exercises the realistic transit geometry. No second signal,
    no stellar variability, no other planets. We are testing the gate,
    not the multi-planet search."""
    rng = np.random.default_rng(seed=20260706)
    t = np.arange(N_CADENCES) * CADENCE_D
    y = 1.0 + (NOISE_PPM * 1e-6) * rng.standard_normal(N_CADENCES)

    # Trapezoidal transit model
    period = KEPLER90D_PERIOD_D
    t0 = KEPLER90D_T0_BJD
    duration = KEPLER90D_DURATION_D
    depth = KEPLER90D_DEPTH_PPM * 1e-6

    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    abs_phase = np.abs(phase)
    ramp_duration = 0.1 * duration  # 10% ingress + 10% egress
    flat_duration = duration - 2 * ramp_duration

    in_flat = abs_phase <= (flat_duration / 2.0)
    in_ramp = (abs_phase > (flat_duration / 2.0)) & (abs_phase <= (duration / 2.0))
    ramp_x = abs_phase[in_ramp] - (flat_duration / 2.0)
    y[in_flat] -= depth
    y[in_ramp] -= depth * (1.0 - (ramp_x / ramp_duration))

    return t, y


def main() -> None:
    # Force unbuffered stdout in the parent so the polling loop's prints
    # surface in real time. The daemon worker (spawn-launched child) will
    # inherit PYTHONUNBUFFERED from the env if set; we set it here too.
    import os
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    out_dir = PROJECT_ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_path = out_dir / f"e2e_kepler90d_real_path_{stamp}.json"

    # Import AFTER path is set so that the daemon worker (spawn-launched
    # child) gets a fresh, clean sys.path.
    from astraeus.core.orchestrator import (
        submit_multi_planet_search,
        get_job_status,
        cancel_job,
        JobState,
    )

    print(f"[e2e] target: Kepler-90d  P={KEPLER90D_PERIOD_D}d  depth={KEPLER90D_DEPTH_PPM}ppm")
    print(f"[e2e] curve: {BASELINE_D}d baseline, {N_CADENCES} cadences, {CADENCE_D*24*60:.1f}-min cadence")
    print(f"[e2e] noise: {NOISE_PPM} ppm per cadence")
    print(f"[e2e] CPU count: {multiprocessing.cpu_count()}")
    sys.stdout.flush()

    t0_build = time.perf_counter()
    t, y = make_kepler90d_curve()
    build_s = time.perf_counter() - t0_build
    print(f"[e2e] built curve in {build_s:.2f}s")
    sys.stdout.flush()

    raw = {
        "time": t.tolist(),
        "flux": y.tolist(),
        "target_name": "Kepler-90 (synthetic, d-only)",
        "data_source": "synthetic-e2e",
        "metadata": {
            "st_rad": 1.2,      # Kepler-90 stellar radius
            "st_teff": 5930.0,  # Kepler-90 Teff
            "st_mass": 1.13,    # Kepler-90 mass
            "sy_jmag": 12.49,
        },
    }

    t0_submit = time.perf_counter()
    job_id = submit_multi_planet_search(raw, max_signals=1, snr_floor=5.0)
    print(f"[e2e] submitted job_id={job_id}")
    sys.stdout.flush()

    HARD_TIMEOUT_S = 600.0
    POLL_S = 2.0
    deadline = time.perf_counter() + HARD_TIMEOUT_S
    terminal_seen = False
    snapshots: list[dict] = []
    last_partial_write = 0.0
    while time.perf_counter() < deadline:
        status = get_job_status(job_id)
        snapshots.append({
            "t_s": round(time.perf_counter() - t0_submit, 2),
            "status": status.get("status"),
            "iteration": status.get("iteration", 0),
            "n_candidates": len(status.get("candidates", [])),
        })
        # Write a partial report every 30s so a timeout still leaves evidence.
        if time.perf_counter() - last_partial_write > 30.0:
            partial = {
                "experiment": "e2e_kepler90d_real_path — partial, in progress",
                "job_id": job_id,
                "elapsed_s": round(time.perf_counter() - t0_submit, 2),
                "snapshots": snapshots,
                "current_status": status,
            }
            out_path.write_text(json.dumps(partial, indent=2, default=str))
            last_partial_write = time.perf_counter()
        if status.get("status") in (JobState.DONE, JobState.FAILED, JobState.CANCELLED):
            terminal_seen = True
            final_status = status
            break
        time.sleep(POLL_S)

    if not terminal_seen:
        print(f"[e2e] HARD TIMEOUT after {HARD_TIMEOUT_S}s — cancelling")
        cancel_job(job_id)
        final_status = get_job_status(job_id)

    wall = time.perf_counter() - t0_submit
    print(f"[e2e] wall={wall:.2f}s  final_status={final_status.get('status')}")
    sys.stdout.flush()

    # Verdict
    candidates = final_status.get("candidates", [])
    error = final_status.get("error")
    verdict: dict = {
        "final_status": final_status.get("status"),
        "wall_s": round(wall, 2),
        "n_candidates": len(candidates),
        "error": error,
    }
    verified_candidates: list[dict] = []
    for c in candidates:
        is_verified = (
            isinstance(c.get("vetting_status"), str)
            and c["vetting_status"].startswith("Verified Planet Candidate")
        )
        tls_valid = c.get("tls_valid")
        tls_sde = c.get("tls_sde")
        tls_env_err = c.get("tls_environment_error")
        tls_sci_err = c.get("tls_scientific_error")
        verified_candidates.append({
            "period": c.get("period"),
            "vetting_status": c.get("vetting_status"),
            "is_verified": is_verified,
            "snr": c.get("snr"),
            "tls_valid": tls_valid,
            "tls_sde": tls_sde,
            "tls_period": c.get("tls_period"),
            "tls_fap": c.get("tls_fap"),
            "tls_environment_error": tls_env_err,
            "tls_scientific_error": tls_sci_err,
        })
        print(
            f"[e2e] candidate: P={c.get('period'):.4f}d  status={c.get('vetting_status')!r}  "
            f"snr={c.get('snr'):.2f}  tls_valid={tls_valid}  tls_sde={tls_sde}  "
            f"tls_period={c.get('tls_period')}  env_err={tls_env_err!r}  sci_err={tls_sci_err!r}"
        )
    verdict["candidates"] = verified_candidates
    verdict["any_verified_with_real_tls"] = any(
        v["is_verified"] and v["tls_valid"] is True
        and (v["tls_sde"] is not None and v["tls_sde"] >= 5.0)
        and v["tls_environment_error"] is None
        for v in verified_candidates
    )

    if verdict["final_status"] == JobState.DONE and verdict["any_verified_with_real_tls"]:
        verdict["verdict_text"] = (
            "PASS: the full production code path (orchestrator -> daemon worker -> "
            "BLSSearchEngine -> TLS with use_threads=1) emitted a real candidate as "
            "'Verified Planet Candidate' with a real TLS SDE. The J2c silent-AssertionError "
            "fix is end-to-end functional."
        )
    elif verdict["final_status"] == JobState.FAILED:
        verdict["verdict_text"] = (
            f"FAIL: orchestrator job FAILED with error={error!r}. The full path is broken; "
            "the J2c fix did not unblock the pipeline."
        )
    else:
        verdict["verdict_text"] = (
            f"FAIL: no candidate was emitted as 'Verified' with a real TLS SDE. "
            f"final_status={verdict['final_status']}, n_candidates={len(candidates)}, "
            f"snapshots_tail={snapshots[-3:]}. The pipeline is not yet accepting real "
            f"planets end-to-end."
        )
    print(f"[e2e] VERDICT: {verdict['verdict_text']}")

    report = {
        "experiment": "e2e_kepler90d_real_path — full production call stack on a synthetic Kepler-90d-like transit, J2c fix in place",
        "target_physical": {
            "name": "Kepler-90d",
            "period_d": KEPLER90D_PERIOD_D,
            "depth_ppm": KEPLER90D_DEPTH_PPM,
            "duration_d": KEPLER90D_DURATION_D,
            "t0_bjd": KEPLER90D_T0_BJD,
        },
        "curve": {
            "baseline_d": BASELINE_D,
            "n_cadences": N_CADENCES,
            "cadence_d": CADENCE_D,
            "noise_ppm": NOISE_PPM,
            "build_s": round(build_s, 2),
        },
        "job": {
            "job_id": job_id,
            "max_signals": 1,
            "snr_floor": 5.0,
            "wall_s": round(wall, 2),
            "hard_timeout_s": HARD_TIMEOUT_S,
        },
        "verdict": verdict,
        "snapshots": snapshots,
    }
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[e2e] wrote {out_path}")


if __name__ == "__main__":
    main()
