import warnings
import numpy as np
from astropy import units as u
from unittest.mock import patch

from astraeus.analysis.error_analysis import run_mcmc

def mock_generate_multi_planet_transit(time, planet_list):
    """A fast mock forward model for MCMC testing.
    Uses a simple box transit where depth depends on inclination to create a gradient.
    """
    flux = np.ones(len(time))
    for p in planet_list:
        rp_rs = (p["R_planet"] / p["R_star"]).to_value(u.dimensionless_unscaled)
        inc = p["inclination"].to_value(u.deg)
        # Simple depth that depends on inclination (peaks at 90)
        depth = (rp_rs ** 2) * max(0, 1 - ((90.0 - inc) / 5.0)**2)
        center = (p["period"] / 4).to_value(u.day)
        in_transit = np.abs(time.to_value(u.day) - center) < 0.05
        flux[in_transit] -= depth
    return flux

@patch("astraeus.analysis.fitting.generate_multi_planet_transit", side_effect=mock_generate_multi_planet_transit)
def test_mcmc_retrieval(mock_transit):
    """Test MCMC retrieval on a perfectly known synthetic transit system."""
    
    # 1. Setup: Generate a perfectly known system
    period = 3.5 * u.day
    rp_rs = 0.1
    R_star = 1.0 * u.R_sun
    semi_major_axis = 10.0 * u.R_sun
    
    true_inclination_deg = 89.9
    inclination = true_inclination_deg * u.deg
    
    time = np.linspace(0.8, 0.95, 20) * u.day
    
    # Generate theoretical flux using the mock model so MCMC fits perfectly
    true_flux = mock_generate_multi_planet_transit(
        time,
        [{
            "period": period,
            "R_planet": R_star * rp_rs,
            "R_star": R_star,
            "inclination": inclination
        }]
    )
    
    # Add noise
    np.random.seed(42)
    noise_std = 1e-4
    flux = true_flux + np.random.normal(0, noise_std, size=len(time))
    flux_err = np.full_like(flux, noise_std)
    
    fixed_params = {
        "period": period,
        "semi_major_axis": semi_major_axis,
        "eccentricity": 0.0 * u.dimensionless_unscaled,
        "R_star": R_star,
        "u1": 0.0,
        "u2": 0.0,
    }
    
    param_names = ["radius_ratio", "inclination_deg"]
    initial_guess = (rp_rs, true_inclination_deg)
    
    # 2. Execution: Run MCMC for 500 steps
    flat_samples, percentiles, acc_frac = run_mcmc(
        best_fit_theta=initial_guess,
        time=time,
        flux=flux,
        flux_err=flux_err,
        fixed_params=fixed_params,
        param_names=param_names,
        n_walkers=16,
        n_steps=500,
        return_acceptance=True,
    )
    
    # 3. Verification: Retrieved parameters are within 5% of Ground Truth
    retrieved_rp_rs = percentiles[0, 1]  # Median
    retrieved_inc = percentiles[1, 1]
    
    assert np.isclose(retrieved_rp_rs, rp_rs, rtol=0.05), \
        f"Retrieved Rp/Rs {retrieved_rp_rs:.4f} is not within 5% of true {rp_rs}"
        
    assert np.isclose(retrieved_inc, true_inclination_deg, rtol=0.05), \
        f"Retrieved inclination {retrieved_inc:.2f} is not within 5% of true {true_inclination_deg}"
        
    # 4. Convergence: Check the acceptance fraction
    if not (0.2 <= acc_frac <= 0.5):
        warnings.warn(
            f"MCMC acceptance fraction is {acc_frac:.3f}, which is poorly tuned "
            "(should be between 0.2 and 0.5). Consider adjusting step sizes or priors."
        )
