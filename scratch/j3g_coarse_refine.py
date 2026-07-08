"""Phase 1, J3g: Prototype and time a coarse->refine BLS search.

Inputs:
  (a) The 200d / 9,795-cadence single-signal curve (Kepler-90d-like)
      so we can directly compare coarse->refine wall-time to
      BLSSearchEngine.search() on the same curve.
  (b) The SYN-5P-small variant (1500d / 3,000 cadences / 5 injected
      planets at 12/45/120/300/600d) so we can verify the multi-signal
      regression check the reviewer required.

Strategy:
  1. Coarse pass: np.geomspace(p_min, p_max, 2000) with one duration
     (0.1d). Find the top-K peaks by power.
  2. Refine pass: for each top-K peak, build a fine log-spaced grid
     spanning ±2% in period and ±50% in duration around the peak, run
     model.power on each.
  3. Concatenate, return the top candidate by power.

This is a SCRATCH prototype, not a production change to bls_search.py.
We measure and report:
  - coarse pass time
  - refine pass time
  - total wall time
  - recovered period
  - (for SYN-5P) recovered planets list
"""
from __future__ import annotations

import json
import sys
import time as wallclock
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from astropy.timeseries import BoxLeastSquares

# ============================================================================
# Curve builders
# ============================================================================
KEPLER90D_PERIOD_D = 59.73667
KEPLER90D_DEPTH_PPM = 602.0
KEPLER90D_DURATION_D = 4.2 / 24.0
KEPLER90D_T0_BJD = 130.0
BASELINE_D_SINGLE = 200.0
CADENCE_D = 29.4 / 60.0 / 24.0
N_CADENCES_SINGLE = int(BASELINE_D_SINGLE / CADENCE_D)
NOISE_PPM = 100.0
SEED_SINGLE = 20260706

INJECTED_5P = [
    ("p1",  12.0,  500,  5.0,   0.15),
    ("p2",  45.0,  1000, 22.0,  0.25),
    ("p3", 120.0,  800,  80.0,  0.40),
    ("p4", 300.0,  1500, 200.0,  0.60),
    ("p5", 600.0,  2000, 450.0,  0.80),
]
N_SAMPLES_5P = 3000
T_SPAN_5P = 1500.0
SEED_5P = 42


def make_single_curve():
    rng = np.random.default_rng(seed=SEED_SINGLE)
    t = np.arange(N_CADENCES_SINGLE) * CADENCE_D
    y = 1.0 + (NOISE_PPM * 1e-6) * rng.standard_normal(N_CADENCES_SINGLE)
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


def make_5p_curve():
    rng = np.random.default_rng(seed=SEED_5P)
    t = np.linspace(0, T_SPAN_5P, N_SAMPLES_5P)
    y = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES_5P)
    for name, period, depth_ppm, t0, dur in INJECTED_5P:
        phase = ((t - t0) % period) - period / 2.0
        in_tr = np.abs(phase) < dur / 2.0
        y[in_tr] -= depth_ppm / 1e6
    return t, y


