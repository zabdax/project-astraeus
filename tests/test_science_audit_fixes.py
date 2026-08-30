"""Regression tests for the 2026-08-21 science-pipeline audit fixes.

Locks (see AUDIT_LOGBOOK.md):
- C6: phase-folded data must be fit with a model aligned to phase 0
  (folded_time_to_model_time removes the periapsis+P/4 model offset).
- M14a: run_injection_recovery's injected_epoch is the true transit midpoint.
- M14b: completeness injection cells use a noise-only baseline; cell-cache
  hash carries an algo_version so stale cells are never reused.
- M1: BLS depth is a fraction — no percent conversion heuristic.
- M2: real signals just below p_max are recoverable; the everything-rejected
  fallback is flagged instead of silent.
- M10: a shallow candidate with a detected phase-0.5 secondary is classified
  by the EB evidence branches, not by the depth-only pass.
"""
from __future__ import annotations

import numpy as np
import pytest
from astropy import units as u

from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.data.preprocessing import folded_time_to_model_time, phase_fold_data


# ---------------------------------------------------------------------------
# C6 — model/folded-data phase alignment
# ---------------------------------------------------------------------------
class TestC6FoldedModelAlignment:
    def test_model_dips_at_phase_zero_after_conversion(self):
        """generate_model_flux evaluated on converted time must dip exactly
        where phase_fold_data puts the observed dip (phase 0)."""
        period = 2.470613
        t = np.linspace(0.0, period, 20001)
        model_time = folded_time_to_model_time(t, period) * u.day
        flux = _model_flux(model_time, period)
        dip_phase = t[int(np.argmin(flux))]
        assert abs(dip_phase) < 1e-2, (
            f"model dip lands at folded phase {dip_phase:.4f}, expected ~0"
        )

    def test_conversion_is_a_quarter_period_shift(self):
        t = np.array([0.0, 1.0, -2.0])
        out = folded_time_to_model_time(t, 8.0)
        assert np.allclose(out, t + 2.0)

    def test_fit_recovers_radius_ratio_on_folded_data(self):
        """End-to-end guard: fitting folded data through find_best_fit must
        recover the injected radius ratio instead of collapsing toward the
        prior floor (the pre-C6 failure mode)."""
        from astraeus.analysis.optimization import find_best_fit

        period = 2.470613
        true_k = 0.10
        rng = np.random.default_rng(42)
        phase = np.linspace(-0.5, 0.5, 800)
        # Box-shaped folded transit of depth k^2 centred at phase 0.
        flux = np.where(np.abs(phase) < 0.03, 1.0 - true_k**2, 1.0)
        flux = flux + 1e-4 * rng.standard_normal(flux.size)
        ferr = np.full_like(flux, 1e-4)

        best_theta, success = find_best_fit(
            initial_guess_theta=(0.05, 89.0),
            time=folded_time_to_model_time(phase, period) * u.day,
            flux=flux,
            flux_err=ferr,
            fixed_params={
                "R_star": 1.0 * u.R_sun,
                "period": period * u.day,
                "semi_major_axis": 0.05 * u.AU,
                "eccentricity": 0.0 * u.dimensionless_unscaled,
            },
            param_names=["radius_ratio", "inclination_deg"],
        )
        fitted_k = float(best_theta[0])
        assert fitted_k > 0.05, (
            f"fitted radius ratio {fitted_k:.4f} collapsed toward zero — "
            "model/data phase alignment regressed (audit fix C6)"
        )
        assert abs(fitted_k - true_k) <= 0.05 * true_k + 0.01


def _model_flux(time_quant, period):
    from astraeus.core.transit_model import generate_model_flux

    return generate_model_flux(
        time=time_quant,
        period=period * u.day,
        semi_major_axis=0.05 * u.AU,
        eccentricity=0.0 * u.dimensionless_unscaled,
        inclination=89.0 * u.deg,
        R_star=1.0 * u.R_sun,
        R_planet=0.1 * u.R_sun,
        u1=0.4,
        u2=0.2,
    )


# ---------------------------------------------------------------------------
# M14 — injection epoch honesty + completeness baseline
# ---------------------------------------------------------------------------
class TestM14InjectionEpoch:
    def test_injected_epoch_is_transit_midpoint(self):
        """The injected model must dip AT injected_epoch, not at
        injected_epoch + P/4."""
        from astraeus.simulation.synthetic import generate_model_flux as gmf

        period, epoch = 10.0, 45.0
        t = np.linspace(epoch - period, epoch + period, 40001)
        a_rs = 15.0
        model = gmf(
            time=(t - epoch + 0.25 * period) * u.day,
            period=period * u.day,
            semi_major_axis=a_rs * u.R_sun,
            eccentricity=0.0 * u.dimensionless_unscaled,
            inclination=np.arccos(0.2 / a_rs) * u.rad,
            R_star=1.0 * u.R_sun,
            R_planet=0.05 * u.R_sun,
            u1=0.1,
            u2=0.3,
        )
        dip_t = t[int(np.argmin(model))]
        # Dips repeat every period; compare the folded dip phase to epoch.
        dip_phase_offset = (dip_t - epoch + 0.5 * period) % period - 0.5 * period
        assert abs(dip_phase_offset) < 0.05, (
            f"injected dip folds to {dip_phase_offset:.3f} d from injected_epoch "
            "(injected_epoch contract regressed)"
        )

    def test_cell_hash_contains_algo_version(self):
        from astraeus.simulation.completeness import _compute_cell_hash

        h_new = _compute_cell_hash(10.0, 0.05, 20.0, 3, 42, False)
        # Same inputs must hash identically...
        assert h_new == _compute_cell_hash(10.0, 0.05, 20.0, 3, 42, False)
        # ...and the payload must carry an explicit algorithm version so a
        # methodology change invalidates stale cached cells.
        import inspect
        src = inspect.getsource(_compute_cell_hash)
        assert "algo_version" in src

    def test_injection_branch_uses_noise_only_baseline(self):
        import inspect

        from astraeus.simulation import completeness

        src = inspect.getsource(completeness._run_one_cell)
        assert "flux_baseline" in src and "theoretical_flux" in src, (
            "completeness injection branch must divide out the scenario "
            "transit before run_injection_recovery (audit fix M14b)"
        )


