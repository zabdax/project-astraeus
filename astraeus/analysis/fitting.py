"""Bayesian objective functions for fitting geometric transit models to light curves."""

from __future__ import annotations

import copy
import numpy as np
from astropy import units as u

from astraeus.core.transit_model import generate_multi_planet_transit


def _coerce_dimensionless(val) -> u.Quantity:
    """Wrap a plain number as a dimensionless Quantity (pass Quantities through).

    Audit fix M3 (2026-08-21): the sampler emits plain floats, but the
    forward model validates astropy Quantities, so dimensionless free
    parameters (e.g. ``eccentricity``) must be coerced before model
    construction.
    """
    if isinstance(val, u.Quantity):
        return val
    return u.Quantity(val, u.dimensionless_unscaled)


def _resolve_planet_dict(p: dict, fitted: set, R_star: u.Quantity, u1: float, u2: float) -> dict:
    """Build the forward-model argument dict for one planet.

    Audit fix M4 (2026-08-21): free-parameter names take precedence over
    their fixed twins — a fitted ``radius_ratio`` defines ``R_planet`` and
    a fitted ``inclination_deg`` defines ``inclination``, overriding (not
    being overridden by) the corresponding fixed value.  Supplying BOTH
    twins statically in ``fixed_params`` is ambiguous and raises
    ``ValueError``.
    """
    p_dict = {
        "R_star": R_star,
        "u1": u1,
        "u2": u2,
        "period": p["period"],
        "semi_major_axis": p["semi_major_axis"],
        "eccentricity": _coerce_dimensionless(p.get("eccentricity", 0.0)),
    }

    # Radius: fitted radius_ratio wins over a fixed R_planet twin.
    if "radius_ratio" in fitted:
        p_dict["R_planet"] = R_star * p["radius_ratio"]
    elif "radius_ratio" in p and "R_planet" in p:
        raise ValueError(
            "Ambiguous planet configuration: both 'radius_ratio' and 'R_planet' "
            "are fixed simultaneously; provide only one of the pair."
        )
    elif "radius_ratio" in p:
        p_dict["R_planet"] = R_star * p["radius_ratio"]
    elif "R_planet" in p:
        p_dict["R_planet"] = p["R_planet"]
    else:
        p_dict["R_planet"] = R_star * 0.1

    # Inclination: fitted inclination_deg wins over a fixed 'inclination' twin.
    if "inclination_deg" in fitted:
        p_dict["inclination"] = p["inclination_deg"] * u.deg
    elif "inclination" in fitted:
        p_dict["inclination"] = _coerce_angle(p["inclination"])
    elif "inclination_deg" in p and "inclination" in p:
        raise ValueError(
            "Ambiguous planet configuration: both 'inclination_deg' and "
            "'inclination' are fixed simultaneously; provide only one of the pair."
        )
    elif "inclination_deg" in p:
        p_dict["inclination"] = p["inclination_deg"] * u.deg
    elif "inclination" in p:
        p_dict["inclination"] = _coerce_angle(p["inclination"])
    else:
        p_dict["inclination"] = 90.0 * u.deg

    return p_dict


def _coerce_angle(val) -> u.Quantity:
    """Coerce a numeric inclination to degrees (Quantities pass through)."""
    if isinstance(val, u.Quantity):
        return val
    return u.Quantity(val, u.deg)


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

    # Track which parameters arrive from the sampler so the free-parameter
    # names take precedence over any fixed twin (audit fix M4, 2026-08-21).
    fitted_top: set = set()
    fitted_planets: dict = {}

    for name, val in zip(param_names, theta):
        if name.startswith("planet_"):
            parts = name.split("_", 2)
            if len(parts) == 3 and parts[1].isdigit():
                idx = int(parts[1])
                fitted_planets.setdefault(idx, set()).add(parts[2])
                if "planets" not in params:
                    params["planets"] = []
                while len(params["planets"]) <= idx:
                    params["planets"].append({})
                params["planets"][idx][parts[2]] = val
            else:
                params[name] = val
                fitted_top.add(name)
        else:
            params[name] = val
            fitted_top.add(name)

    R_star = params.get("R_star", 1.0 * u.R_sun)
    u1 = params.get("u1", 0.0)
    u2 = params.get("u2", 0.0)

    planet_list = []

    if "planets" in params:
        for idx, p in enumerate(params["planets"]):
            planet_list.append(
                _resolve_planet_dict(p, fitted_planets.get(idx, set()), R_star, u1, u2)
            )
    else:
        planet_list.append(
            _resolve_planet_dict(params, fitted_top, R_star, u1, u2)
        )

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
