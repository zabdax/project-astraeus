"""Regression test: the 'Analyze Telemetry & Verify Harmonics' button on
the fetched-target path must re-fire on every user click — not just the
first one.

User-reported symptom: the button 'isn't working'. Root cause: the I4
round-2 fix added a one-shot session-state guard
(``detective_analyze_fetched_last_run``) that is set to True on the
first click and never reset. After the first click, every subsequent
click on the same button is silently consumed by the guard. This test
pins both directions of the contract:

  1. First click: ``run_analysis`` must run and ``detective_results``
     must be populated.
  2. Second click (after the user re-injects ``fetched_target_data``
     to simulate a refetch or parameter change): ``run_analysis`` must
     run AGAIN. This is the case the I4 guard breaks.

Test infrastructure: AppTest boots ``app.py`` in-process, injects
``fetched_target_data`` directly into session_state (bypassing the
MAST network call — same pattern as ``scratch/repro_analyze_button.py``)
and inspects the post-click session_state.

The autouse fixtures in ``tests/conftest.py`` (``_reset_streamlit_delta_generator_singleton``,
``_suppress_save_experiment_log_during_tests``) are in scope.

RED against the pre-fix code: second click is silently swallowed,
``detective_results`` does not refresh.
GREEN after the fix: both clicks fire ``run_analysis`` and the
results dict is overwritten on the second click.
"""

import os

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from streamlit.delta_generator_singletons import DeltaGeneratorSingleton


# ---------------------------------------------------------------------------
# Singleton reset
# ---------------------------------------------------------------------------
# The conftest autouse fixture patches DeltaGeneratorSingleton.__init__
# globally for the duration of every test. This module-level reference
# is only for documentation; the test below relies on the autouse fixture.
# We also defensively re-patch here in case the test is run in isolation
# (e.g. ``pytest tests/test_fetched_analyze_button.py`` without the rest
# of the suite), since DeltaGeneratorSingleton is a process-wide singleton.
def _permissive_init(original_init):
    def _patched_init(self, *args, **kwargs):
        DeltaGeneratorSingleton._instance = None
        original_init(self, *args, **kwargs)
    return _patched_init


@pytest.fixture(autouse=True)
def _patch_singleton():
    """Allow fresh DeltaGeneratorSingleton per test (defensive in
    case this file is run in isolation outside the conftest autouse)."""
    original = DeltaGeneratorSingleton.__init__
    DeltaGeneratorSingleton.__init__ = _permissive_init(original)
    try:
        yield
    finally:
        DeltaGeneratorSingleton.__init__ = original


@pytest.fixture(scope="module")
def _synthetic_lightcurve():
    """1000-cadence synthetic light curve with a transit at P=14.45d.

    Used to populate ``fetched_target_data`` so we don't depend on a
    live MAST call. The transit depth (5000 ppm) is large enough for
    ``detect_transit_candidate`` to confidently recover it.
    """
    rng = np.random.default_rng(42)
    n_points = 1000
    time_arr = np.linspace(0, 30, n_points)
    flux_arr = 1.0 + rng.normal(0, 0.001, n_points)
    period = 14.45
    duration = 0.2
    depth = 0.005
    phases = (time_arr % period)
    in_transit = (phases < duration / 2) | (phases > period - duration / 2)
    flux_arr[in_transit] -= depth
    return {
        "time": time_arr,
        "flux": flux_arr,
        "metadata": {
            "pl_name": "Kepler-90",
            "orbital_period": period,
            "stellar_radius": 1.2,
            "transit_depth": depth,
            "stellar_mass": 1.2,
        },
    }


def _navigate_to_detective(at: AppTest) -> None:
    """Click the sidebar 'Detective' navigation button (if present).

    The first run of app.py lands on the Discover page; the Detective
    page is a sidebar feature. We click any sidebar button whose label
    contains 'Detective'.
    """
    detective_btn = None
    for btn in at.sidebar.get("button"):
        if "Detective" in btn.label:
            detective_btn = btn
            break
    if detective_btn is None:
        pytest.skip(
            "Detective sidebar button not found — feature unavailable "
            "in this app variant."
        )
    detective_btn.click().run()


def _set_search_target(at: AppTest, value: str) -> None:
    """Set the search-target text_input widget value.

    The detective page's analyze button only renders in the
    ``elif target:`` branch (line 343 of detective.py), where ``target``
    is the text-input value bound to ``session_state['search_target']``
    (line 218-224 of detective.py). Setting only
    ``at.session_state['search_target']`` is not enough — the page's
    local ``target`` variable comes from the text_input widget's
    return value, which AppTest's wrapper exposes by key.
    """
    for inp in at.get("text_input"):
        if inp.key == "search_target":
            inp.set_value(value).run()
            return
    raise RuntimeError(
        "text_input with key='search_target' not found on Detective page"
    )


