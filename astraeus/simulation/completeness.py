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
from dataclasses import dataclass, field
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