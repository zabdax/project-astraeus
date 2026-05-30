"""Bayesian objective functions for fitting geometric transit models to light curves."""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.core.transit_model import (
    calculate_sky_separation,
    generate_geometric_transit,
)
from astraeus.core.orbital_models import calculate_orbital_position


def log_likelihood(
    theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
) -> float:
    """Calculate the Gaussian log-likelihood of the transit model.

    Physics & Bayesian Logic:
    The likelihood function P(Data | Model, theta) quantifies how well the theoretical 
    transit model reproduces the observed light curve given a set of free parameters 
    (theta). Assuming independent, identically distributed Gaussian uncertainties on the 
    observed fluxes, the log-likelihood is proportional to the negative chi-squared 
    statistic. We compute the theoretical flux drop from the orbital geometry and 
    sky separation, setting the flux drop to zero when the planet is behind the star 
    (z < 0).

    Args:
        theta: Free parameters to fit. Expected to be `(radius_ratio, inclination_deg)`.
        time: Astropy Quantity array of observation times.
        flux: Array of observed normalized fluxes.
        flux_err: Array of flux uncertainties.
        fixed_params: Dictionary of fixed parameters required for the forward model 
            (e.g., 'R_star', 'period', 'semi_major_axis', 'eccentricity').

    Returns:
        float: The log-likelihood value: -0.5 * sum(((flux - model) / flux_err)^2).
    """
    radius_ratio, inclination_deg = theta

    R_star = fixed_params["R_star"]
    period = fixed_params["period"]
    semi_major_axis = fixed_params["semi_major_axis"]
    eccentricity = fixed_params["eccentricity"]

    R_planet = R_star * radius_ratio
    inclination = inclination_deg * u.deg

    x, y, z = calculate_orbital_position(
        time=time,
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
    )

    separation = calculate_sky_separation(x, y, z)

    # Calculate relative flux drop; it returns a dimensionless Quantity.
    flux_drop_quantity = generate_geometric_transit(
        separation=separation,
        R_star=R_star,
        R_planet=R_planet,
    )
    flux_drop = flux_drop_quantity.to_value(u.dimensionless_unscaled)

    # Mask out the secondary eclipse (planet behind the star).
    # Line of sight is along +z, so z < 0 means planet is hidden.
    z_values = z.to_value(semi_major_axis.unit)
    flux_drop[z_values < 0] = 0.0

    model_flux = 1.0 - flux_drop

    return -0.5 * np.sum(((flux - model_flux) / flux_err) ** 2)


def log_prior(theta: tuple[float, ...]) -> float:
    """Evaluate the prior probability of the free parameters.

    Physics & Bayesian Logic:
    The prior P(theta) encodes our domain knowledge and physical constraints on the 
    parameters before seeing the data. We enforce uninformative (uniform) priors within 
    strictly physical bounds:
      - Radius ratio (R_planet / R_star) must be between 0.0 and 1.0 (the planet cannot
        be larger than the star, nor have a negative radius).
      - Inclination must be between 0 and 90 degrees.

    Args:
        theta: Free parameters to fit. Expected to be `(radius_ratio, inclination_deg)`.

    Returns:
        float: 0.0 if parameters are within bounds (log of 1), or -np.inf if outside bounds (log of 0).
    """
    radius_ratio, inclination_deg = theta

    if not (0.0 < radius_ratio < 1.0):
        return -np.inf

    if not (0.0 <= inclination_deg <= 90.0):
        return -np.inf

    return 0.0


def log_probability(
    theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
) -> float:
    """Calculate the unnormalized log-posterior probability.

    Physics & Bayesian Logic:
    According to Bayes' theorem, the posterior probability P(theta | Data) is proportional 
    to the product of the likelihood and the prior:
        Posterior ~ Likelihood * Prior
    In log-space, this becomes addition:
        log(Posterior) ~ log(Likelihood) + log(Prior).
    This function combines our physical bounds (log_prior) and our goodness-of-fit 
    (log_likelihood) to provide the objective function maximized by MCMC algorithms.

    Args:
        theta: Free parameters to fit. Expected to be `(radius_ratio, inclination_deg)`.
        time: Astropy Quantity array of observation times.
        flux: Array of observed normalized fluxes.
        flux_err: Array of flux uncertainties.
        fixed_params: Dictionary of fixed parameters required for the forward model.

    Returns:
        float: The sum of the log-prior and log-likelihood. If the prior is -inf, 
        returns -inf immediately without computing the computationally expensive likelihood.
    """
    lp = log_prior(theta)
    if not np.isfinite(lp):
        return -np.inf

    return lp + log_likelihood(theta, time, flux, flux_err, fixed_params)
