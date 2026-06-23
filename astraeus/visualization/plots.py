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


def plot_corner(
    flat_samples: np.ndarray,
    labels: list[str],
    true_values: list[float],
    output_path: str | Path,
) -> Path:
    """Generate a corner plot of the posterior distributions.

    Args:
        flat_samples: Flattened array of MCMC samples.
        labels: Parameter labels for the axes.
        true_values: True values for the parameters.
        output_path: Path to save the plot.
    """
    import corner

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig = corner.corner(
        flat_samples,
        labels=labels,
        truths=true_values,
        truth_color="tab:blue",
        show_titles=True,
        title_kwargs={"fontsize": 12},
    )
    fig.savefig(output, dpi=200)
    plt.close(fig)

    return output


def plot_real_retrieval(
    time: np.ndarray,
    observed_flux: np.ndarray,
    theoretical_flux: np.ndarray,
    output_path: str | Path,
) -> Path:
    """Save a validation plot of real phase-folded data against the best-fit model.

    Args:
        time: Phase-folded time array.
        observed_flux: Observed flux array.
        theoretical_flux: Best-fit model flux array.
        output_path: Path to save the plot.

    Returns:
        Path: Path to the saved plot.
    """
    time_arr = np.asarray(time, dtype=float)
    observed = np.asarray(observed_flux, dtype=float)
    theoretical = np.asarray(theoretical_flux, dtype=float)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10.0, 6.0), constrained_layout=True)

    # Sort the theoretical curve so it plots smoothly
    sort_mask = np.argsort(time_arr)

    ax.scatter(
        time_arr,
        observed,
        color="0.6",
        s=4,
        alpha=0.5,
        linewidths=0,
        label="Phase-folded data",
    )
    ax.plot(
        time_arr[sort_mask],
        theoretical[sort_mask],
        color="tab:red",
        linewidth=2.5,
        label="Best-fit model (Quadratic LD)",
    )

    ax.set_xlabel("Phase [days]")
    ax.set_ylabel("Relative Flux")
    ax.set_title("Exoplanet Parameter Retrieval Validation")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)

    fig.savefig(output, dpi=200)
    plt.close(fig)

    return output


def plot_completeness_map(
    result,
    output_dir,
) -> tuple:
    """Render a 2D heatmap of recovery rate plus an SNR-slope line plot.

    Args:
        result: CompletenessSweepResult. The duck-typed access (no import) avoids
            a circular import with astraeus.simulation.completeness.
        output_dir: Directory to write the two PNGs into.

    Returns:
        (heatmap_path, snr_slope_path): Paths to the two PNGs.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    mode = "full_pipeline" if result.config.use_full_pipeline else "bls_only"

    if result.snrs.size == 1:
        fig, ax = plt.subplots(figsize=(8.0, 6.0), constrained_layout=True)
        im = ax.imshow(
            result.recovery_rate[:, :, 0],
            origin="lower",
            aspect="auto",
            extent=(
                np.log10(result.periods_days[0]),
                np.log10(result.periods_days[-1]),
                np.log10(result.radius_ratios[0]),
                np.log10(result.radius_ratios[-1]),
            ),
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        ax.set_xlabel("log10(period [days])")
        ax.set_ylabel("log10(radius_ratio)")
        ax.set_title(
            f"Completeness (mode={mode}, n_inj={result.config.n_injections}, "
            f"SNR={result.snrs[0]:.1f})"
        )
        fig.colorbar(im, ax=ax, label="Recovery rate")
        heatmap_path = output / "heatmap.png"
        fig.savefig(heatmap_path, dpi=200)
        plt.close(fig)
    else:
        n = result.snrs.size
        fig, axes = plt.subplots(
            1, n, figsize=(4.0 * n, 5.0), constrained_layout=True, sharey=True
        )
        if n == 1:
            axes = [axes]
        for idx, (ax_i, snr) in enumerate(zip(axes, result.snrs)):
            im = ax_i.imshow(
                result.recovery_rate[:, :, idx],
                origin="lower",
                aspect="auto",
                extent=(
                    np.log10(result.periods_days[0]),
                    np.log10(result.periods_days[-1]),
                    np.log10(result.radius_ratios[0]),
                    np.log10(result.radius_ratios[-1]),
                ),
                cmap="viridis",
                vmin=0.0,
                vmax=1.0,
            )
            ax_i.set_title(f"SNR={snr:.1f}")
            if idx == 0:
                ax_i.set_ylabel("log10(radius_ratio)")
            ax_i.set_xlabel("log10(period [days])")
        fig.colorbar(im, ax=axes, label="Recovery rate")
        fig.suptitle(f"Completeness ({mode}, n_inj={result.config.n_injections})")
        heatmap_path = output / "heatmap.png"
        fig.savefig(heatmap_path, dpi=200)
        plt.close(fig)

    # SNR-slope plot: pick a reference grid (every other period × middle depth,
    # max 6 lines).
    fig2, ax2 = plt.subplots(figsize=(8.0, 5.0), constrained_layout=True)
    p_step = max(1, result.periods_days.size // 3)
    p_refs = list(range(0, result.periods_days.size, p_step))[:3]
    d_ref = result.radius_ratios.size // 2
    plotted = 0
    for i in p_refs:
        if plotted >= 6:
            break
        ax2.plot(
            result.snrs,
            result.recovery_rate[i, d_ref, :],
            marker="o",
            label=f"P={result.periods_days[i]:.2f}d, D={result.radius_ratios[d_ref]:.4f}",
        )
        plotted += 1
    ax2.axhline(0.5, color="0.5", linestyle="--", linewidth=1.0, label="50% reference")
    ax2.set_xlabel("Injection SNR")
    ax2.set_ylabel("Recovery rate")
    ax2.set_title("Recovery vs SNR (reference period / depth cells)")
    ax2.set_ylim(-0.02, 1.02)
    ax2.legend(loc="best", fontsize=8)
    ax2.grid(alpha=0.25)
    snr_path = output / "snr_slope.png"
    fig2.savefig(snr_path, dpi=200)
    plt.close(fig2)

    return heatmap_path, snr_path
