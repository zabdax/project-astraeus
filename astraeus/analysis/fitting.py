"""Bayesian objective functions for fitting geometric transit models to light curves."""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.core.transit_model import generate_model_flux


def log_likelihood(
    theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
    param_names: list[str] = None,
) -> float:
    """Calculate the Gaussian log-likelihood of the transit model."""
    params = fixed_params.copy()
    if param_names is None:
        param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
        
    for name, val in zip(param_names, theta):
        params[name] = val

    R_star = params.get("R_star", 1.0 * u.R_sun)
    period = params["period"]
    semi_major_axis = params["semi_major_axis"]
    eccentricity = params.get("eccentricity", 0.0 * u.dimensionless_unscaled)
    
    radius_ratio = params.get("radius_ratio", 0.1)
    inclination = params.get("inclination_deg", 90.0) * u.deg
    if "inclination" in params:
        inclination = params["inclination"]
        
    u1 = params.get("u1", 0.0)
    u2 = params.get("u2", 0.0)
    R_planet = params.get("R_planet", R_star * radius_ratio)
    
    model_flux = generate_model_flux(
        time=time,
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
        R_star=R_star,
        R_planet=R_planet,
        u1=u1,
        u2=u2,
    )

    return -0.5 * np.sum(((flux - model_flux) / flux_err) ** 2)


def log_prior(theta: tuple[float, ...], param_names: list[str] = None) -> float:
    """Evaluate the prior probability of the free parameters."""
    if param_names is None:
        param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
        
    for name, val in zip(param_names, theta):
        if name == "radius_ratio" and not (0.0 < val < 1.0):
            return -np.inf
        if name == "inclination_deg" and not (0.0 <= val <= 90.0):
            return -np.inf
        if name in ["u1", "u2"] and not (0.0 <= val <= 1.0):
            return -np.inf
        if name == "eccentricity" and not (0.0 <= val < 1.0):
            return -np.inf
            
    return 0.0


def log_probability(
    theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
    param_names: list[str] = None,
) -> float:
    """Calculate the unnormalized log-posterior probability."""
    lp = log_prior(theta, param_names)
    if not np.isfinite(lp):
        return -np.inf

    return lp + log_likelihood(theta, time, flux, flux_err, fixed_params, param_names)
