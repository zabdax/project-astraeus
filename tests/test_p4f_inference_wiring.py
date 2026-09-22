"""P4-F inference wiring: Candidate -> MCMC, gated by P4-A verdicts.

The pipeline has never run inference against a real detected candidate:
period and semi-major axis were hardcoded/config constants. These tests
pin the bridge that closes the four gaps (period, epoch, a, folded
data provenance) plus the gate plumbing through run_retrieval.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from astropy import units as u
from unittest.mock import patch

from astraeus.analysis.inference import (
    candidate_to_mcmc_config,
    kepler_semi_major_axis_au,
    run_candidate_inference,
)


def test_kepler_semi_major_axis_earth_sun():
    assert kepler_semi_major_axis_au(365.25, 1.0) == pytest.approx(1.0, rel=1e-9)


def test_kepler_semi_major_axis_hot_jupiter():
    # P = 3.5 d around 1 Msun -> a ~ 0.045 AU.
    assert kepler_semi_major_axis_au(3.5, 1.0) == pytest.approx(0.0451, abs=1e-3)


def test_bridge_mapping_legacy_dict():
    candidate = {
        "period_days": 3.5,
        "t0_bjd": 2455000.5,
        "depth": 0.01,
        "stellar_radius": 1.0,
    }
    stellar = {"st_mass": 1.0, "st_teff": 5778.0}
    config = candidate_to_mcmc_config(candidate, stellar, n_steps=200, n_walkers=16, seed=7)
    assert config.period_days == pytest.approx(3.5)
    assert config.transit_epoch == pytest.approx(2455000.5)
    assert config.semi_major_axis_au == pytest.approx(0.0451, abs=1e-3)
    assert config.eccentricity == pytest.approx(0.0)
    assert config.radius_ratio_guess == pytest.approx(0.1)
    assert config.stellar_radius_rsun == pytest.approx(1.0)
    # P4-D provenance: guesses come from resolve(), not literals.
    from astraeus.core.limb_darkening import resolve

    u1, u2 = resolve(st_teff=5778.0).as_tuple()
    assert (config.u1_guess, config.u2_guess) == pytest.approx((u1, u2))
    assert config.seed == 7


def test_bridge_accepts_attribute_candidates_and_aliases():
    candidate = SimpleNamespace(
        period=2.0, t0=10.0, transit_depth=0.04, stellar_radius=0.9,
    )
    config = candidate_to_mcmc_config(candidate, {"st_mass": 0.9})
    assert config.period_days == pytest.approx(2.0)
    assert config.radius_ratio_guess == pytest.approx(0.2)
    assert config.semi_major_axis_au == pytest.approx(
        kepler_semi_major_axis_au(2.0, 0.9)
    )


def test_bridge_rejects_missing_period():
    with pytest.raises(ValueError, match="period"):
        candidate_to_mcmc_config({"depth": 0.01}, {})


def _tiny_arrays():
    time = np.linspace(0.8, 0.95, 20)
    flux = np.ones_like(time)
    flux[(np.abs(time - 0.875) < 0.05)] -= 0.01
    return time, flux


def test_retrieval_forwards_gates_to_sampler():
    """run_retrieval threads P4-A flags into run_mcmc and carries the report."""
    from astraeus.dashboard.services import mcmc_retrieval as mr

    time, flux = _tiny_arrays()
    canned = {"converged": True, "reasons": []}
    canned_pct = np.array([
        [0.09, 0.1, 0.11],
        [89.4, 89.5, 89.6],
        [0.09, 0.1, 0.11],
        [0.29, 0.3, 0.31],
    ])
    with patch.object(
        mr, "run_mcmc",
        return_value=(np.zeros((10, 4)), canned_pct, 0.35, canned),
    ) as mocked, patch.object(
        mr, "find_best_fit",
        return_value=((0.1, 89.5, 0.1, 0.3), True),
    ):
        config = mr.MCMCConfig(
            period_days=3.5, transit_epoch=0.875, stellar_radius_rsun=1.0,
            semi_major_axis_au=0.045, eccentricity=0.0,
            radius_ratio_guess=0.1, inclination_degrees_guess=89.5,
            u1_guess=0.1, u2_guess=0.3, n_steps=50, n_walkers=8,
            seed=7, require_converged=True,
        )
        result = mr.run_retrieval(time, flux, config)
    assert mocked.call_count == 1
    kwargs = mocked.call_args.kwargs
    assert kwargs["seed"] == 7
    assert kwargs["require_converged"] is True
    assert kwargs["return_convergence"] is True
    assert result.convergence == canned


def mock_box_transit(time, planet_list):
    flux = np.ones(len(time))
    for p in planet_list:
        rp_rs = (p["R_planet"] / p["R_star"]).to_value(u.dimensionless_unscaled)
        inc = p["inclination"].to_value(u.deg)
        depth = (rp_rs ** 2) * max(0, 1 - ((90.0 - inc) / 5.0) ** 2)
        center = (p["period"] / 4).to_value(u.day)
        in_transit = np.abs(time.to_value(u.day) - center) < 0.05
        flux[in_transit] -= depth
    return flux


@patch("astraeus.analysis.fitting.generate_multi_planet_transit",
       side_effect=mock_box_transit)
def test_candidate_inference_end_to_end_small(mock_transit):
    """Bridge -> retrieval -> posterior + convergence report, all real."""
    period = 3.5 * u.day
    R_star = 1.0 * u.R_sun
    time_q = np.linspace(0.8, 0.95, 20) * u.day
    true_flux = mock_box_transit(
        time_q,
        [{"period": period, "R_planet": R_star * 0.1,
          "R_star": R_star, "inclination": 89.9 * u.deg}],
    )
    np.random.seed(9)
    flux = true_flux + np.random.normal(0, 1e-4, size=len(time_q))
    candidate = {"period_days": 3.5, "t0": 0.875, "depth": 0.01,
                 "stellar_radius": 1.0}
    result = run_candidate_inference(
        np.asarray(time_q.value), flux,
        candidate, {"st_mass": 1.0, "st_teff": 5778.0},
        n_steps=200, n_walkers=16, seed=0,
    )
    assert result.percentiles.shape == (4, 3)
    assert set(result.convergence) >= {"converged", "reasons", "acceptance"}
    assert isinstance(result.convergence["converged"], bool)
