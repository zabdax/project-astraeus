"""Phase 1, J3: Decompose the 184s BLSSearchEngine.search() cost.

Splits the call into four timed sections and reports each:
  1. autoperiod()            (line 45) — period grid construction
  2. model.power()           (line 49) — box-fitting grid evaluation
  3. window periodogram      (lines 53-57) — LombScargle.autopower
  4. alias-rejection loop    (lines 60-129) — Python loop over candidates

Uses the exact synthetic curve from e2e_kepler90d_real_path.py
(200d / 9,795 cadences / single Kepler-90d-like transit, known_periods=[]).
This is the same input that produced the 184s lump-sum number last round.

No astraeus/ source changes; pure diagnostic. Read-only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# Make astraeus importable when run from scratch/
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from astropy.timeseries import BoxLeastSquares, LombScargle
from astraeus.analysis.bls_search import BLSSearchEngine

# --- Match the e2e_kepler90d_real_path.py curve exactly ---------------------
KEPLER90D_PERIOD_D = 59.73667
KEPLER90D_DEPTH_PPM = 602.0
KEPLER90D_DURATION_D = 4.2 / 24.0
KEPLER90D_T0_BJD = 130.0
BASELINE_D = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0  # Kepler long cadence
N_CADENCES = int(BASELINE_D / CADENCE_D)  # ~ 9,795
NOISE_PPM = 100.0
SEED = 20260706


def make_curve() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=SEED)
    t = np.arange(N_CADENCES) * CADENCE_D
    y = 1.0 + (NOISE_PPM * 1e-6) * rng.standard_normal(N_CADENCES)
    period = KEPLER90D_PERIOD_D
    t0 = KEPLER90D_T0_BJD
    duration = KEPLER90D_DURATION_D
    depth = KEPLER90D_DEPTH_PPM * 1e-6
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    abs_phase = np.abs(phase)
    ramp_duration = 0.1 * duration
    flat_duration = duration - 2 * ramp_duration
    in_flat = abs_phase <= (flat_duration / 2.0)
    in_ramp = (abs_phase > (flat_duration / 2.0)) & (abs_phase <= (duration / 2.0))
    ramp_x = abs_phase[in_ramp] - (flat_duration / 2.0)
    y[in_flat] -= depth
    y[in_ramp] -= depth * (1.0 - (ramp_x / ramp_duration))
    return t, y


def main() -> int:
    print(f"[J3] Curve: baseline={BASELINE_D}d, n_cadences={N_CADENCES}, "
          f"cadence={CADENCE_D*24*60:.1f}min, seed={SEED}")
    print(f"[J3] Python: {sys.version.split()[0]}, numpy: {np.__version__}")

    time_arr, flux_arr = make_curve()

    # --- Section 1: BoxLeastSquares() + autoperiod() -------------------------
    t0_total = time.perf_counter()
    model = BoxLeastSquares(time_arr, flux_arr)
    T_baseline = float(np.max(time_arr) - np.min(time_arr))
    p_min = 0.5
    p_max = 450.0 if T_baseline > 300.0 else min(450.0, T_baseline / 2.0)
    print(f"[J3] T_baseline={T_baseline:.2f}d -> p_max={p_max:.2f}d")

    t1 = time.perf_counter()
    periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)
    t2 = time.perf_counter()
    autoperiod_s = t2 - t1
    n_periods = len(periods)
    print(f"[J3] autoperiod: {autoperiod_s:.4f}s -> n_periods={n_periods}")

    # --- Section 2: model.power() -------------------------------------------
    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    durations = durations[durations < np.min(periods)]
    n_durations = len(durations)
    print(f"[J3] duration grid: {n_durations} values")

    t3 = time.perf_counter()
    res = model.power(periods, durations)
    t4 = time.perf_counter()
    power_s = t4 - t3
    print(f"[J3] model.power({n_periods}x{n_durations}): {power_s:.4f}s")

    # --- Section 3: window periodogram --------------------------------------
    t5 = time.perf_counter()
    ls = LombScargle(time_arr, np.ones_like(time_arr), fit_mean=False, center_data=False)
    freq_window, power_window = ls.autopower(minimum_frequency=1/1000.0, maximum_frequency=1/10.0)
    top_window_indices = np.argsort(power_window)[-5:]
    top_window_freqs = freq_window[top_window_indices]
    t6 = time.perf_counter()
    window_s = t6 - t5
    n_window_freqs = len(freq_window)
    print(f"[J3] window periodogram: {window_s:.4f}s "
          f"(n_freqs={n_window_freqs}, top_window_freqs={top_window_freqs})")

    # --- Section 4: alias-rejection loop ------------------------------------
    sorted_indices = np.argsort(res.power)[::-1]
    n_candidates = len(sorted_indices)
    known_periods: list[float] = []  # cold iteration, empty list

    best_period = None
    best_snr = 0.0
    best_depth = 0.0
    best_power = 0.0
    transit_time = 0.0
    duration = 0.0
    accepted_idx = None
    candidates_scanned = 0

    t7 = time.perf_counter()
    for idx in sorted_indices:
        cand_period = float(res.period[idx])
        cand_freq = 1.0 / cand_period
        is_alias = False
        for prev_period in known_periods:
            ratio = cand_period / prev_period
            is_harmonic = False
            for h in [0.25, 0.33, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0]:
                if abs(ratio - h) / h < 0.05:
                    is_harmonic = True
                    break
            if is_harmonic:
                is_alias = True
                break
            prev_freq = 1.0 / prev_period
            for w_freq in top_window_freqs:
                for k in [1, 2, 3, 4, 5]:
                    for m in [1, 2, 3, 4, 5]:
                        if abs(cand_freq - (prev_freq + k * w_freq) / m) < 1e-4:
                            is_alias = True
                            break
                        if abs(cand_freq - abs(prev_freq - k * w_freq) / m) < 1e-4:
                            is_alias = True
                            break
                    if is_alias:
                        break
                if is_alias:
                    break
            if is_alias:
                break
        candidates_scanned += 1
        if not is_alias:
            best_period = cand_period
            best_power = float(res.power[idx])
            best_depth = float(res.depth[idx])
            transit_time = res.transit_time[idx]
            duration = res.duration[idx]
            best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(
                time_arr, flux_arr, best_period, transit_time, duration)
            best_depth = computed_best_depth if computed_best_depth > 0 else best_depth
            accepted_idx = idx
            break

    # Fallback if all candidates alias-rejected
    if best_period is None:
        best_idx = sorted_indices[0]
        best_period = float(res.period[best_idx])
        best_power = float(res.power[best_idx])
        best_depth = float(res.depth[best_idx])
        transit_time = res.transit_time[best_idx]
        duration = res.duration[best_idx]
        best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(
            time_arr, flux_arr, best_period, transit_time, duration)
        best_depth = computed_best_depth if computed_best_depth > 0 else best_depth
        accepted_idx = best_idx
    t8 = time.perf_counter()
    alias_loop_s = t8 - t7

    t9 = time.perf_counter()
    total_s = t9 - t0_total

    # --- Summary -------------------------------------------------------------
    print("\n[J3] ===== DECOMPOSITION =====")
    sections = [
        ("autoperiod (grid construction)", autoperiod_s),
        ("model.power (BLS box-fitting)", power_s),
        ("window periodogram (LombScargle.autopower)", window_s),
        ("alias-rejection loop (Python)", alias_loop_s),
    ]
    measured_sum = sum(s for _, s in sections)
    for name, dt in sections:
        pct = 100.0 * dt / total_s if total_s > 0 else 0.0
        print(f"  {name:>45}: {dt:8.4f}s  ({pct:5.1f}%)")
    overhead_s = total_s - measured_sum
    print(f"  {'(unaccounted overhead)':>45}: {overhead_s:8.4f}s  "
          f"({100.0*overhead_s/total_s if total_s>0 else 0:5.1f}%)")
    print(f"  {'TOTAL':>45}: {total_s:8.4f}s")
    print(f"\n[J3] candidates scanned: {candidates_scanned} / {n_candidates}")
    print(f"[J3] accepted candidate idx: {accepted_idx}")
    print(f"[J3] accepted period: {best_period:.6f}d "
          f"(target = {KEPLER90D_PERIOD_D:.5f}d, "
          f"rel_err={abs(best_period - KEPLER90D_PERIOD_D)/KEPLER90D_PERIOD_D*100:.4f}%)")
    print(f"[J3] known_periods during this call: {known_periods}  "
          f"(len={len(known_periods)})")

    out = {
        "baseline_d": BASELINE_D,
        "n_cadences": int(N_CADENCES),
        "n_periods": int(n_periods),
        "n_durations": int(n_durations),
        "n_window_freqs": int(n_window_freqs),
        "n_candidates": int(n_candidates),
        "candidates_scanned": int(candidates_scanned),
        "accepted_idx": int(accepted_idx) if accepted_idx is not None else None,
        "known_periods_len_during_call": len(known_periods),
        "autoperiod_s": autoperiod_s,
        "model_power_s": power_s,
        "window_periodogram_s": window_s,
        "alias_loop_s": alias_loop_s,
        "overhead_s": overhead_s,
        "total_s": total_s,
        "accepted_period_d": best_period,
        "target_period_d": KEPLER90D_PERIOD_D,
    }
    out_path = SCRIPT_DIR / "j3_decompose_bls_result.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[J3] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