# ============================================================================
# Coarse -> refine implementation
# ============================================================================
def coarse_refine_search(
    time: np.ndarray,
    flux: np.ndarray,
    p_min: float = 0.5,
    p_max: float | None = None,
    n_coarse: int = 2000,
    coarse_durations: tuple[float, ...] = (0.05, 0.1, 0.2, 0.4, 0.6, 0.8),
    top_k: int = 5,
    refine_period_frac: float = 0.02,
    refine_durations: tuple[float, ...] = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.8),
    n_refine_period: int = 50,
) -> dict:
    """Coarse-grid then refine. Returns the top candidate dict.

    Times the two passes and stores the breakdown in result['_timing'].
    """
    if p_max is None:
        p_max = min(450.0, (float(np.max(time)) - float(np.min(time))) / 2.0)

    model = BoxLeastSquares(time, flux)

    # --- Pass 1: coarse grid, multi-duration sweep ---
    coarse_periods = np.geomspace(p_min, p_max, n_coarse)
    coarse_durs_arr = np.array(coarse_durations)
    # BoxLeastSquares requires max(duration) < min(period)
    coarse_durs_arr = coarse_durs_arr[coarse_durs_arr < coarse_periods.min()]
    if len(coarse_durs_arr) == 0:
        coarse_durs_arr = np.array([coarse_periods.min() * 0.5])
    tc1 = wallclock.perf_counter()
    coarse_res = model.power(coarse_periods, coarse_durs_arr)
    coarse_s = wallclock.perf_counter() - tc1

    # Find top-K peaks in coarse (over period-duration grid)
    coarse_top_idx = np.argsort(coarse_res.power.ravel())[::-1][:top_k]
    coarse_top_periods = coarse_res.period.ravel()[coarse_top_idx]
    coarse_top_durs = coarse_res.duration.ravel()[coarse_top_idx]
    coarse_top_powers = coarse_res.power.ravel()[coarse_top_idx]

    # --- Pass 2: refine around each top-K peak ---
    refine_results = []
    t_total_refine = 0.0
    for peak_p, peak_d in zip(coarse_top_periods, coarse_top_durs):
        p_lo = peak_p * (1.0 - refine_period_frac)
        p_hi = peak_p * (1.0 + refine_period_frac)
        fine_periods = np.geomspace(p_lo, p_hi, n_refine_period)
        # Center refine durations on the coarse-peak duration
        d_center = peak_d
        d_lo = max(0.01, d_center * 0.5)
        d_hi = d_center * 2.0
        if d_hi - d_lo < 0.05:
            fine_durs = np.array([d_center])
        else:
            fine_durs = np.linspace(d_lo, d_hi, 5)
        # BoxLeastSquares requires max(duration) < min(period)
        fine_durs = fine_durs[fine_durs < fine_periods.min()]
        if len(fine_durs) == 0:
            fine_durs = np.array([fine_periods.min() * 0.5])
        tc2 = wallclock.perf_counter()
        fine_res = model.power(fine_periods, fine_durs)
        t_total_refine += wallclock.perf_counter() - tc2
        refine_results.append(fine_res)
    refine_s = t_total_refine

    # Concatenate refine results and pick the top
    if not refine_results:
        return {
            'period': float(coarse_top_periods[0]),
            'power': float(coarse_top_powers[0]),
            '_timing': {'coarse_s': coarse_s, 'refine_s': refine_s, 'total_s': coarse_s + refine_s},
        }

    # Stack and find global top
    all_powers = np.concatenate([r.power.ravel() for r in refine_results])
    all_periods = np.concatenate([r.period.ravel() for r in refine_results])
    all_durs = np.concatenate([r.duration.ravel() for r in refine_results])
    best_idx = int(np.argmax(all_powers))

    total_s = coarse_s + refine_s
    return {
        'period': float(all_periods[best_idx]),
        'duration': float(all_durs[best_idx]),
        'power': float(all_powers[best_idx]),
        '_coarse_top_periods': [float(p) for p in coarse_top_periods],
        '_coarse_top_durs': [float(d) for d in coarse_top_durs],
        '_coarse_top_powers': [float(p) for p in coarse_top_powers],
        '_timing': {
            'coarse_s': coarse_s,
            'refine_s': refine_s,
            'total_s': total_s,
            'n_coarse_periods': int(n_coarse),
            'n_coarse_durations': int(len(coarse_durs_arr)),
            'n_refine_peaks': int(top_k),
            'n_refine_periods_per_peak': int(n_refine_period),
            'n_refine_durations': int(len(fine_durs)),
        },
    }


# ============================================================================
# Multi-planet recovery: subtract and re-search
# ============================================================================
def mask_transit_simple(time, flux, period, t0, duration, n_mask_widths=1.5):
    """Same shape as BLSSearchEngine.mask_transit()."""
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    mask_window = n_mask_widths * duration
    keep = np.abs(phase) >= 0.5 * mask_window
    return time[keep], flux[keep]


