"""Integration script for real exoplanet parameter retrieval (TrES-2b)."""

import sys
from pathlib import Path
import numpy as np
from astropy import units as u
from scipy.signal import savgol_filter

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from astraeus.data.loader import load_nasa_lightcurve
from astraeus.data.preprocessing import detrend_lightcurve, phase_fold_data
from astraeus.analysis.optimization import find_best_fit
from astraeus.analysis.error_analysis import run_mcmc
from astraeus.visualization.plots import plot_real_retrieval, plot_corner
from astraeus.core.orbital_models import calculate_orbital_position
from astraeus.core.transit_model import calculate_sky_separation, generate_geometric_transit

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def generate_model_flux(
    theta: tuple[float, ...],
    time: u.Quantity,
    fixed_params: dict,
) -> np.ndarray:
    """Generate theoretical flux for the given parameters."""
    radius_ratio, inclination_deg, u1, u2 = theta

    R_star = fixed_params["R_star"]
    period = fixed_params["period"]
    semi_major_axis = fixed_params["semi_major_axis"]
    eccentricity = fixed_params["eccentricity"]

    R_planet = R_star * radius_ratio
    inclination = inclination_deg * u.deg

    x, y, z = calculate_orbital_position(
        time=time,
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
    )

    separation = calculate_sky_separation(x, y, z)

    flux_drop_quantity = generate_geometric_transit(
        separation=separation,
        R_star=R_star,
        R_planet=R_planet,
        u1=u1,
        u2=u2,
    )
    flux_drop = flux_drop_quantity.to_value(u.dimensionless_unscaled)

    z_values = z.to_value(semi_major_axis.unit)
    flux_drop[z_values < 0] = 0.0

    return 1.0 - flux_drop

def main() -> None:
    """Run full parameter retrieval on TrES-2b."""
    print("Phase 1: Fetching and preprocessing real data for TrES-2b...")
    try:
        time_raw, flux_raw, flux_err_raw = load_nasa_lightcurve("TrES-2b", mission="Kepler")
    except ValueError as e:
        print(f"Error loading data: {e}")
        return
        
    print(f"Loaded {len(time_raw)} raw data points.")
    
    # Detrend data
    flux_detrended = detrend_lightcurve(time_raw, flux_raw)

    # Known parameters for TrES-2b
    period_days = 2.470613
    
    # We estimate t0 by finding the minimum flux in a smoothed curve
    smoothed_flux = savgol_filter(flux_detrended, window_length=101, polyorder=2)
    t0_guess = time_raw[np.argmin(smoothed_flux)]
    
    print(f"Estimated transit epoch t0: {t0_guess:.4f}")
    
    # Phase fold data
    folded_time, folded_flux = phase_fold_data(
        time_raw, flux_detrended, period_days, t0_guess
    )
    
    # Assign error (approximate based on out-of-transit scatter)
    out_of_transit_mask = np.abs(folded_time) > 0.1
    noise_std = np.std(folded_flux[out_of_transit_mask])
    folded_flux_err = np.full_like(folded_flux, noise_std)

    print("Phase 2: Setting up MCMC parameter retrieval...")
    time = folded_time * u.day
    
    # TrES-2 physical parameters (approximate)
    fixed_params = {
        "R_star": 1.0 * u.R_sun,
        "period": period_days * u.day,
        "semi_major_axis": 0.03556 * u.AU,
        "eccentricity": 0.0,
    }

    # Initial guess for the 4 free parameters
    # [Radius Ratio, Inclination, u1, u2]
    initial_guess = (0.125, 83.6, 0.4, 0.2)
    
    print("Running initial optimization to find MAP estimate...")
    best_fit_theta, success = find_best_fit(
        initial_guess_theta=initial_guess,
        time=time,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
    )
    
    print(f"Optimization success: {success}")
    print(f"MAP Params: Rp/Rs={best_fit_theta[0]:.4f}, Inc={best_fit_theta[1]:.4f}, u1={best_fit_theta[2]:.4f}, u2={best_fit_theta[3]:.4f}")
    
    print("Phase 3: Running MCMC analysis (this may take a minute)...")
    # Using small step count for speed in this demonstration script
    flat_samples, percentiles = run_mcmc(
        best_fit_theta=best_fit_theta,
        time=time,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
        n_walkers=32,
        n_steps=500,
    )
    
    median_params = percentiles[:, 1]
    print(f"MCMC Median Params: Rp/Rs={median_params[0]:.4f}, Inc={median_params[1]:.4f}, u1={median_params[2]:.4f}, u2={median_params[3]:.4f}")

    print("Phase 4: Generating verification plots...")
    outputs_dir = PROJECT_ROOT / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate theoretical flux using MCMC median parameters
    theoretical_flux = generate_model_flux(tuple(median_params), time, fixed_params)
    
    # Plot final retrieval validation
    retrieval_plot_path = outputs_dir / "real_planet_retrieval.png"
    plot_real_retrieval(
        time=folded_time,
        observed_flux=folded_flux,
        theoretical_flux=theoretical_flux,
        output_path=retrieval_plot_path,
    )
    print(f"Saved retrieval validation plot to {retrieval_plot_path}")
    
    # Corner plot
    corner_plot_path = outputs_dir / "mcmc_corner_plot.png"
    
    # Try importing corner to generate the plot, handled gracefully if absent
    try:
        import corner
        plot_corner(
            flat_samples=flat_samples,
            labels=["Rp/Rs", "Inc (deg)", "u1", "u2"],
            true_values=median_params.tolist(), # using median as truths for reference
            output_path=corner_plot_path,
        )
        print(f"Saved corner plot to {corner_plot_path}")
    except ImportError:
        print("The 'corner' package is not installed; skipping corner plot generation.")
        print("To generate it, run: pip install corner")

if __name__ == "__main__":
    main()
