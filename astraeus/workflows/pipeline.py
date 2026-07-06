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
        param_names = ["radius_ratio", "inclination_deg"]
        best_fit_theta, success = find_best_fit(
            initial_guess_theta=initial_guess,
            time=time,
            flux=flux,
            flux_err=flux_err,
            fixed_params=fixed_params,
            param_names=param_names,
        )
        
        print(f"Optimization success: {success}")
        print(f"Best fit params: radius_ratio={best_fit_theta[0]:.4f}, inclination={best_fit_theta[1]:.4f}")
        return best_fit_theta, time, flux, flux_err, fixed_params, param_names

    def run_mcmc_analysis(
        self,
        best_fit_theta: tuple[float, ...],
        time: u.Quantity,
        flux: np.ndarray,
        flux_err: np.ndarray,
        fixed_params: dict,
        param_names: list[str],
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
            param_names=param_names,
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
        best_fit_theta, time, flux, flux_err, fixed_params, param_names = self.run_retrieval(
            scenario, light_curve
        )
        self.run_mcmc_analysis(
            best_fit_theta, time, flux, flux_err, fixed_params, param_names, scenario
        )

class RealDataPipeline:
    """Orchestrates the retrieval of parameters from real observational data."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.outputs_dir = self.project_root / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def execute_full_workflow(self, target_name: str = "TrES-2b", mission: str = "Kepler", quarter: int = 1) -> None:
        from scipy.signal import savgol_filter
        from astraeus.data.preprocessing import detrend_lightcurve, phase_fold_data
        from astraeus.core.transit_model import generate_model_flux
        from astraeus.visualization.plots import plot_real_retrieval
        
        print(f"Phase 1: Fetching and preprocessing real data for {target_name} (Quarter {quarter})...")
        import lightkurve as lk
        try:
            print(f"Searching MAST for {target_name} Q{quarter} data...")
            search = lk.search_lightcurve(target_name, mission=mission, quarter=quarter)
            if len(search) == 0:
                raise ValueError(f"No data found for {target_name} in Q{quarter}.")
            
            print("Downloading data...")
            lc = search.download()
            lc = lc[lc.quality == 0].remove_nans().normalize()
            # I2 fix (round-2 diagnostic 2026-07-06): convert BKJD/BTJD
            # to BJD full at this ingestion boundary.
            from astraeus.core.time_units import to_bjd
            time_raw = to_bjd(lc.time.value, mission)
            flux_raw = lc.flux.value
        except Exception as e:
            print(f"Error loading data: {e}")
            return
            
        print(f"Loaded {len(time_raw)} raw data points.")
        
        flux_detrended = detrend_lightcurve(time_raw, flux_raw)

        # TrES-2b known parameter assumptions
        period_days = 2.470613
        
        smoothed_flux = savgol_filter(flux_detrended, window_length=101, polyorder=2)
        t0_guess = time_raw[np.argmin(smoothed_flux)]
        print(f"Estimated transit epoch t0: {t0_guess:.4f}")
        
        folded_time, folded_flux = phase_fold_data(
            time_raw, flux_detrended, period_days, t0_guess
        )
        
        out_of_transit_mask = np.abs(folded_time) > 0.1
        noise_std = np.std(folded_flux[out_of_transit_mask])
        folded_flux_err = np.full_like(folded_flux, noise_std)

        print("Phase 2: Setting up MCMC parameter retrieval...")
        time = folded_time * u.day
        
        fixed_params = {
            "R_star": 1.0 * u.R_sun,
            "period": period_days * u.day,
            "semi_major_axis": 0.03556 * u.AU,
            "eccentricity": 0.0 * u.dimensionless_unscaled,
        }

        initial_guess = (0.125, 83.6, 0.4, 0.2)
        param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
        
        print("Running initial optimization to find MAP estimate...")
        best_fit_theta, success = find_best_fit(
            initial_guess_theta=initial_guess,
            time=time,
            flux=folded_flux,
            flux_err=folded_flux_err,
            fixed_params=fixed_params,
            param_names=param_names,
        )
        
        print(f"Optimization success: {success}")
        print(f"MAP Params: Rp/Rs={best_fit_theta[0]:.4f}, Inc={best_fit_theta[1]:.4f}, u1={best_fit_theta[2]:.4f}, u2={best_fit_theta[3]:.4f}")
        
        print("Phase 3: Running MCMC analysis (this may take a minute)...")
        flat_samples, percentiles = run_mcmc(
            best_fit_theta=best_fit_theta,
            time=time,
            flux=folded_flux,
            flux_err=folded_flux_err,
            fixed_params=fixed_params,
            param_names=param_names,
            n_walkers=32,
            n_steps=500,
        )
        
        median_params = percentiles[:, 1]
        print(f"MCMC Median Params: Rp/Rs={median_params[0]:.4f}, Inc={median_params[1]:.4f}, u1={median_params[2]:.4f}, u2={median_params[3]:.4f}")

        print("Phase 4: Generating verification plots...")
        
        # Prepare params to generate model flux
        params_dict = fixed_params.copy()
        for name, val in zip(param_names, median_params):
            params_dict[name] = val
            
        inclination = params_dict.get("inclination_deg", 90.0) * u.deg
        if "inclination" in params_dict:
            inclination = params_dict["inclination"]
        
        theoretical_flux = generate_model_flux(
            time=time,
            period=params_dict["period"],
            semi_major_axis=params_dict["semi_major_axis"],
            eccentricity=params_dict.get("eccentricity", 0.0 * u.dimensionless_unscaled),
            inclination=inclination,
            R_star=params_dict["R_star"],
            R_planet=params_dict["R_star"] * params_dict["radius_ratio"],
            u1=params_dict.get("u1", 0.0),
            u2=params_dict.get("u2", 0.0),
        )
        
        retrieval_plot_path = self.outputs_dir / "real_planet_retrieval.png"
        plot_real_retrieval(
            time=folded_time,
            observed_flux=folded_flux,
            theoretical_flux=theoretical_flux,
            output_path=retrieval_plot_path,
        )
        print(f"Saved retrieval validation plot to {retrieval_plot_path}")
        
        corner_plot_path = self.outputs_dir / "mcmc_corner_plot.png"
        try:
            import corner
            plot_corner(
                flat_samples=flat_samples,
                labels=["Rp/Rs", "Inc (deg)", "u1", "u2"],
                true_values=median_params.tolist(),
                output_path=corner_plot_path,
            )
            print(f"Saved corner plot to {corner_plot_path}")
        except ImportError:
            print("The 'corner' package is not installed; skipping corner plot generation.")