def multi_planet_search(
    time: np.ndarray,
    flux: np.ndarray,
    max_signals: int = 5,
    **kwargs,
) -> list[dict]:
    """Iteratively find and mask out the strongest peak."""
    out = []
    t_active, f_active = time, flux
    for i in range(max_signals):
        if len(t_active) < 100:
            break
        # Recompute p_max from current baseline
        T_active = float(np.max(t_active) - np.min(t_active))
        p_max_active = min(450.0, T_active / 2.0) if T_active > 0 else 50.0
        if p_max_active < 1.0:
            break
        result = coarse_refine_search(t_active, f_active, p_max=p_max_active, **kwargs)
        out.append(result)
        # Mask out the found transit (1.5x duration window)
        if result.get('duration', 0) > 0:
            t_active, f_active = mask_transit_simple(
                t_active, f_active,
                period=result['period'],
                t0=0.0,  # Use a centered mask; t0 estimate from refine is complex
                duration=result.get('duration', 0.1),
            )
    return out


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    out: dict = {}

    # ---- (a) Single-signal curve (direct comparison to BLSSearchEngine) ----
    print("[J3g] === (a) Single-signal curve ===")
    t1, y1 = make_single_curve()
    T_baseline = float(np.max(t1) - np.min(t1))
    print(f"[J3g] n_cadences={len(t1)}, T_baseline={T_baseline:.2f}d, "
          f"target_period={KEPLER90D_PERIOD_D}d")

    cr = coarse_refine_search(t1, y1, p_max=min(450.0, T_baseline/2.0))
    print(f"[J3g] coarse pass: {cr['_timing']['coarse_s']:.4f}s")
    print(f"[J3g] refine pass: {cr['_timing']['refine_s']:.4f}s")
    print(f"[J3g] total:        {cr['_timing']['total_s']:.4f}s")
    print(f"[J3g] coarse top periods: "
          f"{[f'{p:.2f}' for p in cr['_coarse_top_periods']]}")
    print(f"[J3g] recovered period: {cr['period']:.4f}d "
          f"(rel_err = "
          f"{abs(cr['period']-KEPLER90D_PERIOD_D)/KEPLER90D_PERIOD_D*100:.4f}%)")
    out['single'] = {
        'n_cadences': int(len(t1)),
        'T_baseline': T_baseline,
        'target_period': KEPLER90D_PERIOD_D,
        'recovered_period': cr['period'],
        'recovered_power': cr['power'],
        'recovered_duration': cr['duration'],
        'rel_err_pct': abs(cr['period']-KEPLER90D_PERIOD_D)/KEPLER90D_PERIOD_D*100,
        'coarse_s': cr['_timing']['coarse_s'],
        'refine_s': cr['_timing']['refine_s'],
        'total_s': cr['_timing']['total_s'],
        'coarse_top_periods': cr['_coarse_top_periods'],
    }

    # ---- (b) SYN-5P-small multi-planet recovery ----
    print("\n[J3g] === (b) SYN-5P-small multi-planet recovery ===")
    t2, y2 = make_5p_curve()
    print(f"[J3g] n_cadences={len(t2)}, T_baseline={float(np.max(t2)-np.min(t2)):.2f}d")
    print(f"[J3g] injected: {[(n, p) for n, p, *_ in INJECTED_5P]}")

    t_mp_start = wallclock.perf_counter()
    results = multi_planet_search(t2, y2, max_signals=5, top_k=5)
    multi_planet_s = wallclock.perf_counter() - t_mp_start
    print(f"[J3g] multi-planet wall: {multi_planet_s:.2f}s, "
          f"recovered {len(results)} signals")
    recovered = []
    for i, r in enumerate(results):
        period = r['period']
        matched = None
        for (n, p, *_r2) in INJECTED_5P:
            if abs(period - p) / p <= 0.02:
                matched = f"{n}@{p}d"
                recovered.append(matched)
                break
        print(f"  #{i+1}: period={period:.4f}d  matched={matched}  "
              f"power={r.get('power', 0):.4f}")

    out['syn5p'] = {
        'n_cadences': int(len(t2)),
        'T_baseline': float(np.max(t2) - np.min(t2)),
        'injected': [(n, p) for n, p, *_ in INJECTED_5P],
        'recovered': recovered,
        'recovered_count': len(recovered),
        'expected_count': len(INJECTED_5P),
        'all_recovered': len(recovered) == len(INJECTED_5P),
        'wall_s': multi_planet_s,
        'recovered_periods': [r['period'] for r in results],
    }

    out_path = SCRIPT_DIR / "j3g_coarse_refine_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[J3g] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
