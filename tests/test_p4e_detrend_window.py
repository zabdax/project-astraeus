"""P4-E: detrending-window observability + window provenance (TDD).

Bucket P4-E adds observability, not physics:

* ``window_for_duration`` parameterizes the transit-preserving window
  (scales with a duration-like timescale, clamped to the legacy
  0.5/1.5-day bounds). Numbers must be IDENTICAL to the legacy inline
  ``min(MAX, max(MIN, duration * 0.5))`` expression for every input.
* ``DetrendingEngine.detrend_report`` records WHICH window rule produced
  the value (``window_source``) alongside the estimator ``method`` and
  the ``window_days`` actually used.

Zero-numeric-change proof strategy used here:

* The legacy formulas are copied into this file as oracles
  (:func:`_legacy_rotation_window`, :func:`_legacy_st_rad_window`) and
  the new helpers are asserted exactly equal to them (``==``, not
  ``allclose`` — the arithmetic is identical, so even float bits match).
* The ``window_length`` value actually handed to the wotan estimator
  (and the ``size`` handed to the scipy median fallback) is captured via
  monkeypatching and asserted equal to the legacy oracle, proving the
  routing change cannot alter any existing call shape's numbers.
* Tuple shapes are asserted backward compatible: ``detrend`` still
  returns a bare array, ``detrend_with_method`` still returns a 2-tuple
  with the unchanged method strings.

Constraints: this file must finish in well under ~180 s. All fixtures
are tiny synthetic curves; no TLS, no BLS, no network.
"""

from __future__ import annotations

import numpy as np
import pytest

from astraeus.analysis.detrending import (
    METHOD_NONE,
    METHOD_SCIPY_MEDIAN,
    METHOD_WOTAN_BIWEIGHT,
    WINDOW_SOURCE_ROTATION_CLAMPED_MAX,
    WINDOW_SOURCE_ROTATION_CLAMPED_MIN,
    WINDOW_SOURCE_ROTATION_SCALED,
    WINDOW_SOURCE_ST_RAD_INTERPOLATED,
    WINDOW_SOURCE_ST_RAD_LARGE,
    WINDOW_SOURCE_ST_RAD_SMALL,
    DetrendingEngine,
    window_for_duration,
)


# ---------------------------------------------------------------------------
# Legacy oracles (copied from the pre-P4-E inline expressions in
# DetrendingEngine.detrend_with_method -- these are the frozen numbers).
# ---------------------------------------------------------------------------

LEGACY_MIN = 0.5
LEGACY_MAX = 1.5


def _legacy_rotation_window(duration_days: float) -> float:
    """Pre-P4-E rotation branch, verbatim: min(MAX, max(MIN, d * 0.5))."""
    return min(
        LEGACY_MAX,
        max(
            LEGACY_MIN,
            duration_days * 0.5,
        ),
    )


def _legacy_st_rad_window(st_rad: float) -> float:
    """Pre-P4-E st_rad branch, verbatim."""
    if st_rad < 0.3:
        return 0.5
    elif st_rad >= 0.8:
        return 2.0
    else:
        return 0.5 + ((2.0 - 0.5) / (0.8 - 0.3)) * (st_rad - 0.3)


def _curve(n: int = 240, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=seed)
    t = np.arange(n, dtype=np.float64) * 0.02
    flux = 1.0 + 0.01 * rng.standard_normal(n)
    return t, flux


# Nominal spacing of the _curve fixture (0.02 d); the median-size oracle
# derives the effective dt from the actual time array, exactly as the
# implementation does (float64 0.02 steps are not exact, so int() can
# differ by one from the naive 0.02 division -- the test must mirror
# the real computation, not an idealized one).
def _legacy_median_size(window_days: float, dt: float) -> int:
    """Pre-P4-E scipy fallback size derivation, verbatim."""
    points = int(window_days / dt)
    if points % 2 == 0:
        points += 1
    return max(3, points)


# ---------------------------------------------------------------------------
# 1. window identity vs legacy constants across durations
# ---------------------------------------------------------------------------


def test_window_bound_constants_unchanged() -> None:
    """The 0.5/1.5-day bounds themselves are frozen (P4-E only documents)."""
    assert DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS == LEGACY_MIN
    assert DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS == LEGACY_MAX


@pytest.mark.parametrize(
    "duration",
    [
        0.0,  # degenerate -> clamped to MIN
        0.1,  # short -> raw 0.05 -> clamped to MIN
        0.5,  # raw 0.25 -> clamped to MIN
        1.0,  # raw 0.5 -> exactly MIN boundary
        1.5,
        2.0,  # raw 1.0 -> interior (scaled)
        2.7,  # raw 1.35 -> interior
        3.0,  # raw 1.5 -> exactly MAX boundary
        4.0,  # raw 2.0 -> clamped to MAX
        5.0,  # long -> clamped to MAX
        10.0,  # very long -> clamped to MAX
        -1.0,  # unphysical negative -> clamped to MIN (legacy behaviour)
    ],
)
def test_window_for_duration_matches_legacy_oracle(duration: float) -> None:
    """window_for_duration(d) must be bit-identical to the legacy clamp."""
    got = window_for_duration(duration)
    assert got == _legacy_rotation_window(duration)
    assert LEGACY_MIN <= got <= LEGACY_MAX


