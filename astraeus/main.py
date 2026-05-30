"""Command-line entry point for ASTRAEUS synthetic validation."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from astropy import units as u
import numpy as np

from astraeus.simulation import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)
from astraeus.visualization.plots import plot_synthetic_validation, plot_corner
from astraeus.analysis.fitting import find_best_fit
from astraeus.analysis.error_analysis import run_mcmc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "synthetic_validation.png"


def main() -> None:
    """Run the synthetic hot-Jupiter validation workflow."""

    print("Phase 1: Generating synthetic data...")
    scenario = SyntheticTransitScenario.hot_jupiter()
    light_curve = generate_synthetic_transit_series(scenario)
    output_path = plot_synthetic_validation(
        time_days=light_curve.time_days,
        theoretical_flux=light_curve.theoretical_flux,
        observed_flux=light_curve.observed_flux,
        output_path=OUTPUT_PATH,
    )

    print(f"Synthetic validation plot saved to {output_path}")

    # Phase 2: Data Retrieval
    print("Phase 2: Running data retrieval...")
    time = light_curve.time_days * u.day
    flux = light_curve.observed_flux
    
    signal_level = np.mean(np.abs(light_curve.theoretical_flux))
    noise_std = signal_level / scenario.snr
    flux_err = np.full_like(flux, noise_std)

    fixed_params = {
        "R_star": scenario.stellar_radius,
        "period": scenario.period,
        "semi_major_axis": scenario.semi_major_axis,
        "eccentricity": scenario.eccentricity,
    }

    initial_guess = (0.05, 85.0)

    print("Running initial optimization to find MAP estimate...")
    best_fit_theta, success = find_best_fit(
        initial_guess_theta=initial_guess,
        time=time,
        flux=flux,
        flux_err=flux_err,
        fixed_params=fixed_params,
    )
    
    print(f"Optimization success: {success}")
    print(f"Best fit params: radius_ratio={best_fit_theta[0]:.4f}, inclination={best_fit_theta[1]:.4f}")

    print("Running MCMC to quantify uncertainty...")
    flat_samples, percentiles = run_mcmc(
        best_fit_theta=best_fit_theta,
        time=time,
        flux=flux,
        flux_err=flux_err,
        fixed_params=fixed_params,
        n_walkers=32,
        n_steps=2000,
    )

    corner_output_path = PROJECT_ROOT / "outputs" / "mcmc_corner_plot.png"
    
    print("Generating corner plot...")
    plot_corner(
        flat_samples=flat_samples,
        labels=["Radius Ratio", "Inclination (deg)"],
        true_values=[scenario.radius_ratio, scenario.inclination.to_value(u.deg)],
        output_path=corner_output_path,
    )
    print(f"Corner plot saved to {corner_output_path}")


if __name__ == "__main__":
    main()
