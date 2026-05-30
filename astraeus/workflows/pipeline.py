"""Orchestration pipelines for ASTRAEUS tasks."""

from __future__ import annotations

from pathlib import Path
import numpy as np
from astropy import units as u

from astraeus.simulation.synthetic import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)
from astraeus.visualization.plots import plot_synthetic_validation, plot_corner
from astraeus.analysis.optimization import find_best_fit
from astraeus.analysis.error_analysis import run_mcmc


class SyntheticValidationPipeline:
    """Orchestrates the synthetic transit generation, optimization, and MCMC sampling."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.outputs_dir = self.project_root / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def run_generation(self) -> tuple[SyntheticTransitScenario, object]:
        """Generate synthetic data and plot validation."""
        print("Phase 1: Generating synthetic data...")
        scenario = SyntheticTransitScenario.hot_jupiter()
        light_curve = generate_synthetic_transit_series(scenario)
        output_path = self.outputs_dir / "synthetic_validation.png"
        
        saved_path = plot_synthetic_validation(
            time_days=light_curve.time_days,
            theoretical_flux=light_curve.theoretical_flux,
            observed_flux=light_curve.observed_flux,
            output_path=output_path,
        )
        print(f"Synthetic validation plot saved to {saved_path}")
        return scenario, light_curve

    def run_retrieval(
        self,
        scenario: SyntheticTransitScenario,
        light_curve: object,
    ) -> tuple:
        """Run initial optimization to find MAP estimate."""
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
        return best_fit_theta, time, flux, flux_err, fixed_params

    def run_mcmc_analysis(
        self,
        best_fit_theta: tuple[float, ...],
        time: u.Quantity,
        flux: np.ndarray,
        flux_err: np.ndarray,
        fixed_params: dict,
        scenario: SyntheticTransitScenario,
    ) -> None:
        """Run MCMC to quantify uncertainty and generate corner plot."""
        print("Running MCMC to quantify uncertainty...")
        flat_samples, _ = run_mcmc(
            best_fit_theta=best_fit_theta,
            time=time,
            flux=flux,
            flux_err=flux_err,
            fixed_params=fixed_params,
            n_walkers=32,
            n_steps=2000,
        )

        corner_output_path = self.outputs_dir / "mcmc_corner_plot.png"
        
        print("Generating corner plot...")
        plot_corner(
            flat_samples=flat_samples,
            labels=["Radius Ratio", "Inclination (deg)"],
            true_values=[scenario.radius_ratio, scenario.inclination.to_value(u.deg)],
            output_path=corner_output_path,
        )
        print(f"Corner plot saved to {corner_output_path}")

    def execute_full_workflow(self) -> None:
        """Run the complete synthetic validation workflow."""
        scenario, light_curve = self.run_generation()
        best_fit_theta, time, flux, flux_err, fixed_params = self.run_retrieval(
            scenario, light_curve
        )
        self.run_mcmc_analysis(
            best_fit_theta, time, flux, flux_err, fixed_params, scenario
        )
