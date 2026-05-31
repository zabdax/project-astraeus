"""Bayesian objective functions for fitting geometric transit models to light curves."""

from __future__ import annotations

import copy
import numpy as np
from astropy import units as u

from astraeus.core.transit_model import generate_multi_planet_transit


def log_likelihood(
    theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
    param_names: list[str] = None,
) -> float:
    """Calculate the Gaussian log-likelihood of the transit model."""
    params = copy.deepcopy(fixed_params)
    if param_names is None:
        param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
        
    for name, val in zip(param_names, theta):
        if name.startswith("planet_"):
            parts = name.split("_", 2)
            if len(parts) == 3 and parts[1].isdigit():
                idx = int(parts[1])
                if "planets" not in params:
                    params["planets"] = []
                while len(params["planets"]) <= idx:
                    params["planets"].append({})
                params["planets"][idx][parts[2]] = val
            else:
                params[name] = val
        else:
            params[name] = val

    R_star = params.get("R_star", 1.0 * u.R_sun)
    u1 = params.get("u1", 0.0)
    u2 = params.get("u2", 0.0)
    
    planet_list = []
    
    if "planets" in params:
        for p in params["planets"]:
            p_dict = {
                "R_star": R_star,
                "u1": u1,
                "u2": u2,
                "period": p["period"],
                "semi_major_axis": p["semi_major_axis"],
                "eccentricity": p.get("eccentricity", 0.0 * u.dimensionless_unscaled),
            }
            radius_ratio = p.get("radius_ratio", 0.1)
            p_dict["R_planet"] = p.get("R_planet", R_star * radius_ratio)
            
            inclination = p.get("inclination_deg", 90.0) * u.deg
            if "inclination" in p:
                inclination = p["inclination"]
            p_dict["inclination"] = inclination
            planet_list.append(p_dict)
    else:
        p_dict = {
            "R_star": R_star,
            "u1": u1,
            "u2": u2,
            "period": params["period"],
            "semi_major_axis": params["semi_major_axis"],
            "eccentricity": params.get("eccentricity", 0.0 * u.dimensionless_unscaled),
        }
        radius_ratio = params.get("radius_ratio", 0.1)
        p_dict["R_planet"] = params.get("R_planet", R_star * radius_ratio)
        
        inclination = params.get("inclination_deg", 90.0) * u.deg
        if "inclination" in params:
            inclination = params["inclination"]
        p_dict["inclination"] = inclination
        planet_list.append(p_dict)
    
    model_flux = generate_multi_planet_transit(time, planet_list)

    return -0.5 * np.sum(((flux - model_flux) / flux_err) ** 2)


def log_prior(theta: tuple[float, ...], param_names: list[str] = None) -> float:
    """Evaluate the prior probability of the free parameters."""
    if param_names is None:
        param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
        
    for name, val in zip(param_names, theta):
        base_name = name
        if name.startswith("planet_"):
            parts = name.split("_", 2)
            if len(parts) == 3 and parts[1].isdigit():
                base_name = parts[2]

        if base_name == "radius_ratio" and not (0.0 < val < 1.0):
            return -np.inf
        if base_name == "inclination_deg" and not (0.0 <= val <= 90.0):
            return -np.inf
        if base_name in ["u1", "u2"] and not (0.0 <= val <= 1.0):
            return -np.inf
        if base_name == "eccentricity" and not (0.0 <= val < 1.0):
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