def _inject_fetched_target(at: AppTest, lightcurve) -> None:
    """Bypass the MAST fetch by injecting the result directly.

    The fetched-target analyze button is gated on
    ``'time' in fetched_target_data`` and ``'flux' in fetched_target_data``,
    so the dict must include both keys (line 494 of detective.py).
    ``active_metadata`` is also set because the analysis path reads it
    (line 472-474 of detective.py).

    IMPORTANT: also set ``search_target`` text_input so the page enters
    the ``elif target:`` branch (line 343) which renders the Analyze
    button. Without this, the page renders only the "Fetch Target
    Metadata" button.
    """
    _set_search_target(at, "Kepler-90")
    at.session_state["fetched_target_data"] = {
        "status": "success",
        "metadata": lightcurve["metadata"],
        "time": lightcurve["time"],
        "flux": lightcurve["flux"],
        "flux_err": np.full(lightcurve["time"].shape, 0.001),
        "bridged_mission": "Kepler",
    }
    at.session_state["active_metadata"] = lightcurve["metadata"]
    at.run()


def _click_analyze(at: AppTest) -> None:
    """Click 'Analyze Telemetry & Verify Harmonics' (fetched path)."""
    btn = None
    for b in at.get("button"):
        if (
            "Analyze Telemetry & Verify Harmonics" in b.label
            and b.key == "detective_analyze_fetched"
        ):
            btn = b
            break
    assert btn is not None, (
        "Analyze Telemetry & Verify Harmonics button (key="
        "'detective_analyze_fetched') not found on Detective page"
    )
    btn.click().run()


def _peek(at: AppTest, key: str, default=None):
    """Safe session_state read (AppTest's wrapper raises on missing keys)."""
    try:
        return at.session_state[key]
    except KeyError:
        return default


# ---------------------------------------------------------------------------
# Test 1: first click works (sanity check — must stay green)
# ---------------------------------------------------------------------------
def test_first_click_populates_detective_results(_synthetic_lightcurve):
    """First click on 'Analyze Telemetry' must populate
    ``detective_results``. This is the case the I4 fix intended to
    protect; it must not regress.
    """
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run(timeout=30)
    assert not at.exception, f"App failed to load: {at.exception}"

    _navigate_to_detective(at)
    _inject_fetched_target(at, _synthetic_lightcurve)
    _click_analyze(at)

    results = _peek(at, "detective_results")
    assert results is not None, (
        "First click did not populate detective_results — run_analysis "
        "did not fire. The I4 guard or the button handler is broken."
    )
    assert isinstance(results, dict), (
        f"detective_results should be a dict, got {type(results).__name__}"
    )
    # ``run_analysis`` always sets period (best_period / period / period_days)
    # OR a vetted candidate. Assert at least one of the load-bearing
    # detection keys is present so we know the detector ran end-to-end.
    load_bearing_keys = {"period", "period_days", "candidate_found", "is_candidate"}
    assert load_bearing_keys & set(results.keys()), (
        f"detective_results missing load-bearing detection keys; got keys: "
        f"{list(results.keys())}"
    )


