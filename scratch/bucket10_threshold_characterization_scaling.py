"""Bucket 10 — extended characterization: vary the signal level (depth)
to confirm the gap between real-U-shape and ambiguous cases scales the
way the threshold=0.001 would predict, AND verify the threshold is not
fragile to small changes in noise/depth.

Hypothesis: the median delta_u_minus_v for a real U-shape scales
roughly as depth^2 (since chi-squared residuals scale as the squared
flux deficit). For a real U-shape at the same depth=0.01 the median
should still be ~+0.002; for a depth=0.005 half-depth case, ~+0.0005;
for very shallow (depth=0.001) the gap should narrow toward zero.

A noise-aware threshold (e.g., 0.001) should:
  * Accept real U-shapes at standard depth
  * Reject very shallow U-shapes that are indistinguishable from noise
  * Not be fooled by larger signal levels into accepting marginal cases
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astraeus.analysis.vetting import VettingEngine


OUT_PATH = Path(__file__).parent / "bucket10_threshold_characterization_scaling.json"


def make_u_shape(period, duration, depth, noise_std, seed):
    rng = np.random.default_rng(seed)
    n_points = 4000
    span_days = 16.0
    t0 = 1.5
    ingress_frac = 0.10
    t = np.linspace(0.0, span_days, n_points)
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    flux = np.ones_like(t)
    in_trans = np.abs(phase) < 0.5 * duration
    ingress = 0.5 * duration * ingress_frac
    flat_region = np.abs(phase) < (0.5 * duration - ingress)
    flux[in_trans] = 1.0 - depth
    slope_mask = in_trans & ~flat_region
    if ingress > 0:
        flux[slope_mask] = 1.0 - depth * (0.5 * duration - np.abs(phase[slope_mask])) / ingress
    flux = flux + rng.normal(0.0, noise_std, size=t.shape)
    return t, flux


def characterize(depth: float, noise_std: float, n_repeats: int = 5) -> dict:
    period = 3.0
    duration = 0.1
    deltas = []
    statuses = []
    for k in range(n_repeats):
        t, flux = make_u_shape(period, duration, depth, noise_std, seed=1000 + 100 * k)
        r = VettingEngine.vet_transit_shape(t, flux, period, 1.5, duration, depth)
        deltas.append(r.get("delta_chi2_u", 0.0) - r.get("delta_chi2_v", 0.0))
        statuses.append(r.get("vetting_status"))
    return {
        "depth": depth,
        "noise_std": noise_std,
        "n_repeats": n_repeats,
        "delta_u_minus_v_median": float(np.median(deltas)),
        "delta_u_minus_v_min": float(min(deltas)),
        "delta_u_minus_v_max": float(max(deltas)),
        "delta_u_minus_v_std": float(np.std(deltas)),
        "statuses_observed": sorted(set(statuses)),
        "n_likely_planet": sum(1 for s in statuses if s == "Likely Planet"),
    }


def main() -> None:
    scenarios = [
        # (depth, noise_std, label)
        (0.02,  1e-4, "u_2pct_clean"),
        (0.01,  1e-4, "u_1pct_clean"),    # reference scenario
        (0.005, 1e-4, "u_0p5pct_clean"),
        (0.002, 1e-4, "u_0p2pct_clean"),
        (0.001, 1e-4, "u_0p1pct_clean"),
        (0.01,  3e-4, "u_1pct_noisy"),
        (0.01,  1e-3, "u_1pct_very_noisy"),
        (0.0005, 5e-3, "u_marginal"),     # same as Phase-1.2 marginal
    ]
    rows = [characterize(d, n, n_repeats=5) for d, n, _ in scenarios]
    out = {
        "threshold_default": "0.0 (current, the bug)",
        "rows": [
            {**r, "label": label}
            for r, (_, _, label) in zip(rows, scenarios)
        ],
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT_PATH}")
    print()
    print(f"{'label':24s}  {'depth':>8s}  {'noise':>10s}  {'median':>12s}  {'min':>12s}  {'max':>12s}  {'Likely?':>8s}")
    print("-" * 96)
    for r in out["rows"]:
        print(f"{r['label']:24s}  {r['depth']:8.4f}  {r['noise_std']:10.6f}  {r['delta_u_minus_v_median']:+12.6f}  {r['delta_u_minus_v_min']:+12.6f}  {r['delta_u_minus_v_max']:+12.6f}  {r['n_likely_planet']:>4d}/5")


if __name__ == "__main__":
    main()