"""P4-C vetting diagnostics: weighted chi2 + odd/even + ephemeris match.

TDD tests for the additive bucket P4-C change to
``astraeus/analysis/vetting.py``. Nothing here may alter the verdict,
threshold, or return shape of existing functions — all coverage below
only pins additive behaviour:

* ``VettingEngine.vet_transit_shape(..., flux_err=None)`` — the default
  (``None``) path must be byte-identical to the legacy unweighted path,
  while ``flux_err=ones`` must reproduce the same verdict/chi2 values
  and heteroscedastic errors must run cleanly.
* ``odd_even_depth_test`` — consistent on a symmetric injection,
  inconsistent on a crafted odd/even-mismatch light curve.
* ``ephemeris_match`` — exact match, harmonic (2x / 0.5x) match,
  clean non-match, and the explicit ``None`` (never silent ``False``)
  contract for an empty known-period list.
* Legacy guard — default outputs unchanged and the ``snr > 10.0``
  literal untouched (a separate gated decision owns that threshold).

Fast by design: only ``vet_transit_shape`` (local window fit) is
exercised — no BLS ``detect_transit_candidate`` calls — so this file
finishes in seconds.
"""

from __future__ import annotations

import inspect

import numpy as np

from astraeus.analysis import vetting as vetting_mod
from astraeus.analysis.vetting import VettingEngine


# ---------------------------------------------------------------------------
# Light-curve builders (small/fast: local-window fits only, no BLS)
# ---------------------------------------------------------------------------