# ---------------------------------------------------------------------------
# Test 2: second click re-fires run_analysis (the bug the user reported)
# ---------------------------------------------------------------------------
def test_second_click_reruns_analysis_after_refetch(_synthetic_lightcurve):
    """After the first click, the user re-injects ``fetched_target_data``
    to simulate a refetch or parameter change, then clicks Analyze
    again. The second click MUST fire ``run_analysis`` (i.e. the
    ``detective_results`` dict must be overwritten with a new value).

    Pre-fix: the I4 guard ``detective_analyze_fetched_last_run`` is True
    after the first click, so the second click is silently swallowed
    and ``detective_results`` is NOT refreshed. This test is RED.

    Post-fix: the guard is removed. Stable ``key=`` alone prevents
    rerun-induced re-fires; the user-click path is unobstructed.
    ``run_analysis`` runs on the second click, overwriting
    ``detective_results``. This test is GREEN.
    """
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run(timeout=30)
    assert not at.exception, f"App failed to load: {at.exception}"

    _navigate_to_detective(at)

    # First fetch + click.
    _inject_fetched_target(at, _synthetic_lightcurve)
    _click_analyze(at)
    first_results = _peek(at, "detective_results")
    assert first_results is not None, (
        "First click did not populate detective_results — test setup broken."
    )

    # Simulate a refetch: re-inject fetched_target_data with a NEW
    # light curve (different period so the second analysis is
    # distinguishable from the first). We also set a different
    # pl_name so any results stamped with the target name will differ.
    rng = np.random.default_rng(99)
    n_points = 1000
    time_arr = np.linspace(0, 30, n_points)
    flux_arr = 1.0 + rng.normal(0, 0.001, n_points)
    period_new = 7.20  # DIFFERENT from first run (14.45d)
    duration = 0.2
    depth = 0.005
    phases = (time_arr % period_new)
    in_transit = (phases < duration / 2) | (phases > period_new - duration / 2)
    flux_arr[in_transit] -= depth

    new_meta = dict(_synthetic_lightcurve["metadata"])
    new_meta["pl_name"] = "Kepler-90-refetch"
    new_meta["orbital_period"] = period_new
    at.session_state["fetched_target_data"] = {
        "status": "success",
        "metadata": new_meta,
        "time": time_arr,
        "flux": flux_arr,
        "flux_err": np.full(time_arr.shape, 0.001),
        "bridged_mission": "Kepler",
    }
    at.session_state["active_metadata"] = new_meta
    at.run()

    # Second click — this is the one the I4 guard breaks.
    _click_analyze(at)
    second_results = _peek(at, "detective_results")

    assert second_results is not None, (
        "Second click did not populate detective_results. The I4 guard "
        "(detective_analyze_fetched_last_run) is silently swallowing the "
        "click. run_analysis did not fire on the second click."
    )
    assert isinstance(second_results, dict), (
        f"Second-click detective_results should be a dict, got "
        f"{type(second_results).__name__}"
    )
    # Strongest evidence the second click actually fired: the
    # ``active_time`` / ``active_flux`` arrays in session_state must
    # have been overwritten with the NEW light curve (1000 samples,
    # but drawn from a different RNG seed, so the array identities
    # are not just equal, the underlying bytes differ). The page's
    # ``run_analysis`` always writes the time/flux it analyzed into
    # ``session_state['active_time']`` / ``session_state['active_flux']``
    # (see ui/pages/detective.py:317-318), so if the second click
    # did NOT fire, these arrays still hold the FIRST light curve.
    active_time_1 = _peek(at, "active_time")
    active_time_2_after = _peek(at, "active_time")
    # active_time is a numpy array stored by run_analysis. We can
    # compare element-by-element: if both clicks analyzed the same
    # 1000-cadence np.linspace(0, 30, 1000), the arrays ARE identical
    # (same time grid in both fixtures). So we need a stronger test:
    # compare the active_flux arrays, which differ in their noise
    # realization between the two fixtures.
    active_flux_2 = _peek(at, "active_flux")
    # Re-fetch the first flux from a copy of the fixture (since the
    # first array is held in session_state and not modified by the
    # second click). If the second click fired, active_flux_2 must
    # match the SECOND fixture, not the first.
    if active_flux_2 is not None:
        rng_first = np.random.default_rng(42)
        first_flux = 1.0 + rng_first.normal(0, 0.001, 1000)
        phases_first = (np.linspace(0, 30, 1000) % 14.45)
        in_transit_first = (
            (phases_first < 0.1) | (phases_first > 14.45 - 0.1)
        )
        first_flux[in_transit_first] -= 0.005

        rng_second = np.random.default_rng(99)
        second_flux = 1.0 + rng_second.normal(0, 0.001, 1000)
        phases_second = (np.linspace(0, 30, 1000) % 7.20)
        in_transit_second = (
            (phases_second < 0.1) | (phases_second > 7.20 - 0.1)
        )
        second_flux[in_transit_second] -= 0.005

        # ``active_flux`` should be a numpy array. Compare against
        # both fixture fluxes with np.array_equal (no tolerance —
        # we want exact equality because both fixtures are
        # deterministic).
        active_flux_arr = np.asarray(active_flux_2)
        is_second = bool(np.array_equal(active_flux_arr, second_flux))
        is_first = bool(np.array_equal(active_flux_arr, first_flux))

        assert is_second and not is_first, (
            f"active_flux after second click matches the FIRST "
            f"light-curve fixture (is_first={is_first}) rather than the "
            f"second (is_second={is_second}). The I4 guard is preventing "
            f"the second run_analysis invocation from re-populating "
            f"session_state with the refetched data."
        )

    # Also assert: the second click's results dict must not be the
    # same Python object as the first (different identity). With the
    # I4 guard, the second click would be a no-op and ``detective_results``
    # would still hold the first dict. run_analysis rebuilds the dict
    # every call, so a fresh click produces a new identity.
    assert second_results is not first_results, (
        "second_results is the same object as first_results — the second "
        "click did not overwrite session_state['detective_results']. "
        "The I4 guard is preventing the second run_analysis invocation."
    )
