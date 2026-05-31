import numpy as np
import pytest
from astropy import units as u
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from astraeus.core.transit_model import generate_model_flux, generate_multi_planet_transit
from astraeus.analysis.error_analysis import run_mcmc

def test_ui_dynamic_expansion():
    """
    Programmatically add 3 planets in the simulator.
    Assert that the UI renders 3 distinct sets of sliders.
    """
    at = AppTest.from_file("app.py", default_timeout=120)
    at.run()
    
    # The default state in the Simulator starts with 1 planet.
    # We click "Add Planet" twice to get 3 total planets.
    for _ in range(2):
        add_btn = next((b for b in at.button if b.label == "Add Planet"), None)
        assert add_btn is not None, "Add Planet button not found in Simulator"
        add_btn.click().run()
        
    # Count the number of 'Radius Ratio' sliders to verify 3 distinct planet controls exist
    radius_sliders = [s for s in at.slider if "Radius Ratio" in s.label]
    assert len(radius_sliders) == 3, f"Expected 3 distinct Radius Ratio sliders, got {len(radius_sliders)}"


def test_physics_summation():
    """
    Assert that generate_multi_planet_transit returns a flux model 
    that is the cumulative product of 3 individual transit profiles.
    """
    time = np.linspace(-0.2, 0.2, 100) * u.day
    
    p1 = {
        "period": 1.0 * u.day, "semi_major_axis": 10.0 * u.R_sun, 
        "eccentricity": 0.0 * u.dimensionless_unscaled, "inclination": 90.0 * u.deg, 
        "R_star": 1.0 * u.R_sun, "R_planet": 0.1 * u.R_sun, "u1": 0.0, "u2": 0.0
    }
    p2 = {
        "period": 1.5 * u.day, "semi_major_axis": 13.0 * u.R_sun, 
        "eccentricity": 0.0 * u.dimensionless_unscaled, "inclination": 89.0 * u.deg, 
        "R_star": 1.0 * u.R_sun, "R_planet": 0.05 * u.R_sun, "u1": 0.0, "u2": 0.0
    }
    p3 = {
        "period": 2.0 * u.day, "semi_major_axis": 16.0 * u.R_sun, 
        "eccentricity": 0.0 * u.dimensionless_unscaled, "inclination": 88.0 * u.deg, 
        "R_star": 1.0 * u.R_sun, "R_planet": 0.02 * u.R_sun, "u1": 0.0, "u2": 0.0
    }
    
    # Calculate individually
    flux1 = generate_model_flux(time=time, **p1)
    flux2 = generate_model_flux(time=time, **p2)
    flux3 = generate_model_flux(time=time, **p3)
    
    # The mathematically correct accumulation of relative transit drops is multiplicative
    expected_total = flux1 * flux2 * flux3
    
    # Calculate jointly via the backend scaling engine
    actual_total = generate_multi_planet_transit(time, [p1, p2, p3])
    
    # Assert bit-for-bit (or nearly) identical arrays
    np.testing.assert_allclose(actual_total, expected_total, err_msg="Multi-planet flux is not the cumulative product of individual transits")


def mock_multi_transit(time, planet_list):
    """Fast mock for MCMC to prevent slow integration during tests."""
    return np.ones(len(time))

@patch("astraeus.analysis.fitting.generate_multi_planet_transit", side_effect=mock_multi_transit)
def test_regression_mcmc(mock_transit):
    """
    Add 1 planet, run MCMC, verify convergence. 
    Then add a 2nd planet, run MCMC, and ensure the code doesn't raise DimensionMismatchError.
    """
    time = np.linspace(-0.1, 0.1, 50) * u.day
    flux = np.ones(50)
    flux_err = np.full(50, 1e-4)
    
    # --- 1 Planet MCMC ---
    fixed_params_1 = {
        "period": 1.0 * u.day,
        "semi_major_axis": 10.0 * u.R_sun,
        "eccentricity": 0.0 * u.dimensionless_unscaled,
        "R_star": 1.0 * u.R_sun,
    }
    param_names_1 = ["radius_ratio", "inclination_deg"]
    init_guess_1 = (0.1, 90.0)
    
    # Verify convergence / no crash on single body system
    samples1, perc1 = run_mcmc(
        best_fit_theta=init_guess_1, time=time, flux=flux, flux_err=flux_err, 
        fixed_params=fixed_params_1, param_names=param_names_1, 
        n_walkers=10, n_steps=50
    )
    assert samples1 is not None
    assert samples1.shape[1] == 2, "Expected 2 parameters retrieved for 1 planet"
    
    # --- 2 Planet MCMC (Regression Test) ---
    fixed_params_2 = {
        "planets": [
            {
                "period": 1.0 * u.day,
                "semi_major_axis": 10.0 * u.R_sun,
                "eccentricity": 0.0 * u.dimensionless_unscaled,
            },
            {
                "period": 2.0 * u.day,
                "semi_major_axis": 15.0 * u.R_sun,
                "eccentricity": 0.0 * u.dimensionless_unscaled,
            }
        ],
        "R_star": 1.0 * u.R_sun,
    }
    param_names_2 = [
        "planet_0_radius_ratio", "planet_0_inclination_deg", 
        "planet_1_radius_ratio", "planet_1_inclination_deg"
    ]
    init_guess_2 = (0.1, 90.0, 0.05, 89.0)
    
    try:
        samples2, perc2 = run_mcmc(
            best_fit_theta=init_guess_2, time=time, flux=flux, flux_err=flux_err, 
            fixed_params=fixed_params_2, param_names=param_names_2, 
            n_walkers=10, n_steps=50
        )
    except Exception as e:
        pytest.fail(f"Adding 2nd planet raised an exception during MCMC (Regression): {e}")
        
    assert samples2 is not None
    assert samples2.shape[1] == 4, "Expected 4 parameters retrieved for 2 planets"
