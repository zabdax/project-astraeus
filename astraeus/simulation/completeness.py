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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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