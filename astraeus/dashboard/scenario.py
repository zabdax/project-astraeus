"""Dashboard input models and validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardTransitScenario:
    """Primitive UI inputs for an interactive transit simulation."""

    radius_ratio: float
    period_days: float
    eccentricity: float
    inclination_degrees: float
    snr: int
    samples: int = 900
