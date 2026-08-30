"""Regression countermeasures for the 2026-08-21 physics/analysis audit fixes.

Each test maps to one audit-fix ID (M1..M15) from the verified-bug audit.
See AUDIT_LOGBOOK.md and the fix comments in the touched modules.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from astropy import units as u

from astraeus.analysis.error_analysis import run_mcmc
from astraeus.analysis.fitting import log_likelihood, log_probability
from astraeus.analysis.logging import ExperimentLedger, save_experiment_log
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.reporting import generate_completeness_report
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.analysis.ttv_nbody_validation import estimate_analytic_ttv_amplitude_min
from astraeus.core.nbody_solver import M_EARTH_IN_MSUN, PlanetParams, run_stability_analysis
from astraeus.core.transit_model import generate_model_flux
from astraeus.data.loader import universal_load_lightcurve
from astraeus.visualization.plots import _heatmap_grid, plot_completeness_map


# ===========================================================================
# Audit fix M1 — pair-dependent gravitational softening
# ===========================================================================
def test_compact_single_planet_orbit_is_stable():
    """Single planet e=0, a=0.05 AU must complete: unsoftened star-planet
    gravity restores the Keplerian dynamics the ICs assume (audit fix M1)."""
    planets = [
        PlanetParams(
            mass_msun=M_EARTH_IN_MSUN,
            semi_major_axis_au=0.05,
            eccentricity=0.0,
            initial_phase_rad=0.0,
        )
    ]
    result = run_stability_analysis(
        stellar_mass_msun=1.0, planets=planets, n_steps=50_000
    )
    assert result.is_stable is True
    assert result.termination_reason == "completed"
    assert result.energy_relative_error < 1e-6
    # Eccentricity drift diagnostics must be meaningful again for compact
    # orbits (softening no longer pollutes the osculating elements).
    assert result.max_eccentricity_drift < 0.005


def test_chaos_vector_b1_coincident_planets_still_flagged_unstable():
    """The planet-planet softening must survive: run the actual chaos-suite
    vector B1 (two coincident planets -> unstable, finite diagnostics)."""
    import test_chaos_integration_suite as chaos

    chaos.vector_b1_sub_epsilon_collision()


# ===========================================================================
# Audit fix M2 — scalar-time generate_model_flux
# ===========================================================================
def test_generate_model_flux_accepts_scalar_time():
    kw = dict(
        period=1.0 * u.day,
        semi_major_axis=0.05 * u.AU,
        eccentricity=0.0 * u.dimensionless_unscaled,
        inclination=90.0 * u.deg,
        R_star=1.0 * u.R_sun,
        R_planet=0.1 * u.R_sun,
    )
    times = np.array([-0.25, 0.0, 0.25]) * u.day
    flux_arr = generate_model_flux(times, **kw)
    flux_scalar = generate_model_flux(-0.25 * u.day, **kw)

    # Scalar input must not raise and must match the array call's element.
    assert np.ndim(flux_scalar) == 0
    assert np.isclose(float(flux_scalar), float(flux_arr[0]))

    # The z<0 branch (np.where) must still zero the flux drop: at least one
    # sample off the near side of the orbit returns exactly 1.0.
    assert np.any(np.asarray(flux_arr) == 1.0)


# ===========================================================================
# Audit fixes M3 + M4 — Quantity coercion and free-parameter precedence
# ===========================================================================
_BASE_FIXED = {
    "period": 2.0 * u.day,
    "semi_major_axis": 0.05 * u.AU,
    "R_star": 1.0 * u.R_sun,
    "u1": 0.0,
    "u2": 0.0,
}
_FIT_TIME = np.linspace(0.0, 2.0, 200) * u.day
_FIT_FLUX = np.ones(200)
_FIT_FLUX_ERR = np.full(200, 1e-3)


def test_log_likelihood_accepts_eccentricity_free_parameter():
    """A raw sampled eccentricity float must be coerced to a Quantity, not
    raise TypeError (audit fix M3)."""
    param_names = ["radius_ratio", "inclination_deg", "eccentricity"]
    theta = (0.1, 89.0, 0.05)
    ll = log_likelihood(theta, _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, _BASE_FIXED, param_names)
    assert np.isfinite(ll) and ll > -np.inf

    lp = log_probability(theta, _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, _BASE_FIXED, param_names)
    assert np.isfinite(lp) and lp > -np.inf


def test_fitted_radius_ratio_overrides_fixed_r_planet():
    """A fitted radius_ratio must win over a fixed R_planet twin, and both
    twins fixed statically is an error (audit fix M4)."""
    ll_plain = log_likelihood(
        (0.1,), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, _BASE_FIXED, ["radius_ratio"]
    )
    fixed_with_rp = {**_BASE_FIXED, "R_planet": 0.5 * u.R_sun}
    ll_override = log_likelihood(
        (0.1,), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, fixed_with_rp, ["radius_ratio"]
    )
    # The fixed (wrong) R_planet must be ignored in favour of the fit.
    assert ll_override == ll_plain

    # Same precedence for inclination_deg over a fixed 'inclination' twin.
    fixed_with_inc = {**_BASE_FIXED, "inclination": 80.0 * u.deg}
    ll_inc_plain = log_likelihood(
        (0.1, 89.0), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, _BASE_FIXED,
        ["radius_ratio", "inclination_deg"],
    )
    ll_inc_override = log_likelihood(
        (0.1, 89.0), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, fixed_with_inc,
        ["radius_ratio", "inclination_deg"],
    )
    assert ll_inc_override == ll_inc_plain

    # Both twins fixed statically (neither fitted) is ambiguous config.
    with pytest.raises(ValueError, match="radius_ratio"):
        log_likelihood(
            (0.0,), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR,
            {**_BASE_FIXED, "radius_ratio": 0.3, "R_planet": 0.5 * u.R_sun},
            ["u1"],
        )
    with pytest.raises(ValueError, match="inclination"):
        log_likelihood(
            (0.0,), _FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR,
            {**_BASE_FIXED, "inclination_deg": 90.0, "inclination": 80.0 * u.deg},
            ["u1"],
        )


# ===========================================================================
# Audit fix M5 — TSM undefined for R >= 10 R_Earth
# ===========================================================================
def _depth_for_radius_earth(radius_earth: float) -> float:
    return (radius_earth / 109.2) ** 2


def test_tsm_undefined_for_giant_planets():
    giant = PhysicalPropertiesEngine.derive(
        3.0, _depth_for_radius_earth(11.0), 1.0, 5800.0, 1.0, 10.0
    )
    assert giant["planet_radius_earth"] >= 10.0
    assert giant["jwst_tsm_score"] == 0.0

    subgiant = PhysicalPropertiesEngine.derive(
        3.0, _depth_for_radius_earth(5.0), 1.0, 5800.0, 1.0, 10.0
    )
    assert subgiant["jwst_tsm_score"] > 0.0


# ===========================================================================
# Audit fix M6 — identical-period TTV amplitude guard
# ===========================================================================
def test_analytic_ttv_amplitude_identical_periods_is_zero():
    amp = estimate_analytic_ttv_amplitude_min(10.0, 10.0, 30.0 * M_EARTH_IN_MSUN, 1.0)
    assert amp == 0.0
    # Non-identical periods still produce a positive amplitude.
    assert estimate_analytic_ttv_amplitude_min(10.0, 20.0, 30.0 * M_EARTH_IN_MSUN, 1.0) > 0.0


# ===========================================================================
# Audit fix M7 — TTV epoch dip-significance gate + logged exceptions
# ===========================================================================
def test_ttv_analyzer_rejects_gap_covered_epochs():
    period, t0, duration = 10.0, 5.0, 0.1
    time = np.arange(0.0, 40.0, 0.001)
    rng = np.random.default_rng(7)
    flux = 1.0 + rng.normal(0.0, 1e-4, size=time.size)
    # Inject four real box transits (depth 0.01 >> 3 sigma of the noise).
    for k in range(4):
        t_calc = t0 + k * period
        flux[np.abs(time - t_calc) < 0.02] = 0.99

    ttv_data = TTVAnalyzer.calculate(time, flux, period, t0, duration)
    epochs = [d["epoch"] for d in ttv_data]
    # Only the genuine transits survive; noise-only windows (which would
    # previously record phantom residuals) are rejected.
    assert sorted(epochs) == [0, 1, 2, 3]


def test_ttv_analyzer_logs_fatal_input_errors(caplog):
    with caplog.at_level("WARNING", logger="astraeus.analysis.ttv_analysis"):
        result = TTVAnalyzer.calculate(np.arange(10.0), None, 1.0, 0.5, 0.1)
    assert result == []
    assert any("TTV analysis aborted" in r.message for r in caplog.records)


# ===========================================================================
# Audit fix M8 — completeness report worst/best cells skip NaN
# ===========================================================================
def _fake_sweep_result(recovery_rate: np.ndarray) -> tuple:
    n_p, n_d, n_s = recovery_rate.shape
    nan_like = np.full_like(recovery_rate, np.nan)
    result = SimpleNamespace(
        config=SimpleNamespace(use_full_pipeline=False, n_injections=5),
        periods_days=np.linspace(1.0, 5.0, n_p),
        radius_ratios=np.linspace(0.02, 0.1, n_d),
        snrs=np.array([10.0] * n_s),
        recovery_rate=recovery_rate,
        period_err_median=nan_like,
        period_err_std=nan_like,
        depth_err_median=nan_like,
        depth_err_std=nan_like,
        n_recovered=np.zeros_like(recovery_rate, dtype=int),
        cell_runtime_seconds=np.zeros_like(recovery_rate),
        total_runtime_seconds=1.0,
        cache_hits=0,
        cache_misses=0,
        shape=(n_p, n_d, n_s),
    )
    config = SimpleNamespace(
        use_full_pipeline=False,
        period_min_days=1.0,
        period_max_days=5.0,
        period_count=n_p,
        radius_ratio_min=0.02,
        radius_ratio_max=0.1,
        radius_ratio_count=n_d,
        snr_values=[10.0] * n_s,
        n_injections=5,
        duration_days=90.0,
        samples=100,
    )
    return result, config


def test_completeness_report_worst_best_skip_nan_cells():
    rate = np.array(
        [[[0.5], [0.2], [0.9]], [[0.8], [np.nan], [0.3]]], dtype=float
    )
    result, config = _fake_sweep_result(rate)
    report = generate_completeness_report(result, config, {})

    worst = report["summary_stats"]["worst_performing_cell"]
    best = report["summary_stats"]["best_performing_cell"]
    # Raw argmin/argmax would land on the NaN cell (flat index 4); the fix
    # selects among finite entries only.
    assert np.isfinite(worst["recovery_rate"]) and worst["recovery_rate"] == 0.2
    assert np.isfinite(best["recovery_rate"]) and best["recovery_rate"] == 0.9


# ===========================================================================
# Audit fix M9 — PDF header visibility + None-safe candidate fields
# ===========================================================================
def test_academic_report_handles_none_candidate_fields():
    from astraeus.analysis.reporting import generate_academic_report

    payload = {
        "star_id": "AUDIT-9",
        "candidates": [
            {
                "candidate_id": "AUDIT-9 b",
                "period": None,  # key present with None -> previously TypeError
                "snr": None,
                "depth": 0.01,
                "epoch": None,
            }
        ],
    }
    buf = generate_academic_report(payload, figures={})
    data = buf.getvalue()
    assert data[:4] == b"%PDF"
    buf.close()


# ===========================================================================
# Audit fix M10 — corrupt experiment log backup + ledger dirname guard
# ===========================================================================
def test_save_experiment_log_backs_up_corrupt_file(tmp_path, monkeypatch):
    log_file = tmp_path / "experiments.json"
    monkeypatch.setattr("astraeus.analysis.logging.LOG_FILE", str(log_file))
    log_file.write_text("{ this is not json", encoding="utf-8")

    exp_id = save_experiment_log({"p": 1}, {"dataset": "d"}, [])

    backups = list(tmp_path.glob("experiments.json.corrupt-*"))
    assert len(backups) == 1, "corrupt log was not backed up before overwrite"
    assert "not json" in backups[0].read_text(encoding="utf-8")

    with open(log_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    assert len(history) == 1
    assert history[0]["id"] == exp_id


def test_experiment_ledger_accepts_bare_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = ExperimentLedger("ledger.json")  # empty dirname must not raise
    ledger.log_candidate(
        target_metadata={"target": "T-1"},
        calculated_period=3.1,
        signal_confidence=9.0,
        tracking_statistics={"snr": 9.0},
        data_source="synthetic",
    )
    assert (tmp_path / "ledger.json").exists()


# ===========================================================================
# Audit fix M11 — seeded MCMC walker initialization
# ===========================================================================
class _StubSampler:
    """Captures the walker initialization without running emcee."""

    instances: list = []

    def __init__(self, n_walkers, ndim, log_prob_fn, args=None):
        self.n_walkers = n_walkers
        self.ndim = ndim
        _StubSampler.instances.append(self)

    def run_mcmc(self, pos0, n_steps, progress=True):
        self.pos0 = np.array(pos0, dtype=float)
        self.n_steps = n_steps

    def get_chain(self, discard=0, flat=True):
        n_keep = max(self.n_steps - discard, 1)
        return np.zeros((self.n_walkers * n_keep, self.ndim))


def test_run_mcmc_seed_controls_walker_initialization():
    theta0 = (0.1, 89.0)
    args = (_FIT_TIME, _FIT_FLUX, _FIT_FLUX_ERR, dict(_BASE_FIXED),
            ["radius_ratio", "inclination_deg"])

    with patch.object(run_mcmc.__globals__["emcee"], "EnsembleSampler", _StubSampler):
        _StubSampler.instances.clear()
        run_mcmc(theta0, *args, n_walkers=8, n_steps=50, seed=42)
        pos_seeded_a = _StubSampler.instances[-1].pos0.copy()
        run_mcmc(theta0, *args, n_walkers=8, n_steps=50, seed=42)
        pos_seeded_b = _StubSampler.instances[-1].pos0.copy()

        np.random.seed(0)
        run_mcmc(theta0, *args, n_walkers=8, n_steps=50, seed=None)
        pos_unseeded_a = _StubSampler.instances[-1].pos0.copy()
        np.random.seed(1)
        run_mcmc(theta0, *args, n_walkers=8, n_steps=50, seed=None)
        pos_unseeded_b = _StubSampler.instances[-1].pos0.copy()

    expected = theta0 + 1e-4 * np.random.default_rng(42).normal(size=(8, 2))
    assert np.allclose(pos_seeded_a, expected)
    assert np.array_equal(pos_seeded_a, pos_seeded_b)
    assert not np.allclose(pos_unseeded_a, pos_unseeded_b)


# ===========================================================================
# Audit fixes M12 + M13 + M14 — loader unit conversion, bjd_tdb mapping,
# non-finite filtering
# ===========================================================================
def test_loader_maps_bjd_tdb_and_converts_hours_to_days(tmp_path):
    import pandas as pd

    df = pd.DataFrame({
        "bjd_tdb": [24.0, 48.0, 72.0],
        "flux": [1.0, np.inf, 0.99],  # inf must be filtered (audit fix M14)
        "flux_err": [0.01, 0.01, 0.01],
    })
    csv_path = tmp_path / "lc.csv"
    df.to_csv(csv_path, index=False)

    t, f, e = universal_load_lightcurve("csv", str(csv_path), time_unit="hour")
    assert np.allclose(t, [1.0, 3.0])  # hours genuinely converted to days
    assert np.allclose(f, [1.0, 0.99])
    assert np.allclose(e, [0.01, 0.01])
    assert np.all(np.isfinite(t)) and np.all(np.isfinite(f)) and np.all(np.isfinite(e))


def test_loader_rejects_invalid_time_unit(tmp_path):
    import pandas as pd

    df = pd.DataFrame({
        "time": [1.0, 2.0],
        "flux": [1.0, 1.0],
        "flux_err": [0.01, 0.01],
    })
    csv_path = tmp_path / "lc2.csv"
    df.to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="Time column"):
        universal_load_lightcurve("csv", str(csv_path), time_unit="bogus_unit_xyz")
    with pytest.raises(ValueError, match="Time column"):
        universal_load_lightcurve("csv", str(csv_path), time_unit="m")


def test_loader_flux_unit_must_be_dimensionless_compatible(tmp_path):
    import pandas as pd

    df = pd.DataFrame({
        "time": [1.0, 2.0],
        "flux": [1.0, 1.0],
        "flux_err": [0.01, 0.01],
    })
    csv_path = tmp_path / "lc3.csv"
    df.to_csv(csv_path, index=False)

    # Dimensionless-compatible flux unit: converted, values unchanged.
    t, f, e = universal_load_lightcurve(
        "csv", str(csv_path), flux_unit=u.dimensionless_unscaled
    )
    assert np.allclose(f, [1.0, 1.0])

    # Physical flux unit: not convertible to the normalized convention.
    with pytest.raises(ValueError, match="Flux column"):
        universal_load_lightcurve("csv", str(csv_path), flux_unit="erg / (cm2 s AA)")


# ===========================================================================
# Audit fix M15 — completeness heatmap orientation (transpose)
# ===========================================================================
def test_heatmap_grid_returns_transposed_orientation():
    recovery_rate = np.arange(24, dtype=float).reshape(2, 3, 4)
    grid = _heatmap_grid(recovery_rate, 2)

    # Rows must be radius_ratios (y), columns periods (x), matching the
    # declared extent with origin="lower".
    assert grid.shape == (3, 2)
    assert np.array_equal(grid, recovery_rate[:, :, 2].T)
    # Explicit orientation check: grid[radius_idx, period_idx].
    assert grid[1, 0] == recovery_rate[0, 1, 2]
    assert grid[0, 1] == recovery_rate[1, 0, 2]


@pytest.mark.parametrize("n_snrs", [1, 3])
def test_plot_completeness_map_renders_both_branches(tmp_path, n_snrs):
    n_p, n_d = 4, 3
    rate = np.random.default_rng(3).random((n_p, n_d, n_snrs))
    result, config = _fake_sweep_result(rate)
    result.config = SimpleNamespace(use_full_pipeline=False, n_injections=5)

    heatmap_path, snr_path = plot_completeness_map(result, tmp_path)
    assert os.path.exists(heatmap_path)
    assert os.path.exists(snr_path)
