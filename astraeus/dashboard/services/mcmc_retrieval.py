"""MCMC parameter-retrieval workflow for ingested light-curve data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from astropy import units as u
from scipy.signal import savgol_filter

from astraeus.analysis.error_analysis import run_mcmc
from astraeus.analysis.optimization import find_best_fit
from astraeus.core.transit_model import generate_model_flux
from astraeus.data.preprocessing import detrend_lightcurve, phase_fold_data


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class MCMCConfig:
    """User-configurable retrieval settings from the Streamlit form."""

    period_days: float
    transit_epoch: float
    stellar_radius_rsun: float
    semi_major_axis_au: float
    eccentricity: float
    radius_ratio_guess: float
    inclination_degrees_guess: float
    u1_guess: float
    u2_guess: float
    n_steps: int
    n_walkers: int = 32


@dataclass(frozen=True)
class MCMCRetrievalResult:
    """Computed MCMC retrieval outputs needed by the UI."""

    folded_time: np.ndarray
    folded_flux: np.ndarray
    theoretical_flux: np.ndarray
    median_params: np.ndarray
    percentiles: np.ndarray
    flat_samples: np.ndarray
    t0_used: float
    t0_was_estimated: bool


def run_retrieval(
    time_raw: np.ndarray,
    flux_raw: np.ndarray,
    config: MCMCConfig,
    progress_callback: ProgressCallback | None = None,
) -> MCMCRetrievalResult:
    """Run detrending, phase folding, optimization, MCMC, and model validation."""

    flux_detrended = detrend_lightcurve(time_raw, flux_raw)
    t0_used, t0_was_estimated = resolve_transit_epoch(
        time_raw,
        flux_detrended,
        config.transit_epoch,
    )
    folded_time, folded_flux = phase_fold_data(
        time_raw,
        flux_detrended,
        config.period_days,
        t0_used,
    )
    folded_flux_err = estimate_folded_flux_error(folded_time, folded_flux)

    # Audit fix C6 (2026-08-21): the model dips at periapsis + P/4 while the
    # folded data dips at phase 0 — shift model time so the optimizer, MCMC,
    # and the verification model all share one aligned convention.
    from astraeus.data.preprocessing import folded_time_to_model_time
    time_u = folded_time_to_model_time(folded_time, config.period_days) * u.day
    fixed_params = build_fixed_params(config)
    param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
    initial_guess = (
        config.radius_ratio_guess,
        config.inclination_degrees_guess,
        config.u1_guess,
        config.u2_guess,
    )

    best_fit_theta, _success = find_best_fit(
        initial_guess_theta=initial_guess,
        time=time_u,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
        param_names=param_names,
    )

    flat_samples, percentiles = run_mcmc(
        best_fit_theta=best_fit_theta,
        time=time_u,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
        param_names=param_names,
        n_walkers=config.n_walkers,
        n_steps=config.n_steps,
        progress_callback=progress_callback,
    )
    median_params = percentiles[:, 1]
    theoretical_flux = generate_retrieval_model(time_u, fixed_params, param_names, median_params)

    return MCMCRetrievalResult(
        folded_time=folded_time,
        folded_flux=folded_flux,
        theoretical_flux=theoretical_flux,
        median_params=median_params,
        percentiles=percentiles,
        flat_samples=flat_samples,
        t0_used=float(t0_used),
        t0_was_estimated=t0_was_estimated,
    )


def resolve_transit_epoch(
    time_raw: np.ndarray,
    flux_detrended: np.ndarray,
    user_t0: float,
) -> tuple[float, bool]:
    """Use the supplied transit epoch or estimate it from the smoothed minimum."""

    if user_t0 != 0.0:
        return float(user_t0), False

    window_length = min(101, len(flux_detrended))
    if window_length % 2 == 0:
        window_length -= 1
    if window_length < 5:
        return float(time_raw[np.argmin(flux_detrended)]), True

    smoothed_flux = savgol_filter(flux_detrended, window_length=window_length, polyorder=2)
    return float(time_raw[np.argmin(smoothed_flux)]), True


def estimate_folded_flux_error(folded_time: np.ndarray, folded_flux: np.ndarray) -> np.ndarray:
    """Estimate a constant flux error from out-of-transit folded data."""

    out_of_transit_mask = np.abs(folded_time) > 0.1
    if np.any(out_of_transit_mask):
        noise_std = np.std(folded_flux[out_of_transit_mask])
    else:
        noise_std = np.std(folded_flux)
    return np.full_like(folded_flux, noise_std)


def build_fixed_params(config: MCMCConfig) -> dict[str, u.Quantity]:
    """Build fixed physical parameters with astropy units."""

    return {
        "R_star": config.stellar_radius_rsun * u.R_sun,
        "period": config.period_days * u.day,
        "semi_major_axis": config.semi_major_axis_au * u.AU,
        "eccentricity": config.eccentricity * u.dimensionless_unscaled,
    }


def generate_retrieval_model(
    time_u: u.Quantity,
    fixed_params: dict[str, u.Quantity],
    param_names: list[str],
    median_params: np.ndarray,
) -> np.ndarray:
    """Generate the theoretical model using median MCMC parameters."""

    params = fixed_params.copy()
    for name, value in zip(param_names, median_params):
        params[name] = value

    inclination = params.get("inclination_deg", 90.0) * u.deg
    return generate_model_flux(
        time=time_u,
        period=params["period"],
        semi_major_axis=params["semi_major_axis"],
        eccentricity=params.get("eccentricity", 0.0 * u.dimensionless_unscaled),
        inclination=inclination,
        R_star=params["R_star"],
        R_planet=params["R_star"] * params["radius_ratio"],
        u1=params.get("u1", 0.0),
        u2=params.get("u2", 0.0),
    )
