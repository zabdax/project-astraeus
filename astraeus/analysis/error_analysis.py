"""Error analysis module using MCMC sampling."""

import numpy as np
import emcee
from astropy import units as u

from astraeus.analysis.fitting import log_probability

def run_mcmc(
    best_fit_theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
    param_names: list[str] = None,
    n_walkers: int = 32,
    n_steps: int = 2000,
) -> tuple[np.ndarray, np.ndarray]:
    """Run an MCMC simulation to quantify the uncertainty of recovered parameters.

    Args:
        best_fit_theta: Starting values for the free parameters (e.g., from an optimizer).
        time: Astropy Quantity array of observation times.
        flux: Array of observed normalized fluxes.
        flux_err: Array of flux uncertainties.
        fixed_params: Dictionary of fixed parameters required for the forward model.
        n_walkers: Number of walkers in the ensemble.
        n_steps: Number of MCMC steps to run.

    Returns:
        tuple[np.ndarray, np.ndarray]: The flattened chain of posterior samples 
        (after discarding 20% burn-in), and an array containing the 16th, 50th, 
        and 84th percentiles for each parameter.
    """
    ndim = len(best_fit_theta)
    
    # Initialize the starting positions of the walkers in a tiny Gaussian ball
    # tightly clustered around the best_fit_theta
    pos = best_fit_theta + 1e-4 * np.random.randn(n_walkers, ndim)
    
    # Instantiate the EnsembleSampler passing in log_probability
    sampler = emcee.EnsembleSampler(
        n_walkers, 
        ndim, 
        log_probability, 
        args=(time, flux, flux_err, fixed_params, param_names)
    )
    
    # Run the MCMC simulation
    sampler.run_mcmc(pos, n_steps, progress=True)
    
    # Discard the first 20% of steps as "burn-in" and flatten the remaining chain
    burnin = int(0.2 * n_steps)
    flat_samples = sampler.get_chain(discard=burnin, flat=True)
    
    # Calculate the 16th, 50th, and 84th percentiles for each parameter
    percentiles = np.percentile(flat_samples, [16, 50, 84], axis=0)
    
    # Transpose to get shape (n_params, 3) if there are multiple parameters
    percentiles = percentiles.T
    
    return flat_samples, percentiles
