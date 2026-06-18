import numpy as np
import pytest

from astraeus.core.nbody_solver import (
    G_AU3_MSUN_YR2,
    M_EARTH_IN_MSUN,
    PlanetParams,
    StabilityResult,
    _compute_osculating_eccentricity,
    _hill_radius,
    _keplerian_to_cartesian,
    check_system_stability,
    estimate_mass_from_radius,
    run_stability_analysis,
)


def test_energy_conservation():
    """Test 1 — Two-body energy conservation.
    Single Earth-mass planet on circular orbit at 1 AU around a 1 M_sun star.
    Run for 10,000 steps. Assert energy_relative_error < 1e-6 and is_stable is True.
    """
    planets = [
        PlanetParams(
            mass_msun=M_EARTH_IN_MSUN,
            semi_major_axis_au=1.0,
            eccentricity=0.0,
            initial_phase_rad=0.0,
        )
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=10_000,
    )
    
    assert result.is_stable is True
    assert result.termination_reason == "completed"
    assert result.energy_relative_error < 1e-6


def test_known_stable_system():
    """Test 2 — Known stable system (Jupiter-Saturn analog)."""
    M_jupiter = 317.8 * M_EARTH_IN_MSUN
    M_saturn = 95.2 * M_EARTH_IN_MSUN
    planets = [
        PlanetParams(mass_msun=M_jupiter, semi_major_axis_au=5.2, eccentricity=0.048, initial_phase_rad=0.0),
        PlanetParams(mass_msun=M_saturn, semi_major_axis_au=9.5, eccentricity=0.054, initial_phase_rad=np.pi/4),
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=10_000,
    )
    
    assert result.is_stable is True
    assert result.termination_reason == "completed"


def test_forced_collision():
    """Test 3 — Forced collision (crossing orbits)."""
    planets = [
        PlanetParams(mass_msun=0.001, semi_major_axis_au=1.0, eccentricity=0.0, initial_phase_rad=0.0),
        PlanetParams(mass_msun=0.001, semi_major_axis_au=1.01, eccentricity=0.0, initial_phase_rad=np.pi),
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=50_000,
    )
    
    assert result.is_stable is False
    assert result.termination_reason == "collision"
    assert result.colliding_pair is not None


def test_forced_ejection():
    """Test 4 — Forced ejection.
    A very light planet near a massive one.
    """
    planets = [
        PlanetParams(mass_msun=0.01, semi_major_axis_au=0.5, eccentricity=0.0, initial_phase_rad=0.0),
        PlanetParams(mass_msun=1e-7, semi_major_axis_au=0.52, eccentricity=0.5, initial_phase_rad=np.pi),
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=50_000,
    )
    
    assert result.is_stable is False
    assert result.termination_reason in ["ejection", "collision", "energy_divergence"]


def test_circular_orbit_eccentricity_drift():
    """Test 5 — Circular orbit eccentricity drift ≈ 0."""
    planets = [
        PlanetParams(
            mass_msun=M_EARTH_IN_MSUN,
            semi_major_axis_au=1.0,
            eccentricity=0.0,
            initial_phase_rad=0.0,
        )
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=5_000,
    )
    
    assert result.max_eccentricity_drift < 0.005


def test_estimate_mass_from_radius():
    """Test 6 — estimate_mass_from_radius."""
    mass = estimate_mass_from_radius(1.0)
    assert mass == pytest.approx(M_EARTH_IN_MSUN, rel=0.01)
    
    mass_zero = estimate_mass_from_radius(0.0)
    assert mass_zero == 0.0


def test_check_system_stability_api():
    """Test 7 — check_system_stability dict API."""
    planet_dicts = [
        {
            "mass_msun": M_EARTH_IN_MSUN,
            "semi_major_axis_au": 1.0,
            "eccentricity": 0.0,
            "initial_phase_rad": 0.0,
        }
    ]
    result_dict = check_system_stability(
        stellar_mass_msun=1.0,
        planet_dicts=planet_dicts,
        n_steps=100,
    )
    
    assert isinstance(result_dict, dict)
    assert "is_stable" in result_dict
    assert "survival_time_years" in result_dict
    assert "max_eccentricity_drift" in result_dict
    assert "termination_reason" in result_dict
    assert "colliding_pair" in result_dict
    assert "ejected_body" in result_dict
    assert "final_eccentricities" in result_dict
    assert "energy_relative_error" in result_dict
    assert result_dict["is_stable"] is True


def test_empty_planets():
    """Test 8 — Empty planets."""
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=[],
    )
    assert result.is_stable is True
    assert result.survival_time_years == 0.0
