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
    run_stability_integration,
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
    """Test 3 — Forced close encounter (grazing orbits).

    2026-08-21 audit note: with dt = min_period/100 the Hill-zone of this
    configuration is traversed in LESS than one timestep, so whether the
    encounter registers as "collision" (Hill-zone contact sampled) or
    "energy_divergence" (unresolved encounter blows up the energy check
    first) depends on chaotic trajectory detail — it flipped when the
    star–planet softening fix (audit M1) changed the trajectory at the
    1e-4 level. Both verdicts mean "system destroyed by the encounter";
    what this test really guards is that the solver terminates unstably
    with finite diagnostics and never silently reports stability or a
    NaN leak. test_collision_detection_fires_deterministically below locks
    the collision machinery itself.
    """
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
    assert result.termination_reason in ("collision", "energy_divergence"), (
        f"close-encounter system terminated as {result.termination_reason!r}"
    )
    if result.termination_reason == "collision":
        assert result.colliding_pair is not None


def test_collision_detection_fires_deterministically():
    """Bodies initialised inside each other's mutual Hill zone must be
    flagged as colliding on the first step — deterministic lock for the
    collision machinery (pair indices, unstable verdict, finite payload).
    """
    planets = [
        PlanetParams(mass_msun=0.001, semi_major_axis_au=1.0, eccentricity=0.0, initial_phase_rad=0.0),
        PlanetParams(mass_msun=0.001, semi_major_axis_au=1.01, eccentricity=0.0, initial_phase_rad=0.05),
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0,
        planets=planets,
        n_steps=1_000,
    )

    assert result.is_stable is False
    assert result.termination_reason == "collision"
    assert result.colliding_pair == (0, 1)
    assert np.all(np.isfinite(result.final_eccentricities))
    assert np.isfinite(result.energy_relative_error)


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


# ---------------------------------------------------------------------------
# Tests 9-11: Kepler-90b N-body scenarios via the low-level
# run_stability_integration entry point. Ported from
# scripts/manual_tests/test_engine.py (Bucket 7 handoff) per the
# consolidation directive in the bucket5 plan. The original script
# was a single driver that printed pass/fail banners and exited via
# sys.exit(0 if all_passed else 1) — that pattern kills pytest, so
# each scenario is wrapped in its own test function with explicit
# assertions.
# ---------------------------------------------------------------------------


def test_earth_sun_circular_via_state_vectors():
    """Earth-Sun analog at 1 AU, 1000 steps at dt=0.001 yr; must survive."""
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    velocities = np.array([[0.0, 0.0, 0.0], [0.0, 2.0 * np.pi, 0.0]])
    masses = np.array([1.0, 3.0e-6])
    result = run_stability_integration(
        positions, velocities, masses, n_steps=1000, dt=0.001
    )
    assert result.is_stable
    assert result.survival_time_years > 0.99


def test_kepler90b_high_resolution_stability():
    """Kepler-90b at a=0.074 AU, dt=1e-5 yr, 5000 steps; must be stable."""
    positions = np.array([[0.0, 0.0, 0.0], [0.074, 0.0, 0.0]])
    velocities = np.array([[0.0, 0.0, 0.0], [0.0, 25.32, 0.0]])
    masses = np.array([1.2, 9.0e-6])
    result = run_stability_integration(
        positions, velocities, masses, n_steps=5000, dt=1e-5
    )
    assert result.is_stable


def test_kepler90b_oversized_dt_forces_blowup():
    """Kepler-90b with dt=0.01 yr (100x oversized) must fail with a
    recognized termination reason within 1000 steps."""
    positions = np.array([[0.0, 0.0, 0.0], [0.074, 0.0, 0.0]])
    velocities = np.array([[0.0, 0.0, 0.0], [0.0, 25.32, 0.0]])
    masses = np.array([1.2, 9.0e-6])
    result = run_stability_integration(
        positions, velocities, masses, n_steps=1000, dt=0.01
    )
    assert not result.is_stable
    assert result.termination_reason in (
        "Physical Boundary Breach",
        "ejection",
        "energy_divergence",
        "collision",
    )
