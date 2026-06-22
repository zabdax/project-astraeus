"""Throwaway script: characterize detect_transit_candidate on REAL
synthetic transit signals, for comparison with the noise FP distribution.

Bucket 9.1 / Phase 1.4. Not a test — a diagnostic.

We replay four real-signal scenarios that the guardrail tests already
assert on (test_pipeline_smoke.py, test_vetting_threshold_hardening.py,
test_agent_detective.py::test_signal_recovery) and record the SNR and
confidence_score that detect_transit_candidate produces. This is the
"must-not-regress" fixture list — the new threshold must sit BELOW these
values and ABOVE the noise distribution.

Output: scratch/bucket9.1_real_signal_characterization.json (and stdout).
"""

from __future__ import annotations

import json
import os
import sys
import time
from statistics import mean, median

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.simulation.synthetic import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)


def _build_m_dwarf_hot_planet(seed: int = 7) -> tuple[np.ndarray, np.ndarray, dict]:
    """Hot planet around M-dwarf (test_vetting_threshold_hardening scenario)."""
    rng = np.random.default_rng(seed)
    n_points = 4000
    period_days = 1.5
    duration_days = 0.08
    primary_depth = 0.04
    secondary_depth = 0.0010
    duration_total = 16.0
    t0_days = 0.5

    t = np.linspace(0.0, duration_total, n_points)
    phase = (t - t0_days + 0.5 * period_days) % period_days - 0.5 * period_days
    in_transit = np.abs(phase) < 0.5 * duration_days
    flux = np.ones_like(t)
    flux[in_transit] -= primary_depth
    phase_secondary = ((t - t0_days) / period_days) % 1.0
    in_secondary = np.abs(phase_secondary - 0.5) < 0.03
    flux[in_secondary & ~in_transit] -= secondary_depth
    flux = flux + rng.normal(0.0, 1e-4, size=t.shape)
    metadata = {"st_rad": 0.5, "st_teff": 3500.0, "st_mass": 0.5, "sy_jmag": 10.0}
    return t, flux, metadata