def test_class_and_module_helpers_agree() -> None:
    """DetrendingEngine.window_for_duration delegates to the module helper."""
    for duration in (0.1, 1.0, 2.0, 3.0, 9.0):
        assert DetrendingEngine.window_for_duration(duration) == window_for_duration(duration)


def test_window_scales_monotonically_inside_bounds() -> None:
    """Inside the clamp the window scales with duration (documented rule)."""
    assert window_for_duration(1.0) < window_for_duration(2.0) < window_for_duration(2.9)
    assert window_for_duration(2.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 2. routing identity: the estimator receives the legacy window value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rotation", [0.2, 1.0, 2.0, 3.0, 6.0])
def test_wotan_receives_legacy_window(rotation: float, monkeypatch) -> None:
    """The window_length handed to wotan.flatten must equal the oracle."""
    import wotan

    captured: dict = {}

    def _fake_flatten(time, flux, window_length, method, return_trend):
        captured["window_length"] = window_length
        captured["method"] = method
        flux = np.asarray(flux, dtype=np.float64)
        return flux, np.ones_like(flux)

    monkeypatch.setattr(wotan, "flatten", _fake_flatten)
    t, flux = _curve()
    out, method = DetrendingEngine.detrend_with_method(t, flux, rotation)
    assert method == METHOD_WOTAN_BIWEIGHT
    assert captured["window_length"] == _legacy_rotation_window(rotation)
    assert captured["method"] == "biweight"
    assert out.shape == flux.shape


@pytest.mark.parametrize(
    "st_rad",
    [0.1, 0.29, 0.3, 0.5, 0.79, 0.8, 1.0, 2.0],
)
def test_wotan_receives_legacy_st_rad_window(st_rad: float, monkeypatch) -> None:
    """The st_rad branch values (incl. the 2.0 d evolved-star value that
    exceeds the rotation clamp) must pass through unchanged."""
    import wotan

    captured: dict = {}

    def _fake_flatten(time, flux, window_length, method, return_trend):
        captured["window_length"] = window_length
        flux = np.asarray(flux, dtype=np.float64)
        return flux, np.ones_like(flux)

    monkeypatch.setattr(wotan, "flatten", _fake_flatten)
    t, flux = _curve()
    DetrendingEngine.detrend_with_method(t, flux, 2.0, st_rad=st_rad)
    assert captured["window_length"] == _legacy_st_rad_window(st_rad)


@pytest.mark.parametrize("rotation", [0.2, 2.0, 6.0])
def test_median_fallback_receives_legacy_window(rotation: float, monkeypatch) -> None:
    """With wotan missing, the scipy median size must derive from the
    legacy window (proves the median path routing is unchanged too)."""
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    import scipy.ndimage

    captured: dict = {}
    real_median = scipy.ndimage.median_filter

    def _fake_median(arr, size):
        captured["size"] = size
        return real_median(arr, size=size)

    monkeypatch.setattr(scipy.ndimage, "median_filter", _fake_median)
    t, flux = _curve()
    out, method = DetrendingEngine.detrend_with_method(t, flux, rotation)
    assert method == METHOD_SCIPY_MEDIAN
    dt = float(np.median(np.diff(t)))
    assert captured["size"] == _legacy_median_size(_legacy_rotation_window(rotation), dt)
    assert out.shape == flux.shape


# ---------------------------------------------------------------------------
# 3. detrend_report shape + provenance
# ---------------------------------------------------------------------------


def test_report_shape() -> None:
    """detrend_report returns exactly {method, window_days, window_source}."""
    t, flux = _curve()
    report = DetrendingEngine.detrend_report(t, flux, 2.0)
    assert set(report.keys()) == {"method", "window_days", "window_source"}
    assert report["method"] == METHOD_WOTAN_BIWEIGHT
    assert report["window_days"] == _legacy_rotation_window(2.0)
    assert report["window_source"] == WINDOW_SOURCE_ROTATION_SCALED


@pytest.mark.parametrize(
    ("rotation", "expected_source"),
    [
        (0.2, WINDOW_SOURCE_ROTATION_CLAMPED_MIN),  # raw 0.1 -> MIN
        (1.0, WINDOW_SOURCE_ROTATION_SCALED),  # raw 0.5 == MIN: clamp inactive
        (2.0, WINDOW_SOURCE_ROTATION_SCALED),  # raw 1.0 -> interior
        (3.0, WINDOW_SOURCE_ROTATION_SCALED),  # raw 1.5 -> MAX boundary
        (6.0, WINDOW_SOURCE_ROTATION_CLAMPED_MAX),  # raw 3.0 -> MAX
    ],
)
def test_report_rotation_sources(rotation: float, expected_source: str) -> None:
    t, flux = _curve()
    report = DetrendingEngine.detrend_report(t, flux, rotation)
    assert report["window_days"] == _legacy_rotation_window(rotation)
    assert report["window_source"] == expected_source


@pytest.mark.parametrize(
    ("st_rad", "expected_source"),
    [
        (0.1, WINDOW_SOURCE_ST_RAD_SMALL),
        (0.29, WINDOW_SOURCE_ST_RAD_SMALL),
        (0.3, WINDOW_SOURCE_ST_RAD_INTERPOLATED),
        (0.5, WINDOW_SOURCE_ST_RAD_INTERPOLATED),
        (0.79, WINDOW_SOURCE_ST_RAD_INTERPOLATED),
        (0.8, WINDOW_SOURCE_ST_RAD_LARGE),
        (1.2, WINDOW_SOURCE_ST_RAD_LARGE),
    ],
)
def test_report_st_rad_sources(st_rad: float, expected_source: str) -> None:
    t, flux = _curve()
    report = DetrendingEngine.detrend_report(t, flux, 2.0, st_rad=st_rad)
    assert report["window_days"] == _legacy_st_rad_window(st_rad)
    assert report["window_source"] == expected_source


def test_report_method_matches_with_method(monkeypatch) -> None:
    """Provenance tracks the estimator: the report method always equals
    the detrend_with_method label, on both the wotan and fallback paths."""
    t, flux = _curve()
    _, method = DetrendingEngine.detrend_with_method(t, flux, 2.0)
    assert DetrendingEngine.detrend_report(t, flux, 2.0)["method"] == method

    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    _, fallback_method = DetrendingEngine.detrend_with_method(t, flux, 2.0)
    assert fallback_method == METHOD_SCIPY_MEDIAN
    fallback_report = DetrendingEngine.detrend_report(t, flux, 2.0)
    assert fallback_report["method"] == METHOD_SCIPY_MEDIAN
    # Window provenance is estimator-independent: same rule, same value.
    assert fallback_report["window_days"] == _legacy_rotation_window(2.0)
    assert fallback_report["window_source"] == WINDOW_SOURCE_ROTATION_SCALED


def test_report_window_equals_estimator_window(monkeypatch) -> None:
    """The reported window_days is the value actually passed to wotan --
    provenance tied to reality, not recomputed decoration."""
    import wotan

    captured: dict = {}

    def _fake_flatten(time, flux, window_length, method, return_trend):
        captured["window_length"] = window_length
        flux = np.asarray(flux, dtype=np.float64)
        return flux, np.ones_like(flux)

    monkeypatch.setattr(wotan, "flatten", _fake_flatten)
    t, flux = _curve()
    report = DetrendingEngine.detrend_report(t, flux, 2.0)
    assert report["window_days"] == captured["window_length"]
    assert report["method"] == METHOD_WOTAN_BIWEIGHT


def test_report_fails_closed_when_required_and_missing(monkeypatch) -> None:
    """require_wotan=True propagates the fail-closed gate through report."""
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    t, flux = _curve()
    with pytest.raises(Exception, match="(?i)wotan"):
        DetrendingEngine.detrend_report(t, flux, 2.0, require_wotan=True)


# ---------------------------------------------------------------------------
# 4. backward compatibility: tuple shapes and method labels frozen
# ---------------------------------------------------------------------------


def test_tuple_shapes_backward_compatible() -> None:
    """detrend -> bare array; detrend_with_method -> 2-tuple. Unchanged."""
    t, flux = _curve()
    bare = DetrendingEngine.detrend(t, flux, 2.0)
    assert isinstance(bare, np.ndarray)
    assert bare.shape == flux.shape

    pair = DetrendingEngine.detrend_with_method(t, flux, 2.0)
    assert isinstance(pair, tuple) and len(pair) == 2
    arr, method = pair
    assert isinstance(arr, np.ndarray)
    assert method in (METHOD_WOTAN_BIWEIGHT, METHOD_SCIPY_MEDIAN, METHOD_NONE)
    np.testing.assert_array_equal(bare, arr)


def test_method_strings_unchanged() -> None:
    """P4-E must not relabel the estimator strings locked by existing tests."""
    assert METHOD_WOTAN_BIWEIGHT == "wotan:biweight"
    assert METHOD_SCIPY_MEDIAN == "scipy:median_filter"
    assert METHOD_NONE == "none"
