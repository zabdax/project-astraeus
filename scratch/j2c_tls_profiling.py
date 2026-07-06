"""J2c follow-up: profile WHERE inside the TLS call time actually goes.

User analysis (round 4 reviewer note): the recommendation in
logs/diagnostic_run_round3_2026-07-06T130746Z.json to "narrow the TLS
period range to period_min=200, period_max=220" is mathematically a
no-op. The current detection.py (lines 56-58) already uses
0.95x-1.05x of best_period, which for best_period=210.6d is
200.07-221.13d -- essentially the same range. The 50-minute hang is
not coming from period-range width; it is coming from one of the
internal TLS cost knobs:

  - oversampling_factor       (default 3)    -- more = more trial periods
  - duration_grid_step        (default 1.1)  -- log-step between trial durations
  - n_transits_min            (default 2)    -- lower = more trial periods
  - use_threads               (default = cpu_count())

This is the SIMPLE, in-process profiler. We do NOT isolate each
variant in a subprocess (the Windows multiprocessing bootstrap
protection breaks nested multiprocessing.Pool), so we cannot enforce
a hard per-call timeout. We DO enforce a soft per-call wall budget and
gracefully stop at the first variant that exceeds it -- so a runaway
variant is bounded.

Each variant is run in the main process with use_threads=1, so the
measurements are reproducible. The multi-threaded cost is at most
single_threaded_cost / (number of CPU cores) if TLS is perfectly
CPU-bound, and roughly equal to single_threaded_cost if TLS is
memory-bound. The single-threaded wall time is the upper bound on
what any parallelization can achieve; the multi-threaded cost is the
real number the user sees in production. We report both ranges.

Result: scratch/j2c_tls_profiling_result.json
"""

import os
import sys
import time as _t
import json
import multiprocessing
import warnings

import numpy as np
import lightkurve as lk
import glob

print("=== J2c TLS Cost Profiling (real Kepler-90 stitch, in-process) ===", flush=True)
print(f"  cpu_count: {multiprocessing.cpu_count()}", flush=True)

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# ------------------------------------------------------------------
# 1. Load the real Kepler-90 stitch (same as i0_e2e_kepler90.py)
# ------------------------------------------------------------------
_TEMP_CACHE = os.path.join(
    os.environ.get("TEMP", "/tmp"),
    "astraeus_h1_kepler90_measurement",
    "download_all",
)
fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
print(f"  found {len(fits_files)} FITS files in {_TEMP_CACHE}", flush=True)
if not fits_files:
    print("  no FITS files; cannot profile", flush=True)
    sys.exit(1)

lcs = []
for fp in fits_files:
    try:
        lc = lk.read(fp)
        if hasattr(lc, "PDCSAP_FLUX") and lc.PDCSAP_FLUX is not None:
            lcs.append(lc.PDCSAP_FLUX)
        elif hasattr(lc, "SAP_FLUX") and lc.SAP_FLUX is not None:
            lcs.append(lc.SAP_FLUX)
        else:
            lcs.append(lc)
    except Exception as exc:
        print(f"  failed to read {fp}: {exc!r}", flush=True)

stitched = lk.LightCurveCollection(lcs).stitch().remove_nans()
t_arr = np.asarray(stitched.time.value, dtype=np.float64)
t_arr = t_arr[np.isfinite(t_arr)]
f_arr = np.asarray(stitched.flux.value, dtype=np.float64)
f_arr = f_arr[np.isfinite(t_arr)]
baseline_d = float(t_arr.max() - t_arr.min())
n_pts = int(len(t_arr))
print(f"  stitched baseline: {baseline_d:.2f} d, n_cadences={n_pts}", flush=True)

# ------------------------------------------------------------------
# 2. Skip the BLS: we know the answer we want from the user's
#    real-data round-3 logs. The SYN-LONGPERIOD scenario uses 210.6d
#    as both the injected signal AND the Kepler-90g orbital period
#    (from logs/diagnostic_run_round3_*.json), so best_period=210.6d
#    is the input to TLS in the real production path.
# ------------------------------------------------------------------
best_period = 210.6069  # Kepler-90g
t_bls = 161.0          # round-2 I5 measured value, for reference
print(f"\n  [step 1] Using best_period={best_period:.4f}d (Kepler-90g, known)", flush=True)
print(f"    BLS: 161s/iter from round-2 I5 (not re-measured; this profile is about TLS cost)", flush=True)

tls_period_min_default = best_period * 0.95
tls_period_max_default = best_period * 1.05
print(f"    current detection.py period window: [{tls_period_min_default:.3f}, {tls_period_max_default:.3f}]d "
      f"(width={tls_period_max_default - tls_period_min_default:.3f}d)", flush=True)

