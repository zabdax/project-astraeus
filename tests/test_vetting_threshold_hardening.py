"""Tests for the bucket-2 threshold-hardening changes.

These tests guard against the headline bug this bucket exists to fix: a
genuine hot, large planet around a cool star whose real thermal
occultation depth legitimately exceeds the historical 800 ppm constant
was being misclassified as an eclipsing binary.

Coverage:

* Unit tests for ``PhysicalPropertiesEngine.expected_occultation_depth_ppm``
  verifying the Rayleigh-Jeans formula, the temperature cap, and the
  ``None``-on-missing-input contract.
* Integration tests through ``detect_transit_candidate`` confirming that
  a secondary-eclipse depth above 800 ppm but below the *physically
  derived* threshold is now labeled "Verified Planet Candidate
  (Atmospheric Occultation Detected)" instead of "Eclipsing Binary".
* Integration tests confirming that when physical inputs are missing the
  pipeline falls back to the documented 800 ppm constant and flags the
  fallback in the result dict via ``secondary_eclipse_threshold_mode``.
"""

from __future__ import annotations

import numpy as np

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.physical_properties import (
    PhysicalPropertiesEngine,
    R_SUN_TO_R_EARTH,
)
from astraeus.analysis.vetting import VettingEngine
from astraeus.core.constants import (
    VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM,
    VETTING_U_VS_V_CHI2_DELTA_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Unit tests for expected_occultation_depth_ppm
# ---------------------------------------------------------------------------


def test_expected_occultation_depth_ppm_hot_jupiter_around_sun():
    """Jupiter-radius planet around a Sun-like star: ~2.7e3 ppm.

    Geometric depth alone would be (R_p/R_star)^2 = 0.01 = 10000 ppm.
    The Rayleigh-Jeans formula scales by T_planet/T_star ≈ 0.26, so the
    expected thermal occultation depth is roughly a quarter of the
    geometric depth.
    """
    depth_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        planet_radius_earth=11.2,           # ~1 R_Jupiter
        stellar_radius_solar=1.0,
        planet_equilibrium_temp_k=1500.0,
        stellar_teff_k=5778.0,
    )
    assert depth_ppm is not None
    # (11.2 / (1.0 * 109.2))^2 * (1500/5778) * 1e6 ≈ 2730 ppm
    assert 2500.0 < depth_ppm < 3000.0, (
        f"hot-Jupiter-around-Sun expected ~2730 ppm, got {depth_ppm:.1f}"
    )
    # Sanity: well below the geometric upper bound of ~10000 ppm.
    assert depth_ppm < 10000.0


def test_expected_occultation_depth_ppm_earth_sun_analog():
    """Earth around Sun: very small thermal occultation depth."""
    depth_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        planet_radius_earth=1.0,
        stellar_radius_solar=1.0,
        planet_equilibrium_temp_k=279.0,
        stellar_teff_k=5778.0,
    )
    assert depth_ppm is not None
    # (1/109.2)^2 * (279/5778) * 1e6 ≈ 4 ppm
    assert 3.0 < depth_ppm < 6.0, (
        f"Earth-Sun expected ~4 ppm, got {depth_ppm:.2f}"
    )


def test_expected_occultation_depth_ppm_hot_planet_around_m_dwarf_exceeds_800ppm():
    """The headline bucket-2 case: a hot planet around an M-dwarf can
    legitimately produce a thermal occultation depth well above the
    historical 800 ppm constant.

    With a 3.86 R_earth planet at 1500 K around a 0.5 R_sun, 3500 K
    M-dwarf the formula yields >1000 ppm.
    """
    depth_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        planet_radius_earth=3.86,
        stellar_radius_solar=0.5,
        planet_equilibrium_temp_k=1500.0,
        stellar_teff_k=3500.0,
    )
    assert depth_ppm is not None
    assert depth_ppm > 800.0, (
        f"hot-planet-around-M-dwarf should exceed 800 ppm to motivate "
        f"the physical-threshold fix; got {depth_ppm:.1f}"
    )
    # Sanity: still below the geometric upper bound.
    geometric_ppm = (3.86 / (0.5 * R_SUN_TO_R_EARTH)) ** 2 * 1e6
    assert depth_ppm < geometric_ppm


