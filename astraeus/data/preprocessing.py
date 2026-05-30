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
