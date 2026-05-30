"""Dashboard-facing simulation orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from astropy import units as u

from astraeus.core.geometry import calculate_sky_separation
from astraeus.core.orbital_models import calculate_orbital_position
from astraeus.core.transit_model import generate_geometric_transit
from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.data.preprocessing import inject_gaussian_noise

STELLAR_RADIUS = 1.0 * u.R_sun


@dataclass(frozen=True)
class DashboardSimulation:
    """Computed arrays and derived metrics for the dashboard views."""

    time_days: np.ndarray
    x_rsun: np.ndarray
    y_rsun: np.ndarray
    z_rsun: np.ndarray
    theoretical_flux: np.ndarray
    observed_flux: np.ndarray
    semi_major_axis_rsun: float
    noise_sigma: float

    @property
    def residuals(self) -> np.ndarray:
        """Return observed minus theoretical flux."""

        return self.observed_flux - self.theoretical_flux

    @property
    def max_depth_ppm(self) -> float:
        """Return the deepest modeled transit depth in parts per million."""

        return float((1.0 - np.min(self.theoretical_flux)) * 1_000_000.0)


def generate_dashboard_simulation(
    scenario: DashboardTransitScenario,
) -> DashboardSimulation:
    """Generate orbit, light-curve, and residual data for one slider state."""

    scenario.validate()

    time_days = np.linspace(0.0, scenario.period_days, scenario.samples)
    time = time_days * u.day
    period = scenario.period_days * u.day
    semi_major_axis = semi_major_axis_for_solar_mass(scenario.period_days).to(u.R_sun)

    x, y, z = calculate_orbital_position(
        time=time,
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=scenario.eccentricity * u.dimensionless_unscaled,
        inclination=scenario.inclination_degrees * u.deg,
    )
    theoretical_flux = generate_theoretical_flux(
        x=x,
        y=y,
        z=z,
        stellar_radius=STELLAR_RADIUS,
        radius_ratio=scenario.radius_ratio,
    )
    observed_flux = inject_gaussian_noise(
        theoretical_flux,
        snr=float(scenario.snr),
        seed=scenario.stable_seed,
    )

    return DashboardSimulation(
        time_days=time_days,
        x_rsun=x.to_value(u.R_sun),
        y_rsun=y.to_value(u.R_sun),
        z_rsun=z.to_value(u.R_sun),
        theoretical_flux=theoretical_flux,
        observed_flux=observed_flux,
        semi_major_axis_rsun=float(semi_major_axis.to_value(u.R_sun)),
        noise_sigma=float(np.mean(np.abs(theoretical_flux)) / scenario.snr),
    )


def semi_major_axis_for_solar_mass(period_days: float) -> u.Quantity:
    """Return semi-major axis from Kepler's third law for a solar-mass host."""

    period_years = (period_days * u.day).to_value(u.year)
    return (period_years ** (2.0 / 3.0)) * u.AU


def generate_theoretical_flux(
    x: u.Quantity,
    y: u.Quantity,
    z: u.Quantity,
    stellar_radius: u.Quantity,
    radius_ratio: float,
) -> np.ndarray:
    """Calculate line-of-sight-aware geometric transit flux."""

    separation = calculate_sky_separation(x, y, z)
    planet_radius = radius_ratio * stellar_radius
    flux_drop = generate_geometric_transit(
        separation=separation,
        R_star=stellar_radius,
        R_planet=planet_radius,
    ).to_value(u.dimensionless_unscaled)
    planet_in_front = z.to_value(stellar_radius.unit) > 0.0

    return 1.0 - np.where(planet_in_front, flux_drop, 0.0)