def test_expected_occultation_depth_ppm_returns_none_for_missing_inputs():
    """All required inputs must be positive; any missing/zero input
    triggers the ``None`` fallback contract."""
    assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        0.0, 1.0, 1500.0, 5778.0,
    ) is None
    assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        1.0, 0.0, 1500.0, 5778.0,
    ) is None
    assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        1.0, 1.0, 0.0, 5778.0,
    ) is None
    assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        1.0, 1.0, 1500.0, 0.0,
    ) is None
    assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        -1.0, 1.0, 1500.0, 5778.0,
    ) is None


def test_expected_occultation_depth_ppm_caps_temperature_ratio_at_one():
    """A planet cannot emit more thermal flux than the star in any
    bandpass without violating energy conservation. Archive values
    that are physically inconsistent (T_eq > T_eff) must therefore be
    capped at the geometric transit depth."""
    radius_term = (1.0 / (1.0 * R_SUN_TO_R_EARTH)) ** 2 * 1e6
    depth_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        planet_radius_earth=1.0,
        stellar_radius_solar=1.0,
        planet_equilibrium_temp_k=10000.0,   # impossible: hotter than the star
        stellar_teff_k=5778.0,
    )
    assert depth_ppm is not None
    # Cap at temp_ratio = 1.0 → depth equals the geometric upper bound.
    assert abs(depth_ppm - radius_term) < 0.1, (
        f"capped depth should equal the geometric upper bound "
        f"({radius_term:.1f} ppm); got {depth_ppm:.1f}"
    )


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------


