"""Error analysis module using MCMC sampling."""

import numpy as np
import emcee
from astropy import units as u

from astraeus.analysis.fitting import log_probability
from astraeus.core.constants import (
    MCMC_ACCEPTANCE_MAX,
    MCMC_ACCEPTANCE_MIN,
    MCMC_BURNIN_FRACTION,
    MCMC_MIN_EFFECTIVE_SAMPLES,
)


class MCMCConvergenceError(RuntimeError):
    """An MCMC posterior failed its convergence gates (P4-A).

    Fail-closed: raised only when the caller passes
    ``require_converged=True``. The default path still returns numbers
    (legacy behavior), so this exception can never surprise an existing
    caller — it must be opted into per call.
    """


def _assess_convergence(
    acceptance: float,
    tau: list[float] | np.ndarray | None,
    n_post_burnin: int,
    min_effective: int = MCMC_MIN_EFFECTIVE_SAMPLES,
) -> dict:
    """Pure gate logic: acceptance band + autocorrelation effective size.

    Returns a report dict with ``converged`` and machine-readable
    ``reasons``. A ``tau`` of None (autocorr estimation failed) is a
    negative verdict, never a pass — an unmeasurable chain is not a
    converged chain.
    """
    reasons: list[str] = []
    acceptance_ok = bool(MCMC_ACCEPTANCE_MIN <= acceptance <= MCMC_ACCEPTANCE_MAX)
    if not acceptance_ok:
        reasons.append(
            f"acceptance {acceptance:.3f} outside "
            f"[{MCMC_ACCEPTANCE_MIN}, {MCMC_ACCEPTANCE_MAX}]"
        )
    if tau is None:
        n_effective_min = 0.0
        effective_ok = False
        reasons.append("autocorr time estimation failed")
    else:
        tau_max = float(np.max(np.asarray(tau, dtype=float)))
        n_effective_min = float(n_post_burnin / tau_max) if tau_max > 0 else 0.0
        effective_ok = bool(n_effective_min >= min_effective)
        if not effective_ok:
            reasons.append(
                f"effective samples {n_effective_min:.1f} < {min_effective} "
                f"(tau_max={tau_max:.1f})"
            )
    return {
        "acceptance": float(acceptance),
        "acceptance_ok": acceptance_ok,
        "tau": None if tau is None else [float(t) for t in np.asarray(tau).ravel()],
        "n_effective_min": n_effective_min,
        "effective_ok": effective_ok,
        "converged": bool(acceptance_ok and effective_ok),
        "reasons": reasons,
    }

def run_mcmc(
    best_fit_theta: tuple[float, ...],
    time: u.Quantity,
    flux: np.ndarray,
    flux_err: np.ndarray,
    fixed_params: dict,
    param_names: list[str] = None,
    n_walkers: int = 32,
    n_steps: int = 2000,
    progress_callback: callable = None,
    return_acceptance: bool = False,
    seed: int | None = None,
    return_convergence: bool = False,
    require_converged: bool = False,
    min_effective: int = MCMC_MIN_EFFECTIVE_SAMPLES,
):
    """Run an MCMC simulation to quantify the uncertainty of recovered parameters.

    Args:
        best_fit_theta: Starting values for the free parameters (e.g., from an optimizer).
        time: Astropy Quantity array of observation times.
        flux: Array of observed normalized fluxes.
        flux_err: Array of flux uncertainties.
        fixed_params: Dictionary of fixed parameters required for the forward model.
        n_walkers: Number of walkers in the ensemble.
        n_steps: Number of MCMC steps to run.
        progress_callback: Optional callback for progress updates.
        return_acceptance: If True, returns the mean acceptance fraction.
        seed: Optional RNG seed for reproducible walker initialization
            (audit fix M11, 2026-08-21).  When None, the legacy unseeded
            global-RNG behavior is kept.
        return_convergence: If True (P4-A), appends a convergence report
            dict (acceptance + autocorrelation gates) to the return tuple.
        require_converged: If True (P4-A), raises MCMCConvergenceError
            instead of returning an unconverged posterior. Opt-in per call;
            the default preserves the legacy always-return behavior.
        min_effective: Minimum post-burn-in effective samples per
            parameter for the converged verdict.

    Returns:
        If return_acceptance is False:
            tuple[np.ndarray, np.ndarray]: The flattened chain and percentiles array.
        If return_acceptance is True:
            tuple[np.ndarray, np.ndarray, float]: The flattened chain, percentiles array, and mean acceptance fraction.
        If return_convergence is True, a convergence report dict is
        appended as the final tuple element in both cases.
    """
    ndim = len(best_fit_theta)

    # Initialize the starting positions of the walkers in a tiny Gaussian ball
    # tightly clustered around the best_fit_theta.  A supplied seed makes the
    # posterior reproducible from identical inputs (audit fix M11).
    if seed is not None:
        rng = np.random.default_rng(seed)
        pos = best_fit_theta + 1e-4 * rng.normal(size=(n_walkers, ndim))
    else:
        pos = best_fit_theta + 1e-4 * np.random.randn(n_walkers, ndim)
    
    # Instantiate the EnsembleSampler passing in log_probability
    sampler = emcee.EnsembleSampler(
        n_walkers, 
        ndim, 
        log_probability, 
        args=(time, flux, flux_err, fixed_params, param_names)
    )
    
    # Run the MCMC simulation
    if progress_callback is None:
        sampler.run_mcmc(pos, n_steps, progress=True)
    else:
        for i, _ in enumerate(sampler.sample(pos, iterations=n_steps)):
            progress_callback(i + 1, n_steps)
    
    # Discard the first 20% of steps as "burn-in" and flatten the remaining chain
    burnin = int(MCMC_BURNIN_FRACTION * n_steps)
    flat_samples = sampler.get_chain(discard=burnin, flat=True)

    # Calculate the 16th, 50th, and 84th percentiles for each parameter
    percentiles = np.percentile(flat_samples, [16, 50, 84], axis=0)

    # Transpose to get shape (n_params, 3) if there are multiple parameters
    percentiles = percentiles.T

    mean_acc: float | None = None
    if return_acceptance:
        mean_acc = float(np.mean(sampler.acceptance_fraction))

    # P4-A convergence gates (opt-in verdict + opt-in enforcement; the
    # legacy numbers above are byte-identical either way).
    report: dict | None = None
    if return_convergence or require_converged:
        if mean_acc is None:
            mean_acc = float(np.mean(sampler.acceptance_fraction))
        try:
            tau = sampler.get_autocorr_time(tol=0, quiet=True)
        except Exception:
            tau = None
        report = _assess_convergence(
            mean_acc, tau, n_post_burnin=n_steps - burnin,
            min_effective=min_effective,
        )
        if require_converged and not report["converged"]:
            raise MCMCConvergenceError(
                "MCMC posterior failed convergence gates: "
                + "; ".join(report["reasons"])
            )

    if return_acceptance and return_convergence:
        return flat_samples, percentiles, mean_acc, report
    if return_acceptance:
        return flat_samples, percentiles, mean_acc
    if return_convergence:
        return flat_samples, percentiles, report

    return flat_samples, percentiles