# ---------------------------------------------------------------------------
# M1 — BLS depth is a fraction (no /100 heuristic)
# ---------------------------------------------------------------------------
class TestM1DepthIsFraction:
    def test_deep_event_depth_not_shrunk(self):
        """A ~15%-deep event (EB territory) must keep its depth and yield a
        giant radius — the old heuristic turned it into a 0.15% 'planet'."""
        result = _run_detection_on_box(depth=0.15, period=5.0)
        assert result["transit_depth"] == pytest.approx(0.15, abs=0.02)
        radius = float(result.get("planet_radius_earth", 0.0))
        assert radius > 25.0, (
            f"planet_radius_earth={radius:.1f} — deep-event depth was "
            "shrunk by a percent-to-fraction heuristic (audit fix M1)"
        )

    def test_shallow_event_depth_passthrough(self):
        result = _run_detection_on_box(depth=0.01, period=5.0)
        assert result["transit_depth"] == pytest.approx(0.01, abs=0.002)


# ---------------------------------------------------------------------------
# M2 — boundary handling in BLSSearchEngine.search
# ---------------------------------------------------------------------------
class TestM2BoundaryHandling:
    def test_real_signal_just_below_pmax_is_recovered(self):
        """A genuine planet 4% below p_max sits in the old blanket
        rejection band; it must now be recovered."""
        baseline, true_period = 60.0, 28.8  # p_max = 30.0; |28.8-30|/30 = 4%
        rng = np.random.default_rng(7)
        t = np.linspace(0.0, baseline, 3000)
        y = 1.0 + 5e-4 * rng.standard_normal(t.size)
        ph = (t - 5.0 + 0.5 * true_period) % true_period - 0.5 * true_period
        y[np.abs(ph) < 0.125] -= 0.01

        res = BLSSearchEngine.search(t, y)
        assert abs(res["period"] - true_period) / true_period <= 0.02, (
            f"recovered {res['period']:.3f}d, expected ~{true_period}d — "
            "signal near p_max is being blacklisted again (audit fix M2)"
        )
        assert res["all_peaks_rejected"] is False

    def test_result_carries_all_peaks_rejected_flag(self):
        rng = np.random.default_rng(3)
        t = np.linspace(0.0, 20.0, 600)
        y = 1.0 + 1e-3 * rng.standard_normal(t.size)
        res = BLSSearchEngine.search(t, y)
        assert "all_peaks_rejected" in res


# ---------------------------------------------------------------------------
# M10 — EB evidence outranks the depth-only pass
# ---------------------------------------------------------------------------
class TestM10SecondaryEclipseOutranksDepthPass:
    def test_shallow_primary_with_deep_secondary_is_eb(self):
        """Primary 1% deep (< 3% ceiling) + significant secondary at phase
        0.5: the old depth-only pass stamped this 'Verified Planet
        Candidate' before the EB branches could speak. Period/duration are
        chosen so the secondary covers most of GeometricValidator's
        median-based phase-0.5 window (±0.05 in normalized phase)."""
        result = _run_detection_on_box(
            depth=0.01, period=2.0, secondary_depth=0.004, duration=0.12
        )
        status = str(result.get("vetting_status", ""))
        assert "Eclipsing Binary" in status, (
            f"vetting_status={status!r} — a shallow primary with a detected "
            "phase-0.5 secondary must be classified by the EB evidence "
            "branches (audit fix M10)"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _box_light_curve(depth, period, secondary_depth=0.0, baseline=60.0,
                     n=3000, duration=0.15, noise=5e-4, seed=11):
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, baseline, n)
    y = 1.0 + noise * rng.standard_normal(n)
    ph = (t - 5.0 + 0.5 * period) % period - 0.5 * period
    y[np.abs(ph) < 0.5 * duration] -= depth
    if secondary_depth > 0.0:
        # Mirror GeometricValidator's convention: normalized phase
        # ((t - t0)/period) mod 1, eclipse centred at 0.5.
        phase_norm = ((t - 5.0) / period) % 1.0
        sec_mask = np.abs(phase_norm - 0.5) < 0.5 * duration / period
        y[sec_mask] -= secondary_depth
    return t, y


def _run_detection_on_box(depth, period, secondary_depth=0.0, duration=0.15):
    from astraeus.analysis.detection import detect_transit_candidate

    t, y = _box_light_curve(
        depth, period, secondary_depth=secondary_depth, duration=duration
    )
    return detect_transit_candidate(
        t,
        y,
        target_name="audit_regression",
        data_source="synthetic",
        metadata={"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0},
    )
