"""High-speed sensitivity engine for UI sliders and interactive analysis."""

from __future__ import annotations

import numpy as np

__all__ = ["get_model_curve"]


def get_model_curve(params: dict, time_array: np.ndarray) -> np.ndarray:
    """Generate a high-speed, vectorized uniform-disk transit model.

    Optimized for iterative calls (e.g., from UI sliders in the Lab) by avoiding
    astropy units and complex integrals. Assumes a circular orbit for maximum
    performance.

    Args:
        params: Dictionary containing orbital and planetary parameters:
            - 'period': Orbital period (days). Default: 1.0
            - 't0': Transit epoch (days). Default: 0.0
            - 'rp_rs': Planet-to-star radius ratio. Default: 0.1
            - 'a_rs': Semi-major axis to star radius ratio. Default: 10.0
            - 'inc': Orbital inclination (degrees). Default: 90.0
        time_array: Array of observation times (e.g., in days).

    Returns:
        Array of relative fluxes (1.0 = out of transit, < 1.0 = in transit),
        with the same shape as `time_array`.
    """
    # Extract parameters with defaults
    period = float(params.get("period", 1.0))
    t0 = float(params.get("t0", 0.0))
    rp_rs = float(params.get("rp_rs", 0.1))
    a_rs = float(params.get("a_rs", 10.0))
    inc_deg = float(params.get("inc", 90.0))

    inc_rad = np.radians(inc_deg)

    # 1. Calculate orbital phase centered around 0
    # phase = 0 is transit center (planet closest to observer)
    phase = ((time_array - t0) / period) % 1.0
    phase[phase > 0.5] -= 1.0

    # 2. Calculate 3D position assuming circular orbit
    angle = 2.0 * np.pi * phase
    x = a_rs * np.sin(angle)
    y = a_rs * np.cos(angle) * np.cos(inc_rad)
    z = a_rs * np.cos(angle) * np.sin(inc_rad)

    # 3. Calculate projected separation on the sky plane
    d = np.sqrt(x**2 + y**2)

    # 4. Calculate flux drop using uniform disk (circle overlap)
    r_star = 1.0
    r_planet = rp_rs

    flux = np.ones_like(time_array, dtype=float)

    # Planet must be in front of star (z > 0) and overlapping in projection
    transit_mask = (z > 0) & (d < (r_star + r_planet))

    if not np.any(transit_mask):
        return flux

    d_in = d[transit_mask]
    overlap = np.zeros_like(d_in)

    # Case A: One disk entirely contained within the other
    contained = d_in <= np.abs(r_star - r_planet)
    overlap[contained] = np.pi * min(r_star, r_planet)**2

    # Case B: Disks partially intersecting
    intersecting = ~contained
    if np.any(intersecting):
        d_int = d_in[intersecting]

        arg1 = (d_int**2 + r_star**2 - r_planet**2) / (2.0 * d_int * r_star)
        arg2 = (d_int**2 + r_planet**2 - r_star**2) / (2.0 * d_int * r_planet)

        arg1 = np.clip(arg1, -1.0, 1.0)
        arg2 = np.clip(arg2, -1.0, 1.0)

        term1 = r_star**2 * np.arccos(arg1)
        term2 = r_planet**2 * np.arccos(arg2)

        root_term = (
            (-d_int + r_star + r_planet)
            * (d_int + r_star - r_planet)
            * (d_int - r_star + r_planet)
            * (d_int + r_star + r_planet)
        )

        term3 = 0.5 * np.sqrt(np.maximum(root_term, 0.0))
        overlap[intersecting] = term1 + term2 - term3

    # Total flux is 1 - (overlap_area / star_area)
    flux_drop = overlap / (np.pi * r_star**2)
    flux[transit_mask] = 1.0 - flux_drop

    return flux