def _build_earth_sun_analog(seed: int = 7) -> tuple[np.ndarray, np.ndarray, dict]:
    """Earth-Sun analog primary transit (no secondary) — 2.0d, 4% depth."""
    rng = np.random.default_rng(seed)
    n_points = 4000
    period_days = 2.0
    duration_days = 0.08
    primary_depth = 0.04
    duration_total = 16.0
    t0_days = 0.5

    t = np.linspace(0.0, duration_total, n_points)
    phase = (t - t0_days + 0.5 * period_days) % period_days - 0.5 * period_days
    in_transit = np.abs(phase) < 0.5 * duration_days
    flux = np.ones_like(t)
    flux[in_transit] -= primary_depth
    flux = flux + rng.normal(0.0, 1e-4, size=t.shape)
    metadata = {"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0}
    return t, flux, metadata


def _build_hot_jupiter_clean(seed: int = 7) -> tuple[np.ndarray, np.ndarray, dict]:
    """Quiet hot-Jupiter scenario from test_vetting_threshold_hardening
    (period 3.0d, depth 1%, no secondary)."""
    rng = np.random.default_rng(seed)
    n_points = 4000
    period_days = 3.0
    duration_days = 0.1
    primary_depth = 0.01
    duration_total = 16.0
    t0_days = 0.5

    t = np.linspace(0.0, duration_total, n_points)
    phase = (t - t0_days + 0.5 * period_days) % period_days - 0.5 * period_days
    in_transit = np.abs(phase) < 0.5 * duration_days
    flux = np.ones_like(t)
    flux[in_transit] -= primary_depth
    flux = flux + rng.normal(0.0, 1e-4, size=t.shape)
    metadata = {"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0}
    return t, flux, metadata


def _build_test_signal_recovery() -> tuple[np.ndarray, np.ndarray]:
    """test_agent_detective.py::test_signal_recovery fixture: period=3.14d,
    depth=0.02, sigma=0.001, 1000 samples over 20 days."""
    n = 1000
    time = np.linspace(0, 20, n)
    flux = np.ones_like(time)
    period_true = 3.14
    duration = 0.1
    depth = 0.02
    phases = time % period_true
    transit_mask = (phases < duration / 2) | (phases > period_true - duration / 2)
    flux[transit_mask] -= depth
    np.random.seed(42)
    flux += np.random.normal(0, 0.001, n)
    return time, flux


def _build_pipeline_smoke() -> tuple[np.ndarray, np.ndarray]:
    """test_pipeline_smoke.py fixture: synthetic transit scenario at
    samples=2000 (seed=42 internal)."""
    scenario = SyntheticTransitScenario(samples=2000)
    light_curve = generate_synthetic_transit_series(scenario)
    return light_curve.time_days, light_curve.observed_flux


def _summarise(rows: list[dict]) -> dict:
    snr = [r["snr"] for r in rows]
    conf = [r["confidence_score"] for r in rows]
    return {
        "n": len(rows),
        "snr_min": min(snr), "snr_max": max(snr),
        "snr_median": median(snr), "snr_mean": mean(snr),
        "confidence_min": min(conf), "confidence_max": max(conf),
        "confidence_median": median(conf), "confidence_mean": mean(conf),
    }


def main() -> None:
    scenarios = [
        ("pipeline_smoke (SyntheticTransitScenario, samples=2000)", _build_pipeline_smoke),
        ("test_signal_recovery (3.14d, depth=0.02, sigma=0.001)", _build_test_signal_recovery),
        ("hot_jupiter_clean (3.0d, depth=0.01, no secondary)", _build_hot_jupiter_clean),
        ("hot_planet_around_m_dwarf (1.5d, primary=0.04, secondary=0.001)", _build_m_dwarf_hot_planet),
        ("earth_sun_analog (2.0d, depth=0.04)", _build_earth_sun_analog),
    ]

    rows = []
    t0 = time.time()
    for name, builder in scenarios:
        # Each scenario is run 5 times with different random offsets to
        # capture natural variance (the synthetic builder has its own
        # internal seed, so the offset is in noise via local re-seed
        # where applicable).
        for repeat in range(5):
            t, flux, metadata = None, None, None
            if name.startswith("pipeline_smoke"):
                t, flux = builder()
                metadata = {"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0}
            elif name.startswith("test_signal_recovery"):
                t, flux = builder()
                metadata = {"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0}
            else:
                t, flux, metadata = builder(seed=7 + repeat)

            res = detect_transit_candidate(t, flux, metadata=metadata, snr_threshold=5.0)
            candidate = bool(res.get("candidate_found", res.get("is_candidate", False)))
            row = {
                "scenario": name,
                "repeat": repeat,
                "candidate_found": candidate,
                "is_candidate": candidate,
                "confidence_score": float(res.get("confidence_score", 0.0)),
                "snr": float(res.get("snr", 0.0)),
                "period": float(res.get("period", res.get("period_days", 0.0))),
                "transit_depth": float(res.get("transit_depth", 0.0)),
                "vetting_status": str(res.get("vetting_status", "")),
            }
            rows.append(row)
            print(
                f"{name[:60]:<60}  r{repeat}  "
                f"{'FP' if not candidate else 'OK'}  "
                f"snr={row['snr']:8.3f}  conf={row['confidence_score']:8.3f}  "
                f"period={row['period']:7.4f}d  depth={row['transit_depth']:.4f}  "
                f"status={row['vetting_status']}",
                flush=True,
            )

    dt = time.time() - t0

    # Group by scenario
    by_scenario: dict[str, list[dict]] = {}
    for r in rows:
        by_scenario.setdefault(r["scenario"], []).append(r)
    summaries = {name: _summarise(group) for name, group in by_scenario.items()}

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bucket9.1_real_signal_characterization.json",
    )
    payload = {
        "snr_threshold": 5.0,
        "summary_by_scenario": summaries,
        "rows": rows,
        "elapsed_seconds": dt,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print()
    print("=" * 70)
    print("Per-scenario summary (5 repeats each):")
    for name, s in summaries.items():
        print(f"  {name}")
        print(f"    snr      min={s['snr_min']:.2f}  med={s['snr_median']:.2f}  max={s['snr_max']:.2f}  mean={s['snr_mean']:.2f}")
        print(f"    conf     min={s['confidence_min']:.2f}  med={s['confidence_median']:.2f}  max={s['confidence_max']:.2f}  mean={s['confidence_mean']:.2f}")
    print()
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
