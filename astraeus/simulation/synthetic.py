"""Synthetic light-curve generation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from astropy import units as u

from astraeus.core.geometry import calculate_sky_separation
from astraeus.core.orbital_models import calculate_orbital_position
from astraeus.core.transit_model import generate_geometric_transit
from astraeus.data.preprocessing import inject_gaussian_noise


@dataclass(frozen=True)
class SyntheticTransitScenario:
    """Configuration for a synthetic exoplanet transit validation run."""

    duration: u.Quantity = field(default_factory=lambda: 10.0 * u.day)
    period: u.Quantity = field(default_factory=lambda: 3.0 * u.day)
    eccentricity: u.Quantity = field(
        default_factory=lambda: 0.0 * u.dimensionless_unscaled
    )
    radius_ratio: float = 0.1
    snr: float = 200.0
    samples: int = 4_000
    seed: int = 42
    stellar_radius: u.Quantity = field(default_factory=lambda: 1.0 * u.R_sun)
    semi_major_axis: u.Quantity = field(default_factory=lambda: 10.0 * u.R_sun)
    inclination: u.Quantity = field(default_factory=lambda: 90.0 * u.deg)

    @classmethod
    def hot_jupiter(cls) -> "SyntheticTransitScenario":
        """Return the default ten-day hot-Jupiter validation scenario."""

        return cls()


@dataclass(frozen=True)
class LightCurveSeries:
    """Container for generated synthetic light-curve arrays."""

    time_days: np.ndarray
    theoretical_flux: np.ndarray
    observed_flux: np.ndarray

    @property
    def residuals(self) -> np.ndarray:
        """Return observed minus theoretical flux."""

        return self.observed_flux - self.theoretical_flux


def generate_synthetic_transit_series(
    scenario: SyntheticTransitScenario,
) -> LightCurveSeries:
    """Generate theoretical and noisy light curves for a transit scenario."""

    _validate_scenario(scenario)

    time_days = _generate_time_grid(scenario.duration, scenario.samples)
    time_quantity = time_days * u.day
    theoretical_flux = _generate_theoretical_flux(time_quantity, scenario)
    observed_flux = inject_gaussian_noise(
        theoretical_flux,
        snr=scenario.snr,
        seed=scenario.seed,
    )

    return LightCurveSeries(
        time_days=time_days,
        theoretical_flux=theoretical_flux,
        observed_flux=observed_flux,
    )


def _generate_time_grid(duration: u.Quantity, samples: int) -> np.ndarray:
    """Return an evenly sampled time grid in days."""

    return np.linspace(
        0.0,
        duration.to_value(u.day),
        samples,
        endpoint=True,
    )


def _generate_theoretical_flux(
    time: u.Quantity,
    scenario: SyntheticTransitScenario,
) -> np.ndarray:
    """Calculate noiseless relative flux from orbital and transit physics."""

    x, y, z = calculate_orbital_position(
        time=time,
        period=scenario.period,
        semi_major_axis=scenario.semi_major_axis,
        eccentricity=scenario.eccentricity,
        inclination=scenario.inclination,
    )
    separation = calculate_sky_separation(x, y, z)
    planet_radius = scenario.radius_ratio * scenario.stellar_radius
    flux_drop = generate_geometric_transit(
        separation=separation,
        R_star=scenario.stellar_radius,
        R_planet=planet_radius,
    ).to_value(u.dimensionless_unscaled)

    planet_in_front = z.to_value(scenario.stellar_radius.unit) > 0.0
    return 1.0 - np.where(planet_in_front, flux_drop, 0.0)


def _validate_scenario(scenario: SyntheticTransitScenario) -> None:
    """Validate scenario fields that are local to synthetic sampling."""

    if scenario.samples < 2:
        raise ValueError("samples must be at least 2")

    if not np.isfinite(scenario.radius_ratio) or scenario.radius_ratio <= 0.0:
        raise ValueError("radius_ratio must be a positive finite value")

    if scenario.radius_ratio > 1.0:
        raise ValueError("radius_ratio must be less than or equal to 1.0")
