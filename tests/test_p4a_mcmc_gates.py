"""P4-A MCMC convergence gates: acceptance + autocorrelation, fail-closed.

The suite's own evidence: emcee warns `acceptance ~0.53` on the standard
mock config every run, and `test_mcmc.py` only `warnings.warn`s. These
tests pin the gates that replace the warning with a verdict.
"""

import numpy as np
import pytest
from astropy import units as u
from unittest.mock import patch

from astraeus.analysis.error_analysis import (
    MCMCConvergenceError,
    _assess_convergence,
    run_mcmc,
)


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


def _mock_setup():
    period = 3.5 * u.day
    R_star = 1.0 * u.R_sun
    time = np.linspace(0.8, 0.95, 20) * u.day
    true_flux = mock_box_transit(
        time,
        [{"period": period, "R_planet": R_star * 0.1,
          "R_star": R_star, "inclination": 89.9 * u.deg}],
    )
    np.random.seed(42)
    flux = true_flux + np.random.normal(0, 1e-4, size=len(time))
    flux_err = np.full_like(flux, 1e-4)
    fixed = {
        "period": period,
        "semi_major_axis": 10.0 * u.R_sun,
        "eccentricity": 0.0 * u.dimensionless_unscaled,
        "R_star": R_star,
        "u1": 0.0,
        "u2": 0.0,
    }
    return time, flux, flux_err, fixed


@patch("astraeus.analysis.fitting.generate_multi_planet_transit",
       side_effect=mock_box_transit)
def test_convergence_report_shape_and_verdict(mock_transit):
    """Seeded mock run: report carries every gate input and fails honestly."""
    time, flux, flux_err, fixed = _mock_setup()
    flat, pct, acc, report = run_mcmc(
        best_fit_theta=(0.1, 89.9),
        time=time, flux=flux, flux_err=flux_err, fixed_params=fixed,
        param_names=["radius_ratio", "inclination_deg"],
        n_walkers=16, n_steps=500, seed=0,
        return_acceptance=True, return_convergence=True,
    )
    assert set(report) >= {
        "acceptance", "acceptance_ok", "tau", "n_effective_min",
        "effective_ok", "converged", "reasons",
    }
    # Measured on this seeded config: acc ~0.545 (outside [0.2, 0.5]),
    # tau ~[51, 54] over 400 post-burnin steps -> effective ~7 < 50.
    assert report["acceptance"] == pytest.approx(0.545, abs=0.05)
    assert report["acceptance_ok"] is False
    assert report["effective_ok"] is False
    assert report["converged"] is False
    assert len(report["reasons"]) >= 2


@patch("astraeus.analysis.fitting.generate_multi_planet_transit",
       side_effect=mock_box_transit)
def test_require_converged_fails_closed(mock_transit):
    """Unconverged posterior + require_converged = error, never silent numbers."""
    time, flux, flux_err, fixed = _mock_setup()
    with pytest.raises(MCMCConvergenceError):
        run_mcmc(
            best_fit_theta=(0.1, 89.9),
            time=time, flux=flux, flux_err=flux_err, fixed_params=fixed,
            param_names=["radius_ratio", "inclination_deg"],
            n_walkers=16, n_steps=500, seed=0,
            require_converged=True,
        )


@patch("astraeus.analysis.fitting.generate_multi_planet_transit",
       side_effect=mock_box_transit)
def test_legacy_return_shapes_unchanged(mock_transit):
    """Old path intact: default 2-tuple, acceptance 3-tuple, no report."""
    time, flux, flux_err, fixed = _mock_setup()
    assert len(run_mcmc(
        best_fit_theta=(0.1, 89.9),
        time=time, flux=flux, flux_err=flux_err, fixed_params=fixed,
        param_names=["radius_ratio", "inclination_deg"],
        n_walkers=16, n_steps=200, seed=0,
    )) == 2
    out = run_mcmc(
        best_fit_theta=(0.1, 89.9),
        time=time, flux=flux, flux_err=flux_err, fixed_params=fixed,
        param_names=["radius_ratio", "inclination_deg"],
        n_walkers=16, n_steps=200, seed=0,
        return_acceptance=True,
    )
    assert len(out) == 3 and isinstance(out[2], float)


def test_assess_convergence_logic():
    """Pure gate logic, both branches, no sampling cost."""
    ok = _assess_convergence(0.35, [4.0, 5.0], n_post_burnin=400, min_effective=50)
    assert ok["converged"] is True and ok["reasons"] == []
    assert ok["n_effective_min"] == pytest.approx(80.0)

    bad_acc = _assess_convergence(0.6, [4.0, 5.0], n_post_burnin=400, min_effective=50)
    assert bad_acc["converged"] is False and bad_acc["acceptance_ok"] is False

    no_tau = _assess_convergence(0.35, None, n_post_burnin=400, min_effective=50)
    assert no_tau["converged"] is False
    assert any("autocorr" in r for r in no_tau["reasons"])
