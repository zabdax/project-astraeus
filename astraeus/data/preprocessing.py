"""Preprocessing utilities for synthetic and observed light curves."""

from __future__ import annotations

import numpy as np


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
