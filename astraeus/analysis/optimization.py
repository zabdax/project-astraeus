"""Optimization routines for finding the best-fit transit model parameters."""

from __future__ import annotations

import numpy as np
from astropy import units as u
from scipy.optimize import minimize

from astraeus.analysis.fitting import log_probability


def find_best_fit(
    initial_guess_theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
) -> tuple[np.ndarray, bool]:
    """Find the best-fit parameters using non-linear optimization.

    Minimizes the negative log-probability to find the Maximum A Posteriori (MAP) 
    estimate, providing a robust starting position for MCMC walkers.

    Args:
        initial_guess_theta: Starting values for the free parameters.
        time: Astropy Quantity array of observation times.
        flux: Array of observed normalized fluxes.
        flux_err: Array of flux uncertainties.
        fixed_params: Dictionary of fixed parameters required for the forward model.

    Returns:
        tuple[np.ndarray, bool]: The optimized parameter array and a boolean flag 
        indicating whether the optimizer successfully converged.
    """
    def neg_log_prob(theta):
        lp = log_probability(tuple(theta), time, flux, flux_err, fixed_params)
        if not np.isfinite(lp):
            return np.inf
        return -lp

    try:
        result = minimize(
            fun=neg_log_prob,
            x0=np.array(initial_guess_theta),
            method="Nelder-Mead",
        )
        return result.x, result.success
    except Exception:
        # Return the initial guess and False if optimization fails (e.g., due to numerical issues)
        return np.array(initial_guess_theta), False
