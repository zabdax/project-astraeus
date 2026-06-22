"""Bucket 10 — characterize the threshold=0.0 behavior of
VettingEngine.vet_transit_shape empirically so that the new positive
threshold in Phase 2 can be motivated by the observed distribution of
(delta_chi2_u - delta_chi2_v), not by trial-and-error.

Generates four classes of synthetic light curves:
  A) Clear U-shape (high-SNR real planet)            -- expected to be "Likely Planet"
  B) Clear V-shape (grazing / eclipsing binary)      -- expected to be "Ambiguous"
  C) Marginal / ambiguous (low-SNR near-noise)       -- expected distribution to set threshold
  D) Flat (pure noise, no transit)                   -- expected "Ambiguous"

Records: delta_chi2_u, delta_chi2_v, delta_u_minus_v, vetting_status,
vetting_confidence for each.

Output: scratch/bucket10_threshold_characterization.json

Read-only (does NOT modify vetting.py). Run with current default threshold=0.0
so we see the natural separation between real U-shape and ambiguous cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astraeus.analysis.vetting import VettingEngine


OUT_PATH = Path(__file__).parent / "bucket10_threshold_characterization.json"


# ---------------------------------------------------------------------------
# Synthetic light-curve generators.
# ---------------------------------------------------------------------------
# We use the same convention as the rest of the codebase:
#   flux ~ 1.0 out of transit, flux ~ 1 - depth in transit.
# ---------------------------------------------------------------------------


def _phase_fold(t: np.ndarray, period: float, t0: float) -> np.ndarray:
    return (t - t0 + 0.5 * period) % period - 0.5 * period


def make_u_shape(
    n_points: int = 4000,
    period: float = 3.0,
    duration: float = 0.1,
    depth: float = 0.01,
    noise_std: float = 1e-4,
    ingress_frac: float = 0.10,
    t0: float = 1.5,
    span_days: float = 16.0,
    seed: int = 1,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Realistic planet transit: trapezoid with 10% ingress/egress."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, span_days, n_points)
    phase = _phase_fold(t, period, t0)
    flux = np.ones_like(t)
    in_trans = np.abs(phase) < 0.5 * duration
    ingress = 0.5 * duration * ingress_frac
    flat_region = np.abs(phase) < (0.5 * duration - ingress)
    flux[in_trans] = 1.0 - depth
    slope_mask = in_trans & ~flat_region
    if ingress > 0:
        flux[slope_mask] = 1.0 - depth * (0.5 * duration - np.abs(phase[slope_mask])) / ingress
    flux = flux + rng.normal(0.0, noise_std, size=t.shape)
    return t, flux, period, t0, duration


def make_v_shape(
    n_points: int = 4000,
    period: float = 3.0,
    duration: float = 0.1,
    depth: float = 0.01,
    noise_std: float = 1e-4,
    t0: float = 1.5,
    span_days: float = 16.0,
    seed: int = 2,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Grazing/eclipsing binary: pure V (linear ramp from edges to center)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, span_days, n_points)
    phase = _phase_fold(t, period, t0)
    flux = np.ones_like(t)
    in_trans = np.abs(phase) < 0.5 * duration
    flux[in_trans] = 1.0 - depth * (1.0 - 2.0 * np.abs(phase[in_trans]) / duration)
    flux = flux + rng.normal(0.0, noise_std, size=t.shape)
    return t, flux, period, t0, duration


def make_flat(
    n_points: int = 4000,
    span_days: float = 16.0,
    noise_std: float = 1e-4,
    seed: int = 3,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Pure noise — no transit signal."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, span_days, n_points)
    flux = 1.0 + rng.normal(0.0, noise_std, size=t.shape)
    return t, 1.0 + (flux - 1.0), 3.0, 1.5, 0.1


def make_marginal(
    n_points: int = 4000,
    period: float = 3.0,
    duration: float = 0.1,
    depth: float = 0.0005,         # very shallow
    noise_std: float = 5e-3,       # 100x baseline noise
    ingress_frac: float = 0.10,
    t0: float = 1.5,
    span_days: float = 16.0,
    seed: int = 4,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Low-SNR near-noise U-shape — should sit in the ambiguous gap."""
    return make_u_shape(
        n_points=n_points,
        period=period,
        duration=duration,
        depth=depth,
        noise_std=noise_std,
        ingress_frac=ingress_frac,
        t0=t0,
        span_days=span_days,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Run vet_transit_shape over each scenario and collect metrics.
# ---------------------------------------------------------------------------


def characterize_one(label: str, args: dict, n_repeats: int = 5) -> dict:
    """Run vet_transit_shape n_repeats times for one scenario."""
    results = []
    for k in range(n_repeats):
        # Pass the seed-offset as a derived seed so we get independent noise
        # realizations of the same physical scenario.
        local_args = dict(args)
        if "seed" in local_args:
            local_args["seed"] = local_args["seed"] + 100 * k
        t, flux, period, t0, duration = _generate(label, local_args)
        r = VettingEngine.vet_transit_shape(t, flux, period, t0, duration, 0.01)
        results.append({
            "delta_chi2_u": r.get("delta_chi2_u", 0.0),
            "delta_chi2_v": r.get("delta_chi2_v", 0.0),
            "delta_u_minus_v": r.get("delta_chi2_u", 0.0) - r.get("delta_chi2_v", 0.0),
            "vetting_status": r.get("vetting_status"),
            "vetting_confidence": r.get("vetting_confidence"),
            "u_shape_chi2": r.get("u_shape_chi2"),
            "v_shape_chi2": r.get("v_shape_chi2"),
        })
    return {"label": label, "n_repeats": n_repeats, "results": results}


def _generate(label: str, args: dict):
    if label == "u_shape_clear":
        return make_u_shape(**args)
    if label == "v_shape_clear":
        return make_v_shape(**args)
    if label == "flat":
        return make_flat(**args)
    if label == "u_shape_marginal":
        return make_marginal(**args)
    raise ValueError(f"unknown label: {label}")


def main() -> None:
    scenarios = [
        ("u_shape_clear", {"depth": 0.01, "noise_std": 1e-4, "seed": 1}),
        ("v_shape_clear", {"depth": 0.01, "noise_std": 1e-4, "seed": 2}),
        ("u_shape_marginal", {"depth": 0.0005, "noise_std": 5e-3, "seed": 4}),
        ("flat", {"noise_std": 1e-4, "seed": 3}),
    ]
    n_repeats = 5
    out = {
        "threshold_default": "0.0 (current, the bug)",
        "n_repeats_per_scenario": n_repeats,
        "scenarios": [characterize_one(label, args, n_repeats=n_repeats)
                      for label, args in scenarios],
    }

    # Per-class summary statistics: min / median / max of delta_u_minus_v.
    summary = {}
    for s in out["scenarios"]:
        vals = [r["delta_u_minus_v"] for r in s["results"]]
        statuses = [r["vetting_status"] for r in s["results"]]
        summary[s["label"]] = {
            "delta_u_minus_v_min": min(vals),
            "delta_u_minus_v_median": float(np.median(vals)),
            "delta_u_minus_v_max": max(vals),
            "delta_u_minus_v_std": float(np.std(vals)),
            "statuses_observed": sorted(set(statuses)),
            "n_runs_with_likely_planet": sum(1 for s_ in statuses if s_ == "Likely Planet"),
        }
    out["summary"] = summary

    OUT_PATH.write_text(json.dumps(out, indent=2, default=float))
    print(f"Wrote {OUT_PATH}")
    print()
    print("Per-class delta_u_minus_v (delta_chi2_u - delta_chi2_v) distribution:")
    print("-" * 72)
    for label, stats in summary.items():
        print(f"  {label:20s}  "
              f"min={stats['delta_u_minus_v_min']:12.3f}  "
              f"median={stats['delta_u_minus_v_median']:12.3f}  "
              f"max={stats['delta_u_minus_v_max']:12.3f}  "
              f"std={stats['delta_u_minus_v_std']:8.3f}  "
              f"LikelyPlanet={stats['n_runs_with_likely_planet']}/{n_repeats}")
    print()
    print("Verdict (current threshold=0.0):")
    for label, stats in summary.items():
        print(f"  {label:20s} -> statuses {stats['statuses_observed']}")


if __name__ == "__main__":
    main()