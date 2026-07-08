"""Phase 1, J3i: Verify p1 (12d) and p5 (600d) are noise-limited, not grid-limited.

The round-6 claim: on the SYN-5P-small curve (1500d, 3000 cadences), the
top-20 of the periodogram after the J3 fix recovers p2 (45d), p3 (120d),
p4 (300d) but NOT p1 (12d) or p5 (600d). The reviewer wants this verified
mechanically, not inferred from absence.

This script computes, on the SYN-5P-small curve:
  1. The BLS periodogram power at exactly p=12d and p=600d, with the
     correct duration for each (0.15d and 0.80d respectively from
     INJECTED). This is the "true" power at the real signal period.
  2. The periodogram power at the same periods, on a noise-only curve
     (no injected signals). This is the noise floor at the same period.
  3. The median and 99th-percentile power across the full periodogram
     on the SYN-5P-small curve. This is the "where does the top-K
     cutoff sit" reference.
  4. The rank of p=12d and p=600d in the full sorted periodogram.

If power(true) - power(noise-only) is small at p1/p5 (signal barely
above noise), the missing-signal claim is verified as a physical noise
limit, not a search problem.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from astropy.timeseries import BoxLeastSquares

# SYN-5P scenario
N_SAMPLES = 3000
T_SPAN = 1500.0
SEED = 42
INJECTED = [
    ("p1",  12.0,  500,  5.0,   0.15),
    ("p2",  45.0,  1000, 22.0,  0.25),
    ("p3", 120.0,  800,  80.0,  0.40),
    ("p4", 300.0,  1500, 200.0,  0.60),
    ("p5", 600.0,  2000, 450.0,  0.80),
]


def make_curve(with_signals: bool) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=SEED)
    t = np.linspace(0, T_SPAN, N_SAMPLES)
    y = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)
    if with_signals:
        for name, period, depth_ppm, t0, dur in INJECTED:
            phase = ((t - t0) % period) - period / 2.0
            y[np.abs(phase) < dur / 2.0] -= depth_ppm / 1e6
    return t, y


def find_nearest_power(res, target_period: float, target_dur: float):
    """Find the (period, dur) entry in res closest to (target_period,
    target_dur) and return its power. astropy's model.power(periods,
    durations) returns the best (dur) per period; we want the period
    closest to target_period."""
    idx = int(np.argmin(np.abs(res.period - target_period)))
    return {
        "period_actual": float(res.period[idx]),
        "duration_actual": float(res.duration[idx]),
        "power": float(res.power[idx]),
        "index": idx,
    }


def main() -> int:
    print(f"[J3i] SYN-5P-small: N={N_SAMPLES}, T={T_SPAN}d")
    print(f"[J3i] injected: {[(n, p) for n, p, *_ in INJECTED]}")

    t_sig, y_sig = make_curve(with_signals=True)
    t_noise, y_noise = make_curve(with_signals=False)

    # Use the same coarse grid as the J3h ablation (frequency_factor=100)
    m_sig = BoxLeastSquares(t_sig, y_sig)
    m_noise = BoxLeastSquares(t_noise, y_noise)

    t0 = time.perf_counter()
    periods_sig = m_sig.autoperiod(
        duration=0.1, minimum_period=0.5, maximum_period=750.0,
        frequency_factor=100.0,
    )
    periods_noise = m_noise.autoperiod(
        duration=0.1, minimum_period=0.5, maximum_period=750.0,
        frequency_factor=100.0,
    )
    print(f"[J3i] autoperiod: {time.perf_counter()-t0:.2f}s, n_periods={len(periods_sig):,}")

    durs = np.array([0.05, 0.1, 0.2, 0.4, 0.6])
    durs = durs[durs < periods_sig.min()]
    n_durs = len(durs)

    t1 = time.perf_counter()
    res_sig = m_sig.power(periods_sig, durs)
    print(f"[J3i] power(signal): {time.perf_counter()-t1:.2f}s, "
          f"n_periods={len(periods_sig):,}, n_durs={n_durs}")

    t2 = time.perf_counter()
    res_noise = m_noise.power(periods_noise, durs)
    print(f"[J3i] power(noise): {time.perf_counter()-t2:.2f}s")

    # Apply J3 physical mask to both
    _MAX_DUTY_CYCLE = 0.2
    physical_sig = res_sig.duration < (res_sig.period * _MAX_DUTY_CYCLE)
    physical_noise = res_noise.duration < (res_noise.period * _MAX_DUTY_CYCLE)

    pw_sig = np.where(physical_sig, res_sig.power, -np.inf)
    pw_noise = np.where(physical_noise, res_noise.power, -np.inf)

    # Noise floor stats
    pw_noise_finite = pw_noise[pw_noise > -np.inf]
    print(f"\n[J3i] ===== NOISE FLOOR (signal-free curve, same seed) =====")
    print(f"  median power: {np.median(pw_noise_finite):.4e}")
    print(f"  99th pct:     {np.percentile(pw_noise_finite, 99):.4e}")
    print(f"  max power:    {pw_noise_finite.max():.4e}")

    # Signal periodogram stats
    pw_sig_finite = pw_sig[pw_sig > -np.inf]
    print(f"\n[J3i] ===== SIGNAL PERIODOGRAM (SYN-5P-small) =====")
    print(f"  median power: {np.median(pw_sig_finite):.4e}")
    print(f"  99th pct:     {np.percentile(pw_sig_finite, 99):.4e}")
    print(f"  max power:    {pw_sig_finite.max():.4e}")
    print(f"  rank-20 cutoff: {sorted(pw_sig_finite, reverse=True)[19]:.4e}")

    # Power at each true injected period (closest grid point)
    print(f"\n[J3i] ===== POWER AT TRUE INJECTED PERIODS =====")
    rows = []
    for (name, p, _d, _t0, dur) in INJECTED:
        sig_at = find_nearest_power(res_sig, p, dur)
        noise_at = find_nearest_power(res_noise, p, dur)
        # Rank in signal periodogram (after physical mask)
        rank = int(np.sum(pw_sig > sig_at["power"])) + 1
        # Excess power above noise at the same period
        excess = sig_at["power"] - noise_at["power"]
        rel_excess = excess / max(noise_at["power"], 1e-30)
        in_top20 = rank <= 20
        in_top50 = rank <= 50
        in_top100 = rank <= 100
        print(f"  {name}@{p:5.1f}d  true_dur={dur:.2f}d")
        print(f"    signal:    period={sig_at['period_actual']:7.3f}d  "
              f"dur={sig_at['duration_actual']:.3f}d  power={sig_at['power']:.4e}")
        print(f"    noise:     period={noise_at['period_actual']:7.3f}d  "
              f"dur={noise_at['duration_actual']:.3f}d  power={noise_at['power']:.4e}")
        print(f"    excess (sig - noise):  {excess:.4e}  "
              f"rel_excess: {rel_excess:.2f}x")
        print(f"    rank: {rank}  in_top20={in_top20}  in_top50={in_top50}  in_top100={in_top100}")
        rows.append({
            "name": name,
            "true_period": p,
            "true_duration": dur,
            "signal_period": sig_at["period_actual"],
            "signal_dur": sig_at["duration_actual"],
            "signal_power": sig_at["power"],
            "noise_period": noise_at["period_actual"],
            "noise_dur": noise_at["duration_actual"],
            "noise_power": noise_at["power"],
            "excess_power": excess,
            "rel_excess": rel_excess,
            "rank": rank,
            "in_top20": in_top20,
            "in_top50": in_top50,
            "in_top100": in_top100,
        })

    out = {
        "curve": {"n_samples": N_SAMPLES, "t_span": T_SPAN, "seed": SEED},
        "grid": {"frequency_factor": 100.0, "n_periods": len(periods_sig),
                 "n_durations": n_durs},
        "noise_floor": {
            "median": float(np.median(pw_noise_finite)),
            "p99": float(np.percentile(pw_noise_finite, 99)),
            "max": float(pw_noise_finite.max()),
        },
        "signal_periodogram": {
            "median": float(np.median(pw_sig_finite)),
            "p99": float(np.percentile(pw_sig_finite, 99)),
            "max": float(pw_sig_finite.max()),
            "rank20_cutoff": float(sorted(pw_sig_finite, reverse=True)[19]),
        },
        "per_planet": rows,
    }
    out_path = SCRIPT_DIR / "j3i_p1p5_noise_floor.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[J3i] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
