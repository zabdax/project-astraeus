"""Plotting utilities for ASTRAEUS validation workflows."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_synthetic_validation(
    time_days: np.ndarray,
    theoretical_flux: np.ndarray,
    observed_flux: np.ndarray,
    output_path: str | Path,
) -> Path:
    """Save a two-panel synthetic light-curve validation plot.

    The top panel compares the noiseless model against the injected-noise
    observation. The bottom panel isolates the residuals, defined as
    observed minus theoretical flux.
    """

    time = np.asarray(time_days, dtype=float)
    theoretical = np.asarray(theoretical_flux, dtype=float)
    observed = np.asarray(observed_flux, dtype=float)

    if not (time.shape == theoretical.shape == observed.shape):
        raise ValueError("time_days, theoretical_flux, and observed_flux must match")

    residuals = observed - theoretical
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, (curve_axis, residual_axis) = plt.subplots(
        2,
        1,
        figsize=(11.0, 7.0),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
        constrained_layout=True,
    )

    curve_axis.plot(
        time,
        theoretical,
        color="tab:blue",
        linewidth=2.0,
        label="Theoretical",
    )
    curve_axis.scatter(
        time,
        observed,
        color="tab:orange",
        s=8,
        alpha=0.45,
        linewidths=0,
        label="Noise-injected",
    )
    curve_axis.set_ylabel("Relative flux")
    curve_axis.set_title("Synthetic Hot Jupiter Transit Validation")
    curve_axis.legend(loc="best")
    curve_axis.grid(alpha=0.25)

    residual_axis.axhline(0.0, color="0.25", linewidth=1.0)
    residual_axis.scatter(
        time,
        residuals,
        color="tab:green",
        s=8,
        alpha=0.6,
        linewidths=0,
    )
    residual_axis.set_xlabel("Time [days]")
    residual_axis.set_ylabel("Residual")
    residual_axis.grid(alpha=0.25)

    fig.savefig(output, dpi=200)
    plt.close(fig)

    return output