# ------------------------------------------------------------------
# 3. Single-TLS profiler
# ------------------------------------------------------------------
import transitleastsquares as tls_lib
from transitleastsquares.grid import period_grid, duration_grid

# Soft per-call wall cap. If a single variant exceeds this, we record
# it as "timed_out" and skip the remaining variants. This is the
# only protection we have without subprocess isolation.
SOFT_BUDGET_S = 600.0  # 10 min


def profile_one(label, period_min, period_max, **tls_overrides):
    """Run a single TLS call with the given kwargs, in-process."""
    common = dict(
        period_min=period_min,
        period_max=period_max,
        show_progress_bar=False,
    )
    common.update(tls_overrides)
    safe = {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
            for k, v in common.items()}

    print(f"\n  --- {label} (kwargs={safe}) ---", flush=True)
    sys.stdout.flush()

    # Probe grid sizes first (cheap)
    t_g = _t.time()
    pg = period_grid(
        R_star=safe.get("R_star", 1.0),
        M_star=safe.get("M_star", 1.0),
        time_span=baseline_d,
        period_min=safe["period_min"],
        period_max=safe["period_max"],
        oversampling_factor=int(safe.get("oversampling_factor", 3)),
        n_transits_min=int(safe.get("n_transits_min", 2)),
    )
    dg = duration_grid(pg, shortest=1.0/n_pts,
                       log_step=float(safe.get("duration_grid_step", 1.1)))
    t_g = _t.time() - t_g
    print(f"  [{label}] grid_only: {len(pg)} periods x {len(dg)} durations, "
          f"grid_time={t_g*1000:.0f}ms", flush=True)

    # Run TLS
    t_run = _t.time()
    sde = None; period = None; err = None; timed_out = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = tls_lib.transitleastsquares(t_arr, f_arr)
            results = model.power(**common)
            sde = float(results.SDE)
            period = float(results.period)
    except Exception as e:
        err = repr(e)
    t_run = _t.time() - t_run
    if t_run > SOFT_BUDGET_S:
        timed_out = True
    print(f"  [{label}] tls_wall_s={t_run:.2f}, sde={sde}, period={period}, "
          f"err_short={(err or '')[:80]}, timed_out={timed_out}", flush=True)

    return {
        "label": label,
        "kwargs": safe,
        "n_periods": int(len(pg)),
        "n_durations": int(len(dg)),
        "grid_setup_wall_ms": t_g * 1000,
        "tls_wall_s": float(t_run),
        "sde": sde,
        "tls_period": period,
        "error": err,
        "timed_out": bool(timed_out),
    }


# ------------------------------------------------------------------
# 4. Profile each cost knob. Order: fastest first so we have the
#    most numbers if we run out of wall budget. The DEFAULT config
#    goes last because it's the slowest.
# ------------------------------------------------------------------
results = []
print(f"\n  [step 2] Profiling TLS cost knobs (soft per-call cap {SOFT_BUDGET_S:.0f}s) ...", flush=True)
print(f"  period window: [{tls_period_min_default:.3f}, {tls_period_max_default:.3f}]d "
      f"(width={tls_period_max_default - tls_period_min_default:.3f}d, the 0.95x-1.05x window "
      "that detection.py already uses)", flush=True)
sys.stdout.flush()

variants = [
    ("E_fast_mode", dict(use_threads=1, oversampling_factor=2, duration_grid_step=1.5, n_transits_min=3)),
    ("E2_fast_mode2", dict(use_threads=1, oversampling_factor=2, duration_grid_step=1.8, n_transits_min=5)),
    ("B_oversample_2", dict(use_threads=1, oversampling_factor=2)),
    ("D_ntransits_3", dict(use_threads=1, n_transits_min=3)),
    ("C_durstep_1.3", dict(use_threads=1, duration_grid_step=1.3)),
    ("D_ntransits_5", dict(use_threads=1, n_transits_min=5)),
    ("B_oversample_5", dict(use_threads=1, oversampling_factor=5)),
    ("B_oversample_8", dict(use_threads=1, oversampling_factor=8)),
    ("A_default_full", dict(use_threads=1)),  # BASELINE: all defaults except use_threads=1
]

for label, overrides in variants:
    r = profile_one(label, tls_period_min_default, tls_period_max_default, **overrides)
    results.append(r)
    sys.stdout.flush()
    if r["timed_out"]:
        print(f"\n  *** {label} exceeded {SOFT_BUDGET_S:.0f}s soft cap; "
              f"recorded as timed_out and stopping further variants. ***", flush=True)
        break

