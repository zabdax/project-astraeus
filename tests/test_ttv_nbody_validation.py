import pytest
import numpy as np
from unittest.mock import patch

from astraeus.core.nbody_solver import M_EARTH_IN_MSUN, PlanetParams, StabilityResult
from astraeus.analysis.ttv_nbody_validation import (
    estimate_ttv_periodicity,
    estimate_analytic_ttv_amplitude_min,
    validate_ttv_with_nbody
)

def test_periodicity_extraction():
    epochs = list(range(100))
    # TTV super-period of 20 epochs
    ttv = [10.0 * np.sin(2 * np.pi * e / 20.0) for e in epochs]
    
    # known period = 10 days, so TTV period = 200 days
    periodicity = estimate_ttv_periodicity(epochs, ttv, 10.0)
    assert periodicity is not None
    assert 190.0 < periodicity < 210.0

def test_analytic_amplitude():
    # 10 days known, 20 days companion (2:1), 30 Earth masses
    amp = estimate_analytic_ttv_amplitude_min(10.0, 20.0, 30.0 * M_EARTH_IN_MSUN, 1.0)
    assert amp > 0

def test_synthetic_recovery():
    """
    Known truth -> synthetic TTV -> recovery attempt.
    """
    known_period = 10.0
    comp_mass_earth = 100.0
    comp_period = 21.5
    stellar_mass = 1.0
    
    # Derive what TTV signal it produces analytically
    amp = estimate_analytic_ttv_amplitude_min(known_period, comp_period, comp_mass_earth*M_EARTH_IN_MSUN, stellar_mass)
    
    epochs = list(range(20))
    ttv_data = [{"epoch": e, "ttv_residual_min": amp * np.sin(e)} for e in epochs]
    
    known_planet = {
        "period_days": known_period,
        "planet_radius_earth": 2.0
    }
    
    result = validate_ttv_with_nbody(known_planet, ttv_data, stellar_mass)
    
    assert "Plausible stable companions found" in result["conclusion"]
    assert len(result["plausible_companions"]) > 0
    
    best_cand = result["plausible_companions"][0]
    assert best_cand["mass_earth"] > 0
    assert best_cand["period_days"] > 0
    assert best_cand["stability"]["is_stable"]

def test_no_signal_rejection():
    # Flat/noise-only TTV residuals
    epochs = list(range(20))
    ttv_data = [{"epoch": e, "ttv_residual_min": 0.1 * (e % 2 - 0.5)} for e in epochs]
    
    known_planet = {
        "period_days": 10.0,
        "planet_radius_earth": 2.0
    }
    
    result = validate_ttv_with_nbody(known_planet, ttv_data, 1.0)
    assert result["conclusion"] == "TTV consistent with noise, no significant amplitude detected"
    assert len(result["plausible_companions"]) == 0

@patch("astraeus.analysis.ttv_nbody_validation.run_stability_analysis")
def test_unstable_candidate_rejection(mock_run_stability):
    # Mock stability to always return unstable
    mock_run_stability.return_value = StabilityResult(
        is_stable=False,
        survival_time_years=0.1,
        max_eccentricity_drift=1.5,
        termination_reason="collision"
    )
    
    known_period = 10.0
    comp_mass_earth = 100.0
    comp_period = 21.5
    stellar_mass = 1.0
    
    amp = estimate_analytic_ttv_amplitude_min(known_period, comp_period, comp_mass_earth*M_EARTH_IN_MSUN, stellar_mass)
    
    epochs = list(range(20))
    ttv_data = [{"epoch": e, "ttv_residual_min": amp * np.sin(e)} for e in epochs]
    
    known_planet = {
        "period_days": known_period,
        "planet_radius_earth": 2.0
    }
    
    result = validate_ttv_with_nbody(known_planet, ttv_data, stellar_mass)
    
    assert "Analytically plausible companions found, but none were dynamically stable" in result["conclusion"]
    assert len(result["plausible_companions"]) == 0
