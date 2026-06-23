"""Completeness sweep over (period, depth, SNR) for ASTRAEUS injection recovery.

This module is a thin sweep layer on top of the existing primitives in
:mod:`astraeus.simulation.synthetic` (``run_injection_recovery``) and
:mod:`astraeus.analysis.detection` (``detect_transit_candidate``). It does
not modify the underlying primitives; it only orchestrates their invocation
across a (period, radius_ratio, SNR) grid, caches per-cell results on disk,
and aggregates them into a :class:`CompletenessSweepResult`.

Phase 1 cost measurement: each ``run_injection_recovery`` call at the default
synthetic parameters (90 d baseline, 4 000 samples) costs ~5.7 s on the
project's reference host. The default grid is sized accordingly so the full
default sweep completes in ~17 minutes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CompletenessSweepConfig:
    """Configuration for a completeness sweep over (period, depth, SNR).

    The sweep builds a log-spaced period × depth grid and an enumerated SNR
    axis, then evaluates ``n_injections`` noisy realizations per cell using
    either the raw-BLS primitive (``run_injection_recovery``) or the full
    detection pipeline (``detect_transit_candidate``).
    """

    # ----- Grid dimensions -----
    period_min_days: float = 0.5
    period_max_days: float = 30.0
    period_count: int = 4
    radius_ratio_min: float = 0.005
    radius_ratio_max: float = 0.10
    radius_ratio_count: int = 3
    snr_values: tuple[float, ...] = (10.0, 30.0, 100.0)

    # ----- Per-cell sampling -----
    n_injections: int = 5
    seed: int = 1729

    # ----- Recovery-mode flag -----
    use_full_pipeline: bool = False

    # ----- Time-series sizing -----
    duration_days: float = 90.0
    samples: int = 4_000

    # ----- Fixed per-cell injection geometry -----
    impact_parameter: float = 0.3
    transit_epoch_fraction: float = 0.5

    # ----- Caching / I/O -----
    cache_dir: str | Path = "outputs/completeness_sweeps"

    # ----- Forwarded to run_injection_recovery in BLS-only mode -----
    known_planets: list[dict] | None = None
    metadata: dict | None = None

    def __post_init__(self) -> None:
        if self.duration_days < 2 * self.period_max_days:
            raise ValueError(
                f"duration_days ({self.duration_days}) must be >= 2 * period_max_days "
                f"({2 * self.period_max_days}) to ensure >= 2 transits per period cell"
            )
        if self.period_count < 2 or self.radius_ratio_count < 2:
            raise ValueError("period_count and radius_ratio_count must be >= 2")
        if len(self.snr_values) < 1:
            raise ValueError("snr_values must contain at least one value")
        if self.n_injections < 1:
            raise ValueError("n_injections must be >= 1")

    @property
    def total_cells(self) -> int:
        return self.period_count * self.radius_ratio_count * len(self.snr_values)


def _canonical_json(obj: Any) -> str:
    """Return a canonical JSON string for hashing (matches logging.py pattern)."""
    return json.dumps(obj, sort_keys=True, default=str)


def _compute_config_hash(config: "CompletenessSweepConfig") -> str:
    """SHA256 of the canonicalized config — also the per-sweep directory name."""
    payload = {k: v for k, v in config.__dict__.items() if k != "cache_dir"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompletenessSweepResult:
    """Aggregated result of one completeness sweep (3D grid: period x depth x SNR)."""

    config: CompletenessSweepConfig
    config_hash: str

    periods_days: np.ndarray
    radius_ratios: np.ndarray
    snrs: np.ndarray

    recovery_rate: np.ndarray
    period_err_median: np.ndarray
    period_err_std: np.ndarray
    depth_err_median: np.ndarray
    depth_err_std: np.ndarray
    n_recovered: np.ndarray
    cell_runtime_seconds: np.ndarray

    total_runtime_seconds: float
    cache_hits: int
    cache_misses: int
    started_at_iso: str
    finished_at_iso: str

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.recovery_rate.shape

    def to_dict(self) -> dict:
        """JSON-serializable view (numpy → list, NaN → null)."""

        def _arr(a: np.ndarray) -> list:
            return np.where(np.isnan(a), None, a).tolist()

        return {
            "schema_version": 1,
            "config_hash": self.config_hash,
            "config": {k: v for k, v in self.config.__dict__.items()},
            "axes": {
                "periods_days": self.periods_days.tolist(),
                "radius_ratios": self.radius_ratios.tolist(),
                "snrs": self.snrs.tolist(),
            },
            "metrics": {
                "recovery_rate": _arr(self.recovery_rate),
                "period_err_median": _arr(self.period_err_median),
                "period_err_std": _arr(self.period_err_std),
                "depth_err_median": _arr(self.depth_err_median),
                "depth_err_std": _arr(self.depth_err_std),
                "n_recovered": self.n_recovered.astype(int).tolist(),
                "cell_runtime_seconds": _arr(self.cell_runtime_seconds),
            },
            "telemetry": {
                "total_runtime_seconds": float(self.total_runtime_seconds),
                "cache_hits": int(self.cache_hits),
                "cache_misses": int(self.cache_misses),
                "started_at_iso": self.started_at_iso,
                "finished_at_iso": self.finished_at_iso,
            },
        }

    def save(self, path: str | Path) -> Path:
        """Atomically write `to_dict()` to disk."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, output)
        return output

    @classmethod
    def load(cls, path: str | Path) -> "CompletenessSweepResult":
        """Inverse of `save`. Recovers numpy arrays from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg_dict = data["config"]
        # Snr_values is a tuple in the dataclass; JSON loads it as a list.
        cfg_dict["snr_values"] = tuple(cfg_dict["snr_values"])

        config = CompletenessSweepConfig(**cfg_dict)
        ax = data["axes"]
        m = data["metrics"]
        t = data["telemetry"]
        return cls(
            config=config,
            config_hash=data["config_hash"],
            periods_days=np.asarray(ax["periods_days"], dtype=float),
            radius_ratios=np.asarray(ax["radius_ratios"], dtype=float),
            snrs=np.asarray(ax["snrs"], dtype=float),
            recovery_rate=np.asarray(m["recovery_rate"], dtype=float),
            period_err_median=np.asarray(m["period_err_median"], dtype=float),
            period_err_std=np.asarray(m["period_err_std"], dtype=float),
            depth_err_median=np.asarray(m["depth_err_median"], dtype=float),
            depth_err_std=np.asarray(m["depth_err_std"], dtype=float),
            n_recovered=np.asarray(m["n_recovered"], dtype=int),
            cell_runtime_seconds=np.asarray(m["cell_runtime_seconds"], dtype=float),
            total_runtime_seconds=float(t["total_runtime_seconds"]),
            cache_hits=int(t["cache_hits"]),
            cache_misses=int(t["cache_misses"]),
            started_at_iso=str(t["started_at_iso"]),
            finished_at_iso=str(t["finished_at_iso"]),
        )


# ---------------------------------------------------------------------------
# Sweep runner (Phase 2 commits b/c — caching added in commit c).
# ---------------------------------------------------------------------------

_VERIFIED_PLANET_STATUSES = frozenset({
    "Verified Planet Candidate",
    "Verified Planet Candidate (Atmospheric Occultation Detected)",
})


def _enumerate_cells(
    config: "CompletenessSweepConfig",
) -> list[tuple[int, float, float, float]]:
    """Return the flat list of (cell_index, period, radius_ratio, snr)."""
    periods = np.geomspace(config.period_min_days, config.period_max_days, config.period_count)
    depths = np.geomspace(config.radius_ratio_min, config.radius_ratio_max, config.radius_ratio_count)
    out: list[tuple[int, float, float, float]] = []
    idx = 0
    for p in periods:
        for d in depths:
            for s in config.snr_values:
                out.append((idx, float(p), float(d), float(s)))
                idx += 1
    return out


def _compute_cell_hash(
    period: float,
    radius_ratio: float,
    snr: float,
    n_injections: int,
    seed: int,
    use_full_pipeline: bool,
) -> str:
    payload = {
        "period": period,
        "radius_ratio": radius_ratio,
        "snr": snr,
        "n_injections": n_injections,
        "seed": seed,
        "use_full_pipeline": use_full_pipeline,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _run_one_cell(
    config: "CompletenessSweepConfig",
    cell_index: int,
    period: float,
    radius_ratio: float,
    snr: float,
) -> dict:
    """Run ``n_injections`` for one (P, D, SNR) cell. Returns a cell-cache dict."""
    from astropy import units as u

    from astraeus.analysis.detection import detect_transit_candidate
    from astraeus.simulation.synthetic import (
        SyntheticTransitScenario,
        generate_synthetic_transit_series,
        run_injection_recovery,
    )

    t_epoch = config.transit_epoch_fraction * config.duration_days
    n_recovered = 0
    period_errs: list[float] = []
    depth_errs: list[float] = []
    injection_records: list[dict] = []
    t0 = time.perf_counter()
    # Injected depth ≈ radius_ratio ** 2 (geometric transit) for residual bookkeeping.
    injected_depth = float(radius_ratio) ** 2

    for i in range(config.n_injections):
        per_inj_seed = config.seed + cell_index * 1000 + i
        scenario = SyntheticTransitScenario(
            duration=config.duration_days * u.day,
            period=period * u.day,
            eccentricity=0.0 * u.dimensionless_unscaled,
            radius_ratio=radius_ratio,
            snr=snr,
            samples=config.samples,
            seed=per_inj_seed,
        )
        series = generate_synthetic_transit_series(scenario)
        record: dict = {"seed": per_inj_seed}

        if config.use_full_pipeline:
            try:
                candidate = detect_transit_candidate(
                    series.time_days,
                    series.observed_flux,
                    target_name=f"completeness_cell_{cell_index}",
                    data_source="completeness_sweep",
                    metadata={
                        "st_rad": 1.0,
                        "st_teff": 5778.0,
                        "st_mass": 1.0,
                        "sy_jmag": 10.0,
                    },
                )
                cand_period = float(candidate.get("period_days", 0.0))
                recovered = bool(candidate.get("candidate_found"))
                rec_depth = float(candidate.get("transit_depth", 0.0))
                rec_snr = float(candidate.get("snr", 0.0))
                vetting = str(candidate.get("vetting_status", "unknown"))
                record.update({
                    "recovered": recovered,
                    "recovered_period": cand_period,
                    "recovered_depth": rec_depth,
                    "recovered_snr": rec_snr,
                    "vetting_status": vetting,
                })
                if recovered and period > 0:
                    rel_err = abs(cand_period - period) / period
                    if rel_err <= 0.01 and vetting in _VERIFIED_PLANET_STATUSES:
                        n_recovered += 1
                        period_errs.append(abs(cand_period - period))
                        depth_errs.append(rec_depth - injected_depth)
            except Exception as exc:  # noqa: BLE001 — sweep must continue past per-injection failures
                record = {"seed": per_inj_seed, "recovered": False, "error": str(exc)}
        else:
            try:
                result = run_injection_recovery(
                    time=series.time_days,
                    flux=series.observed_flux,
                    injected_period=period,
                    injected_r_ratio=radius_ratio,
                    injected_b=config.impact_parameter,
                    injected_epoch=t_epoch,
                    known_planets=config.known_planets,
                    metadata=config.metadata,
                )
                recovered = bool(result.get("signal_recovered"))
                rec_period = float(result.get("recovered_period", 0.0))
                rec_depth = float(result.get("recovered_depth", 0.0))
                rec_snr = float(result.get("recovered_snr", 0.0))
                record.update({
                    "recovered": recovered,
                    "recovered_period": rec_period,
                    "recovered_depth": rec_depth,
                    "recovered_snr": rec_snr,
                    "vetting_status": "n/a",
                })
                if recovered:
                    n_recovered += 1
                    period_errs.append(abs(rec_period - period))
                    depth_errs.append(rec_depth - injected_depth)
            except Exception as exc:  # noqa: BLE001
                record = {"seed": per_inj_seed, "recovered": False, "error": str(exc)}

        injection_records.append(record)

    elapsed = time.perf_counter() - t0
    return {
        "cell": {
            "period_days": period,
            "radius_ratio": radius_ratio,
            "snr": snr,
            "n_injections": config.n_injections,
            "mode": "full_pipeline" if config.use_full_pipeline else "bls_only",
        },
        "result": {
            "recovery_rate": n_recovered / max(config.n_injections, 1),
            "period_err_median": float(np.median(period_errs)) if len(period_errs) >= 1 else float("nan"),
            "period_err_std": float(np.std(period_errs)) if len(period_errs) >= 2 else float("nan"),
            "depth_err_median": float(np.median(depth_errs)) if len(depth_errs) >= 1 else float("nan"),
            "depth_err_std": float(np.std(depth_errs)) if len(depth_errs) >= 2 else float("nan"),
            "n_recovered": n_recovered,
            "runtime_seconds": elapsed,
            "injection_records": injection_records,
        },
        "schema_version": 1,
        "written_at_iso": datetime.now(timezone.utc).isoformat(),
    }


def run_completeness_sweep(
    config: "CompletenessSweepConfig",
    *,
    progress_callback=None,
) -> "CompletenessSweepResult":
    """Run the completeness sweep and aggregate into a 3D result grid.

    Note: caching is added in a later task. This version re-runs every cell.
    """
    config_hash = _compute_config_hash(config)
    periods = np.geomspace(config.period_min_days, config.period_max_days, config.period_count)
    depths = np.geomspace(config.radius_ratio_min, config.radius_ratio_max, config.radius_ratio_count)
    snrs = np.asarray(config.snr_values, dtype=float)

    shape = (config.period_count, config.radius_ratio_count, len(config.snr_values))
    recovery_rate = np.zeros(shape, dtype=float)
    period_err_med = np.full(shape, np.nan, dtype=float)
    period_err_std = np.full(shape, np.nan, dtype=float)
    depth_err_med = np.full(shape, np.nan, dtype=float)
    depth_err_std = np.full(shape, np.nan, dtype=float)
    n_rec = np.zeros(shape, dtype=int)
    cell_rt = np.zeros(shape, dtype=float)

    started = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    for cell_index, period, depth, snr in _enumerate_cells(config):
        cell_data = _run_one_cell(config, cell_index, period, depth, snr)
        r = cell_data["result"]
        i = cell_index // (config.radius_ratio_count * len(config.snr_values))
        rem = cell_index % (config.radius_ratio_count * len(config.snr_values))
        j = rem // len(config.snr_values)
        k = rem % len(config.snr_values)
        recovery_rate[i, j, k] = r["recovery_rate"]
        period_err_med[i, j, k] = r["period_err_median"]
        period_err_std[i, j, k] = r["period_err_std"]
        depth_err_med[i, j, k] = r["depth_err_median"]
        depth_err_std[i, j, k] = r["depth_err_std"]
        n_rec[i, j, k] = r["n_recovered"]
        cell_rt[i, j, k] = r["runtime_seconds"]
        if progress_callback is not None:
            progress_callback(cell_index + 1, config.total_cells, cell_data)

    finished_iso = datetime.now(timezone.utc).isoformat()
    return CompletenessSweepResult(
        config=config,
        config_hash=config_hash,
        periods_days=periods,
        radius_ratios=depths,
        snrs=snrs,
        recovery_rate=recovery_rate,
        period_err_median=period_err_med,
        period_err_std=period_err_std,
        depth_err_median=depth_err_med,
        depth_err_std=depth_err_std,
        n_recovered=n_rec,
        cell_runtime_seconds=cell_rt,
        total_runtime_seconds=time.perf_counter() - started,
        cache_hits=0,
        cache_misses=config.total_cells,
        started_at_iso=started_iso,
        finished_at_iso=finished_iso,
    )