"""Analytical geometric transit light-curve models."""

from __future__ import annotations

import numpy as np
from scipy.integrate import quad_vec
from astropy import units as u

from astraeus.core.geometry import (
    calculate_circle_overlap_area,
    calculate_sky_separation,
)
from astraeus.core.validation import (
    require_convertible_unit,
    require_non_negative_quantity,
    require_positive_quantity,
)
from astraeus.core.orbital_models import calculate_orbital_position

__all__ = [
    "calculate_sky_separation",
    "generate_geometric_transit",
    "generate_model_flux",
    "generate_multi_planet_transit",
]


def generate_geometric_transit(
    separation: u.Quantity,
    R_star: u.Quantity,
    R_planet: u.Quantity,
    u1: float = 0.0,
    u2: float = 0.0,
) -> u.Quantity:
    """Calculate relative flux drop for a transit with quadratic limb darkening.

    Physics derivation:
    This model accounts for the standard quadratic limb darkening law:
    I(mu) / I(1) = 1 - u1 * (1 - mu) - u2 * (1 - mu)**2
    where mu = sqrt(1 - z**2) and z is the normalized distance from the center
    of the stellar disk to the given point. The total blocked flux is computed
    by numerically integrating over concentric stellar rings. For each ring, the
    geometric intersection with the planet disk determines the blocked arc length.

    Geometric assumptions:
    The star and planet are circular disks in projection. The limb darkening
    is radially symmetric. The planet is smaller than or equal to the star,
    and is assumed to be fully opaque. The caller is responsible for ensuring
    the planet is in front of the star.

    Unit expectations:
    ``separation``, ``R_star``, and ``R_planet`` must be Astropy length
    quantities with compatible units. Radii must be strictly positive.
    The limb darkening coefficients ``u1`` and ``u2`` are dimensionless floats.
    The returned relative flux drop is an Astropy dimensionless quantity.
    """

    require_non_negative_quantity(separation, "separation")
    require_positive_quantity(R_star, "R_star")
    require_positive_quantity(R_planet, "R_planet")
    require_convertible_unit(R_planet, R_star.unit, "R_planet")

    if np.any(R_planet.to_value(R_star.unit) > R_star.to_value(R_star.unit)):
        raise ValueError("R_planet must be less than or equal to R_star.")

    delta = (separation / R_star).to_value(u.dimensionless_unscaled)
    rho = (R_planet / R_star).to_value(u.dimensionless_unscaled)
    
    delta_arr = np.atleast_1d(delta)
    
    def I(z):
        mu = np.sqrt(1 - z**2)
        return 1 - u1 * (1 - mu) - u2 * (1 - mu)**2

    def integrand(z):
        res = np.zeros_like(delta_arr, dtype=float)
        
        # When z == 0
        if z == 0:
            mask = rho >= delta_arr
            res[mask] = I(0) * 2 * np.pi * 0 # Always 0
            return res
            
        cos_theta = np.zeros_like(delta_arr, dtype=float)
        
        mask_nonzero = delta_arr > 0
        cos_theta[mask_nonzero] = (z**2 + delta_arr[mask_nonzero]**2 - rho**2) / (2 * z * delta_arr[mask_nonzero])
        
        mask_zero = ~mask_nonzero
        if np.any(mask_zero):
            cos_theta[mask_zero] = -1.0 if z <= rho else 1.0
            
        theta = np.zeros_like(delta_arr, dtype=float)
        
        mask_ge = cos_theta >= 1
        theta[mask_ge] = 0.0
        
        mask_le = cos_theta <= -1
        theta[mask_le] = np.pi
        
        mask_mid = ~(mask_ge | mask_le)
        theta[mask_mid] = np.arccos(cos_theta[mask_mid])
        
        return I(z) * 2 * theta * z

    blocked_flux, _ = quad_vec(integrand, 0, 1, limit=200, epsabs=1e-8, epsrel=1e-8)
    total_flux = np.pi * (1 - u1/3 - u2/6)
    
    relative_flux_drop = blocked_flux / total_flux
    
    if np.isscalar(delta) or (isinstance(delta, np.ndarray) and delta.ndim == 0):
        relative_flux_drop = relative_flux_drop[0]
        
    return relative_flux_drop * u.dimensionless_unscaled


def generate_model_flux(
    time: u.Quantity,
    period: u.Quantity,
    semi_major_axis: u.Quantity,
    eccentricity: u.Quantity,
    inclination: u.Quantity,
    R_star: u.Quantity,
    R_planet: u.Quantity,
    u1: float = 0.0,
    u2: float = 0.0,
) -> np.ndarray:
    """Generate theoretical flux for the given physical parameters."""
    
    x, y, z = calculate_orbital_position(
        time=time,
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
    )

    separation = calculate_sky_separation(x, y, z)

    flux_drop_quantity = generate_geometric_transit(
        separation=separation,
        R_star=R_star,
        R_planet=R_planet,
        u1=u1,
        u2=u2,
    )
    flux_drop = flux_drop_quantity.to_value(u.dimensionless_unscaled)

    z_values = z.to_value(semi_major_axis.unit)
    flux_drop[z_values < 0] = 0.0

    return 1.0 - flux_drop


def generate_multi_planet_transit(
    time: u.Quantity,
    planet_list: list[dict],
) -> np.ndarray:
    """Generate theoretical flux for a system with multiple planets.
    
    Args:
        time: Array of time values.
        planet_list: A list of dictionaries, where each dictionary contains
            the parameters for a single planet to pass to generate_model_flux.
            
    Returns:
        The total relative flux (product of individual transits).
    """
    total_flux = np.ones(len(time), dtype=float)
    
    for planet_params in planet_list:
        flux = generate_model_flux(
            time=time,
            **planet_params
        )
        total_flux *= flux
        
    return total_flux