def _build_u_shape(
    *,
    period_days: float = 3.0,
    duration_days: float = 0.1,
    depth: float = 0.01,
    noise_amplitude: float = 1e-4,
    t0_days: float = 1.5,
    n_points: int = 2000,
    span_days: float = 16.0,
    seed: int = 11,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Trapezoidal U-shape transit, symmetric across all epochs."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, span_days, n_points)
    phase = (t - t0_days + 0.5 * period_days) % period_days - 0.5 * period_days
    flux = np.ones_like(t)
    in_transit = np.abs(phase) < 0.5 * duration_days
    ingress = 0.5 * duration_days * 0.10
    flat_region = np.abs(phase) < (0.5 * duration_days - ingress)
    flux[in_transit] = 1.0 - depth
    slope_mask = in_transit & ~flat_region
    if ingress > 0:
        flux[slope_mask] = 1.0 - depth * (
            0.5 * duration_days - np.abs(phase[slope_mask])
        ) / ingress
    flux = flux + rng.normal(0.0, noise_amplitude, size=t.shape)
    return t, flux, period_days, t0_days, duration_days


def _build_odd_even_mismatch(
    *,
    period_days: float = 3.0,
    duration_days: float = 0.1,
    depth_odd: float = 0.012,
    depth_even: float = 0.004,
    noise_amplitude: float = 5e-5,
    t0_days: float = 1.5,
    n_points: int = 2500,
    span_days: float = 16.0,
    seed: int = 23,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Box-shaped transits whose depth depends on epoch parity.

    Odd epochs get ``depth_odd``, even epochs ``depth_even`` — the
    classic eclipsing-binary odd/even signature.
    """
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, span_days, n_points)
    epochs = np.round((t - t0_days) / period_days).astype(int)
    phase = (t - t0_days) - epochs * period_days
    flux = np.ones_like(t)
    in_transit = np.abs(phase) < 0.5 * duration_days
    is_odd = (epochs % 2) != 0
    flux[in_transit & is_odd] -= depth_odd
    flux[in_transit & ~is_odd] -= depth_even
    flux = flux + rng.normal(0.0, noise_amplitude, size=t.shape)
    return t, flux, period_days, t0_days, duration_days


# ---------------------------------------------------------------------------
# Legacy-contract guards (additive-only: defaults/outputs must not move)
# ---------------------------------------------------------------------------


def test_flux_err_param_exists_and_defaults_to_none():
    """The new ``flux_err`` parameter must be optional with default None."""
    sig = inspect.signature(VettingEngine.vet_transit_shape)
    assert "flux_err" in sig.parameters
    assert sig.parameters["flux_err"].default is None


def test_legacy_default_outputs_unchanged():
    """Default call (no ``flux_err``) keeps the exact legacy return shape."""
    t, flux, period, t0, duration = _build_u_shape()
    result = VettingEngine.vet_transit_shape(t, flux, period, t0, duration, depth=0.01)
    assert set(result.keys()) == {
        "vetting_status",
        "vetting_confidence",
        "u_shape_chi2",
        "v_shape_chi2",
        "delta_chi2_u",
        "delta_chi2_v",
    }
    # Explicit None must be identical to omitting the argument entirely.
    result_none = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01, flux_err=None
    )
    assert result_none == result


def test_snr_literal_preserved():
    """The ``snr > 10.0`` gate is a separate gated decision — P4-C must not
    touch it."""
    source = inspect.getsource(VettingEngine.vet_transit_shape)
    assert "snr > 10.0" in source


# ---------------------------------------------------------------------------
# Weighted chi2 (flux_err) behaviour
# ---------------------------------------------------------------------------


def test_weighted_uniform_errors_agree_with_unweighted():
    """Uniform sigma=1 errors weight every residual by 1, so verdict and
    chi2 values must reproduce the legacy unweighted path."""
    t, flux, period, t0, duration = _build_u_shape()
    legacy = VettingEngine.vet_transit_shape(t, flux, period, t0, duration, depth=0.01)
    weighted = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01, flux_err=np.ones_like(flux)
    )
    assert weighted["vetting_status"] == legacy["vetting_status"]
    np.testing.assert_allclose(weighted["u_shape_chi2"], legacy["u_shape_chi2"], rtol=1e-12)
    np.testing.assert_allclose(weighted["v_shape_chi2"], legacy["v_shape_chi2"], rtol=1e-12)
    np.testing.assert_allclose(weighted["delta_chi2_u"], legacy["delta_chi2_u"], rtol=1e-12)
    np.testing.assert_allclose(weighted["delta_chi2_v"], legacy["delta_chi2_v"], rtol=1e-12)
    assert set(weighted.keys()) == set(legacy.keys())


def test_weighted_heteroscedastic_errors_run_cleanly():
    """Per-point uncertainties must be honoured without changing the
    return shape; down-weighting noisy points keeps a valid verdict."""
    t, flux, period, t0, duration = _build_u_shape()
    rng = np.random.default_rng(99)
    flux_err = np.full_like(flux, 1e-4)
    flux_err[::7] = 5e-4  # every 7th point is noisier -> down-weighted
    assert np.all(flux_err > 0)
    result = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01, flux_err=flux_err
    )
    assert set(result.keys()) == {
        "vetting_status",
        "vetting_confidence",
        "u_shape_chi2",
        "v_shape_chi2",
        "delta_chi2_u",
        "delta_chi2_v",
    }
    assert result["vetting_status"] in (
        "Likely Planet",
        "Ambiguous/False Positive",
        "Insufficient Data",
        "Inconclusive",
        "Indeterminate",
    )
    assert result["u_shape_chi2"] >= 0.0
    assert result["v_shape_chi2"] >= 0.0


# ---------------------------------------------------------------------------
# Odd/even depth test
# ---------------------------------------------------------------------------


def test_odd_even_consistent_on_symmetric_injection():
    """Equal depths on odd and even epochs -> consistent, ratio ~ 1."""
    t, flux, period, t0, duration = _build_u_shape(depth=0.01)
    result = vetting_mod.odd_even_depth_test(t, flux, period, t0, duration, 0.01)
    assert result["consistent"] is True
    np.testing.assert_allclose(result["depth_odd"], 0.01, rtol=0.25)
    np.testing.assert_allclose(result["depth_even"], 0.01, rtol=0.25)
    np.testing.assert_allclose(result["depth_ratio"], 1.0, rtol=0.30)


def test_odd_even_inconsistent_on_crafted_mismatch():
    """3x deeper odd transits (binary signature) -> inconsistent."""
    t, flux, period, t0, duration = _build_odd_even_mismatch()
    result = vetting_mod.odd_even_depth_test(t, flux, period, t0, duration, 0.012)
    assert result["consistent"] is False
    # Odd depth must read substantially deeper than even depth.
    assert result["depth_odd"] > 2.0 * result["depth_even"]
    assert result["depth_ratio"] > 2.0


def test_odd_even_exposed_on_engine():
    """OO alias: available as ``VettingEngine.odd_even_depth_test`` too."""
    assert callable(getattr(VettingEngine, "odd_even_depth_test", None))
    t, flux, period, t0, duration = _build_u_shape(depth=0.01)
    result = VettingEngine.odd_even_depth_test(t, flux, period, t0, duration, 0.01)
    assert result["consistent"] is True


# ---------------------------------------------------------------------------
# Ephemeris match
# ---------------------------------------------------------------------------


def test_ephemeris_exact_match():
    result = vetting_mod.ephemeris_match(3.0, [3.0])
    assert result["match"] is True
    np.testing.assert_allclose(result["matched_period"], 3.0, rtol=1e-12)
    np.testing.assert_allclose(result["ratio"], 1.0, rtol=1e-12)


def test_ephemeris_harmonic_matches():
    """2x and 0.5x harmonics of a known period must match."""
    double = vetting_mod.ephemeris_match(6.0, [3.0])
    assert double["match"] is True
    np.testing.assert_allclose(double["matched_period"], 3.0, rtol=1e-12)
    np.testing.assert_allclose(double["ratio"], 2.0, rtol=1e-12)

    half = vetting_mod.ephemeris_match(1.5, [3.0])
    assert half["match"] is True
    np.testing.assert_allclose(half["ratio"], 0.5, rtol=1e-12)


def test_ephemeris_no_match():
    result = vetting_mod.ephemeris_match(3.0, [5.0])
    assert result["match"] is False
    assert result["matched_period"] is None
    assert result["ratio"] is None


def test_ephemeris_empty_list_returns_none_not_false():
    """Empty known list -> explicit None, never a silent False."""
    result = vetting_mod.ephemeris_match(3.0, [])
    assert result["match"] is None
    assert result["matched_period"] is None
    assert result["ratio"] is None


def test_ephemeris_exposed_on_engine():
    assert callable(getattr(VettingEngine, "ephemeris_match", None))
    assert VettingEngine.ephemeris_match(3.0, [])["match"] is None
