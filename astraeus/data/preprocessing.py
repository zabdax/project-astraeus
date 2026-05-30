"""Preprocessing utilities for synthetic and observed light curves."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def inject_gaussian_noise(
    flux: np.ndarray,
    snr: float,
    seed: int | None = 42,
) -> np.ndarray:
    """Return a light curve with Gaussian white noise at a target SNR.

    The noise standard deviation is estimated from the mean absolute signal
    level, so normalized light curves near unity use approximately
    ``sigma = 1 / snr``.
    """

    flux_array = np.asarray(flux, dtype=float)
    if flux_array.size == 0:
        raise ValueError("flux must contain at least one value")

    if not np.isfinite(snr) or snr <= 0.0:
        raise ValueError("snr must be a positive finite value")

    signal_level = np.mean(np.abs(flux_array))
    noise_std = signal_level / snr

    rng = np.random.default_rng(seed)
    noise = rng.normal(loc=0.0, scale=noise_std, size=flux_array.shape)

    return flux_array + noise


def detrend_lightcurve(
    time: np.ndarray,
    flux: np.ndarray,
    window_length: int = 101,
) -> np.ndarray:
    """Detrend a light curve using a Savitzky-Golay filter.

    Models the low-frequency stellar trend and divides the raw flux by this
    trend to yield a flat baseline of 1.0, preserving transit dips intact.
    """
    flux_array = np.asarray(flux, dtype=float)
    
    # Ensure window_length is valid for savgol_filter
    w = min(window_length, len(flux_array))
    if w % 2 == 0:
        w -= 1
        
    if w < 3:
        # Fallback if array is too small for a meaningful filter
        return flux_array / np.nanmedian(flux_array)

    trend = savgol_filter(flux_array, window_length=w, polyorder=2)
    return flux_array / trend


def phase_fold_data(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    t0: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Phase fold continuous time series data.

    Folds the data across the planet's orbital period so all individual
    transits line up on top of one another.

    Returns:
        A tuple of (folded_time, folded_flux), sorted by phase.
    """
    time_array = np.asarray(time, dtype=float)
    flux_array = np.asarray(flux, dtype=float)
    
    # Calculate the phase (centered at 0)
    phase = ((time_array - t0 + 0.5 * period) % period) - 0.5 * period
    
    # Sort the data by phase
    sort_mask = np.argsort(phase)
    return phase[sort_mask], flux_array[sort_mask]


def standardize_imported_data(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
) -> dict[str, np.ndarray | float]:
    """Sanitize and scale raw imported light curve data.

    Drops NaN, infinite, or negative values. If the median flux is vastly
    greater than 1.5, it normalizes the flux and flux_err by the median
    baseline.

    Args:
        time: The time array.
        flux: The flux array.
        flux_err: The flux error array.

    Returns:
        A dictionary containing the cleaned and scaled arrays, as well as
        metadata like the original median flux.
    """
    time_arr = np.asarray(time, dtype=float)
    flux_arr = np.asarray(flux, dtype=float)
    err_arr = np.asarray(flux_err, dtype=float)

    if not (time_arr.shape == flux_arr.shape == err_arr.shape):
        raise ValueError("time, flux, and flux_err must have the same shape")

    # Filter invalid entries: NaNs, Infinities, and negative values.
    valid_mask = (
        np.isfinite(time_arr) & (time_arr >= 0) &
        np.isfinite(flux_arr) & (flux_arr >= 0) &
        np.isfinite(err_arr) & (err_arr >= 0)
    )

    clean_time = time_arr[valid_mask]
    clean_flux = flux_arr[valid_mask]
    clean_err = err_arr[valid_mask]

    if clean_flux.size == 0:
        raise ValueError("No valid data points remain after sanitization")

    median_flux = float(np.median(clean_flux))

    # Normalize if baseline is vastly greater than 1.5
    if median_flux > 1.5:
        clean_flux = clean_flux / median_flux
        clean_err = clean_err / median_flux
        scale_factor = median_flux
    else:
        scale_factor = 1.0

    return {
        "time": clean_time,
        "flux": clean_flux,
        "flux_err": clean_err,
        "scale_factor": scale_factor,
        "original_median": median_flux,
    }