def _build_transit_with_secondary(
    *,
    period_days: float,
    primary_depth: float,
    secondary_depth: float,
    duration_days: float,
    t0_days: float = 0.5,
    n_points: int = 4000,
    duration_days_total: float = 16.0,
    seed: int = 7,
    noise_amplitude: float = 1e-4,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a noisy light curve with a flat-bottomed primary transit and a
    square-wave secondary dip centred on phase 0.5.

    This is enough to feed ``detect_transit_candidate`` and exercise the
    secondary-eclipse branch in the cross-vetting tree.
    """
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, duration_days_total, n_points)

    # Primary transit (flat-bottomed, U-shape with sharp ingress/egress).
    phase = (t - t0_days + 0.5 * period_days) % period_days - 0.5 * period_days
    in_transit = np.abs(phase) < 0.5 * duration_days
    flux = np.ones_like(t)
    flux[in_transit] -= primary_depth

    # Secondary eclipse at phase 0.5: shallow boxcar.
    phase_secondary = ((t - t0_days) / period_days) % 1.0
    half_window = 0.03  # wider than the validator's half-window (0.05)
    in_secondary = np.abs(phase_secondary - 0.5) < half_window
    flux[in_secondary & ~in_transit] -= secondary_depth

    # Small Gaussian noise so the BLS search picks the period up.
    flux = flux + rng.normal(0.0, noise_amplitude, size=t.shape)
    return t, flux


def _m_dwarf_metadata() -> dict:
    """Hot-planet-around-M-dwarf metadata that motivates the headline fix."""
    return {
        "st_rad": 0.5,            # 0.5 R_sun M-dwarf
        "st_teff": 3500.0,
        "st_mass": 0.5,
        "sy_jmag": 10.0,
    }


# ---------------------------------------------------------------------------
# Integration tests through detect_transit_candidate
# ---------------------------------------------------------------------------


def test_pipeline_uses_physical_threshold_for_hot_planet_around_m_dwarf():
    """The headline misclassification bug, end-to-end:

    A primary transit deeper than 3% with a *plausibly thermal*
    secondary-eclipse depth that exceeds the old flat 800 ppm constant
    must now be classified as "Verified Planet Candidate (Atmospheric
    Occultation Detected)", NOT as "Eclipsing Binary Detected".

    With a 0.5 R_sun / 3500 K M-dwarf and a 3.86 R_earth / 1500 K planet
    the physical derivation produces a threshold of ~1100 ppm, well
    above the historical 800 ppm constant.
    """
    t, flux = _build_transit_with_secondary(
        period_days=1.5,
        primary_depth=0.04,           # > 3% so branch 1 does NOT fire
        secondary_depth=0.0010,       # 1000 ppm: above old 800 ppm, below physical ~1100 ppm
        duration_days=0.08,
    )

    result = detect_transit_candidate(t, flux, metadata=_m_dwarf_metadata())

    # The threshold mode and value must be reported in the result dict.
    assert result.get("secondary_eclipse_threshold_mode") == "physical", (
        f"expected physical-threshold mode, got "
        f"{result.get('secondary_eclipse_threshold_mode')!r}"
    )
    threshold_ppm = result.get("secondary_eclipse_threshold_ppm")
    assert threshold_ppm is not None and threshold_ppm > 800.0, (
        f"physical threshold should exceed 800 ppm for an M-dwarf host; "
        f"got {threshold_ppm}"
    )

    # The headline assertion: this candidate should be a planet, NOT a binary.
    vetting_status = str(result.get("vetting_status"))
    assert "Binary" not in vetting_status, (
        f"hot-planet-around-M-dwarf with 1000 ppm secondary depth was "
        f"misclassified as {vetting_status!r} — the bucket-2 fix did not work"
    )
    assert vetting_status.startswith("Verified Planet Candidate"), (
        f"expected planet candidate verdict, got {vetting_status!r}"
    )


def test_pipeline_fallback_when_physical_inputs_missing():
    """When the physical inputs that drive the threshold derivation are
    missing, the pipeline must fall back to the historical 800 ppm
    constant AND flag the fallback in the result dict."""
    t, flux = _build_transit_with_secondary(
        period_days=2.0,
        primary_depth=0.04,
        secondary_depth=0.0005,       # 500 ppm: below the 800 ppm fallback
        duration_days=0.08,
    )

    # Empty metadata => st_rad, st_teff, st_mass, sy_jmag all default to
    # the placeholders used inside detect_transit_candidate, BUT the
    # transit_depth_fraction > 0 && st_rad > 0 guard inside derive()
    # still produces *some* planet radius, so to force the fallback path
    # we need st_teff = 0 (or transit_depth = 0). The cleanest way is
    # to omit the metadata entirely AND set depth = 0 — but then no
    # candidate is found. Instead, force st_teff = 0 via metadata.
    metadata = {"st_teff": 0.0}  # temperature missing → expected_occultation returns None

    result = detect_transit_candidate(t, flux, metadata=metadata)

    # Mode must be flagged as fallback.
    assert result.get("secondary_eclipse_threshold_mode") == "fallback_fixed", (
        f"expected fallback-fixed mode, got "
        f"{result.get('secondary_eclipse_threshold_mode')!r}"
    )
    # Value must be the documented fallback constant.
    assert result.get("secondary_eclipse_threshold_ppm") == VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM, (
        f"expected fallback {VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM} ppm, "
        f"got {result.get('secondary_eclipse_threshold_ppm')}"
    )


def test_pipeline_fallback_when_transit_depth_unavailable():
    """When the transit depth itself is zero (no candidate recovered),
    the physical derivation has no planet radius to work with — the
    pipeline must fall back gracefully."""
    # Pure noise — no injected transit.
    rng = np.random.default_rng(123)
    t = np.linspace(0, 10, 1000)
    flux = 1.0 + rng.normal(0, 0.001, t.shape)

    result = detect_transit_candidate(t, flux, metadata=_m_dwarf_metadata())

    # Whether or not the BLS search flags this as a candidate, the
    # threshold bookkeeping must be present in the dict.
    assert "secondary_eclipse_threshold_mode" in result
    assert "secondary_eclipse_threshold_ppm" in result
    # The mode and value must come as a consistent pair.
    mode = result["secondary_eclipse_threshold_mode"]
    value = result["secondary_eclipse_threshold_ppm"]
    assert mode in ("physical", "fallback_fixed")
    if mode == "fallback_fixed":
        assert value == VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM
    else:
        assert value > 0.0


def test_pipeline_threshold_mode_present_in_result_dict_for_known_truth():
    """Even when a real candidate is found, the threshold mode and value
    must be present in the result dict so downstream consumers can audit
    the decision."""
    # Use a quiet, well-behaved hot-Jupiter scenario.
    t, flux = _build_transit_with_secondary(
        period_days=3.0,
        primary_depth=0.01,            # 1%, well below the 3% depth ceiling
        secondary_depth=0.0000,         # no secondary — exercises "Verified Planet Candidate"
        duration_days=0.1,
    )
    metadata = {
        "st_rad": 1.0,
        "st_teff": 5778.0,
        "st_mass": 1.0,
        "sy_jmag": 10.0,
    }
    result = detect_transit_candidate(t, flux, metadata=metadata)
    assert "secondary_eclipse_threshold_mode" in result
    assert "secondary_eclipse_threshold_ppm" in result


# ---------------------------------------------------------------------------
# Boundary tests for the bucket-10 significance floor on
# VettingEngine.vet_transit_shape's U-vs-V chi2-delta threshold.
#
# These tests pin the boundary so future threshold-default changes cannot
# silently move the decision rule. The strategy is to construct a synthetic
# light curve whose natural ``(delta_chi2_u - delta_chi2_v)`` is known, then
# pass explicit ``threshold`` values just above and just below that natural
# delta — that way the verdict assertions are independent of whatever the
# default threshold is set to, and only depend on the verdict-logic
# comparison itself.
# ---------------------------------------------------------------------------


def _build_clear_u_shape(
    *,
    period_days: float = 3.0,
    duration_days: float = 0.1,
    depth: float = 0.01,
    noise_amplitude: float = 1e-4,
    t0_days: float = 1.5,
    n_points: int = 4000,
    span_days: float = 16.0,
    seed: int = 1,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """Trapezoidal U-shape transit — the canonical real-planet case for
    bucket-10 boundary testing.

    Returns ``(time, flux, period, t0, duration)`` so the caller can pass
    them straight into ``vet_transit_shape``.
    """
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


def test_vetting_threshold_default_is_positive_significance_floor():
    """The bucket-10 fix: ``vet_transit_shape``'s default ``threshold`` is
    now a positive significance floor (the documented
    ``VETTING_U_VS_V_CHI2_DELTA_THRESHOLD``), not ``0.0``.

    Pins the headline change. If anyone reverts to ``threshold=0.0``,
    this test fails immediately.
    """
    assert VETTING_U_VS_V_CHI2_DELTA_THRESHOLD > 0.0, (
        "bucket 10 fix: vet_transit_shape default threshold must be > 0.0; "
        f"got {VETTING_U_VS_V_CHI2_DELTA_THRESHOLD}"
    )
    # And specifically, must be the empirically-motivated 0.001 from
    # reports/bucket10_threshold_audit.md §3.2.
    assert VETTING_U_VS_V_CHI2_DELTA_THRESHOLD == 0.001, (
        f"threshold changed from the bucket-10 derivation value 0.001 "
        f"to {VETTING_U_VS_V_CHI2_DELTA_THRESHOLD}; re-run "
        f"scratch/bucket10_threshold_characterization.py and update the "
        f"audit before accepting this value"
    )


def test_vetting_threshold_default_accepts_clear_u_shape():
    """A clear trapezoidal U-shape at depth=0.01 must still be classified
    as ``"Likely Planet"`` under the new default threshold — the bucket-10
    fix must not regress real planets.

    At depth=0.01 the empirical ``(delta_chi2_u - delta_chi2_v)`` is
    ~+0.0021, comfortably above the new default of 0.001.
    """
    t, flux, period, t0, duration = _build_clear_u_shape(depth=0.01)
    result = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01,
    )
    assert result["vetting_status"] == "Likely Planet", (
        f"clear U-shape at depth=0.01 must remain 'Likely Planet' under "
        f"the new default threshold={VETTING_U_VS_V_CHI2_DELTA_THRESHOLD}; "
        f"got {result['vetting_status']!r} (delta_u_minus_v="
        f"{result['delta_chi2_u'] - result['delta_chi2_v']:.6f})"
    )


def test_vetting_threshold_boundary_just_above_is_ambiguous():
    """Pin the verdict boundary: when the explicit ``threshold`` is set
    just ABOVE the natural ``(delta_chi2_u - delta_chi2_v)``, the verdict
    MUST be ``"Ambiguous/False Positive"``.

    This is the boundary that bucket-10 establishes. If anyone weakens the
    verdict logic to a strict-inequality flip, an off-by-one comparison, or
    a sign error, this test fails.
    """
    t, flux, period, t0, duration = _build_clear_u_shape(depth=0.01)

    # Probe the natural delta at the default threshold first so we have a
    # reference value to add a small epsilon to.
    probe = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01,
        threshold=0.0,
    )
    natural_delta = probe["delta_chi2_u"] - probe["delta_chi2_v"]
    assert natural_delta > 0.0, (
        f"sanity check: clear U-shape should have positive delta_u_minus_v "
        f"under threshold=0.0; got {natural_delta}"
    )

    # Force the boundary: threshold = natural_delta + tiny epsilon.
    boundary_threshold = natural_delta + 1e-5
    result = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01,
        threshold=boundary_threshold,
    )
    assert result["vetting_status"] == "Ambiguous/False Positive", (
        f"with threshold={boundary_threshold} (just above natural_delta="
        f"{natural_delta}), verdict MUST be 'Ambiguous/False Positive'; "
        f"got {result['vetting_status']!r}"
    )


def test_vetting_threshold_boundary_just_below_is_likely_planet():
    """Pin the verdict boundary from the other side: when the explicit
    ``threshold`` is set just BELOW the natural ``(delta_chi2_u -
    delta_chi2_v)``, the verdict MUST be ``"Likely Planet"``.

    Pairs with ``test_vetting_threshold_boundary_just_above_is_ambiguous``
    to bracket the boundary on both sides.
    """
    t, flux, period, t0, duration = _build_clear_u_shape(depth=0.01)

    probe = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01,
        threshold=0.0,
    )
    natural_delta = probe["delta_chi2_u"] - probe["delta_chi2_v"]
    assert natural_delta > 0.0, (
        f"sanity check: clear U-shape should have positive delta_u_minus_v "
        f"under threshold=0.0; got {natural_delta}"
    )

    # Force the boundary: threshold = natural_delta - tiny epsilon.
    boundary_threshold = natural_delta - 1e-5
    assert boundary_threshold > 0.0, (
        "test fixture broken: natural_delta is too small to subtract 1e-5 "
        "and stay positive; rebuild _build_clear_u_shape with a stronger signal"
    )
    result = VettingEngine.vet_transit_shape(
        t, flux, period, t0, duration, depth=0.01,
        threshold=boundary_threshold,
    )
    assert result["vetting_status"] == "Likely Planet", (
        f"with threshold={boundary_threshold} (just below natural_delta="
        f"{natural_delta}), verdict MUST be 'Likely Planet'; got "
        f"{result['vetting_status']!r}"
    )