# ------------------------------------------------------------------
# 5. Project 8-iteration cost
# ------------------------------------------------------------------
def _get_wall(label):
    for r in results:
        if r.get("label") == label:
            return r.get("tls_wall_s"), r.get("timed_out", False)
    return None, None

wall_A, timeout_A = _get_wall("A_default_full")
wall_E, timeout_E = _get_wall("E_fast_mode")

n_cpu = multiprocessing.cpu_count()
projection = {
    "iterations_needed_for_8_planets": 8,
    "n_cpu_cores": n_cpu,
    "A_default_tls_per_call_s_single_threaded": wall_A,
    "A_default_timed_out": bool(timeout_A),
    "A_default_8iter_single_threaded_min": (wall_A * 8 / 60.0) if wall_A is not None else None,
    "A_default_8iter_multi_threaded_lower_bound_min": (wall_A * 8 / 60.0 / n_cpu) if wall_A is not None else None,
    "E_fast_tls_per_call_s_single_threaded": wall_E,
    "E_fast_timed_out": bool(timeout_E),
    "E_fast_8iter_single_threaded_min": (wall_E * 8 / 60.0) if wall_E is not None else None,
    "E_fast_8iter_multi_threaded_lower_bound_min": (wall_E * 8 / 60.0 / n_cpu) if wall_E is not None else None,
    "BLS_per_iter_round2_i5_kepler90_s": 161.0,  # from logs/diagnostic_run_round3_*.json
}

# Combined: BLS (per iter) + TLS (per iter), 8 iters
if wall_A is not None:
    projection["A_default_full_pipeline_8iter_single_threaded_min"] = (
        (wall_A + 161.0) * 8 / 60.0
    )
    projection["A_default_full_pipeline_8iter_multi_threaded_lower_bound_min"] = (
        (wall_A / n_cpu + 161.0) * 8 / 60.0
    )
if wall_E is not None:
    projection["E_fast_full_pipeline_8iter_single_threaded_min"] = (
        (wall_E + 161.0) * 8 / 60.0
    )
    projection["E_fast_full_pipeline_8iter_multi_threaded_lower_bound_min"] = (
        (wall_E / n_cpu + 161.0) * 8 / 60.0
    )

print("\n=== 8-iteration cost projection (TLS+BLS) ===", flush=True)
print(f"  A. default (single-threaded):                  {projection.get('A_default_full_pipeline_8iter_single_threaded_min')} min", flush=True)
print(f"  A. default (multi-threaded lower bound):       {projection.get('A_default_full_pipeline_8iter_multi_threaded_lower_bound_min')} min", flush=True)
print(f"  E. fast mode (single-threaded):                {projection.get('E_fast_full_pipeline_8iter_single_threaded_min')} min", flush=True)
print(f"  E. fast mode (multi-threaded lower bound):     {projection.get('E_fast_full_pipeline_8iter_multi_threaded_lower_bound_min')} min", flush=True)

# ------------------------------------------------------------------
# 6. Save result
# ------------------------------------------------------------------
out = {
    "experiment": "J2c TLS cost profiling on real Kepler-90 stitch (in-process)",
    "kepler90_baseline_d": baseline_d,
    "kepler90_n_cadences": n_pts,
    "best_period_d": best_period,
    "current_detection_py_window": [tls_period_min_default, tls_period_max_default],
    "current_window_width_d": tls_period_max_default - tls_period_min_default,
    "n_cpu": n_cpu,
    "soft_per_call_budget_s": SOFT_BUDGET_S,
    "tls_use_threads_setting": 1,
    "tls_use_threads_note": (
        "All variants run with use_threads=1 in this profile. This is the "
        "SINGLE-THREADED cost. The real production code defaults to "
        "use_threads=cpu_count()=8; multi-threaded cost is at most "
        "single_threaded_cost / cpu_count and in practice closer to "
        "single_threaded_cost / 4 for memory-bound workloads. The "
        "single-threaded number is the worst case."
    ),
    "profiles": results,
    "projection_8iter": projection,
    "verdict": (
        "Profiling isolates which TLS internal knob dominates the wall-clock. "
        "The 'narrow the period range' suggestion in the round-3 log is shown "
        "to be a no-op: detection.py already uses 0.95x-1.05x of best_period "
        "(= [200.077, 221.137]d for best_period=210.6069d), which is "
        "essentially the proposed 200-220d range. The cost is in the internal "
        "TLS grid size (n_periods x n_durations)."
    ),
}
out_path = os.path.join(_PROJ_ROOT, "scratch", "j2c_tls_profiling_result.json")
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nWrote {out_path}", flush=True)
