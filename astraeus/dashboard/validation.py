"""Dashboard input validation and utility functions."""

from __future__ import annotations

from astraeus.dashboard.scenario import DashboardTransitScenario


def validate_scenario(scenario: DashboardTransitScenario) -> None:
    """Validate slider-level bounds before physics quantities are built."""
    if not 0.0 < scenario.radius_ratio <= 1.0:
        raise ValueError("radius_ratio must satisfy 0 < radius_ratio <= 1")
    if scenario.period_days <= 0.0:
        raise ValueError("period_days must be positive")
    if not 0.0 <= scenario.eccentricity < 1.0:
        raise ValueError("eccentricity must satisfy 0 <= eccentricity < 1")
    if not 0.0 <= scenario.inclination_degrees <= 180.0:
        raise ValueError("inclination_degrees must be between 0 and 180")
    if scenario.snr <= 0:
        raise ValueError("snr must be positive")
    if scenario.samples < 2:
        raise ValueError("samples must be at least 2")


def generate_stable_seed(scenario: DashboardTransitScenario) -> int:
    """Return a deterministic seed for repeatable slider states."""
    scaled_values = (
        int(round(scenario.radius_ratio * 10_000.0)),
        int(round(scenario.period_days * 10_000.0)),
        int(round(scenario.eccentricity * 10_000.0)),
        int(round(scenario.inclination_degrees * 10_000.0)),
        int(scenario.snr),
        int(scenario.samples),
    )
    seed = 0xA57AEE5
    for value in scaled_values:
        seed = ((seed * 1_664_525) + value + 1_013_904_223) % (2**32)
    return seed
