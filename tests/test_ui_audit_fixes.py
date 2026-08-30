"""Regression locks for the 2026-08-21 UI audit fixes.

Fix IDs (matching AUDIT_LOGBOOK entries and inline code comments):
- A4: app.py Candidate Ledger renders the pipeline's ``vetting_status``
  verbatim (helper ``_vetting_verdict_display``); SNR alone must never
  re-derive the verdict at display level.
- A5: the job-status fragment triggers exactly one full-app rerun when a
  job reaches a terminal state (helper ``_needs_terminal_rerun``).
- A6: a stale ``active_job_id`` (job lost from JOB_REGISTRY) renders a
  working "Clear Stale Job" button.
- A7: ``current_dataset_hash`` is written where the dataset becomes
  active (same ``generate_dataset_hash`` call the experiment log uses),
  and History restore namespaces restored params (``restored_param_*``)
  instead of blindly hijacking e.g. the Simulator's "snr".
- A8: stellar mass resolves via the ``stellar_mass`` -> ``st_mass`` ->
  1.0 fallback chain (archive rows carry ``st_mass``).
- A9: the secondary-eclipse verdict compares against the pipeline's
  adaptive ``secondary_eclipse_threshold_ppm``, not a hardcoded 800 ppm.
- A10: the Simulator N-body sweep consumes a real workspace frame
  (``active_dataframe`` / ``selected_kic``) published by the Detective
  analysis, and the banner copy states the data source honestly.
- U1: simulator planet dicts carry a stable ``uid``; per-planet widgets
  key off the uid, so removing a planet cannot leak widget state into
  the survivors.
- U2: "Reset to Default" evicts every per-planet widget key and the
  keyed SNR slider before restoring defaults.

Testing strategy: pure helpers are extracted at module level and tested
behaviorally; page interactions use streamlit AppTest (patterns from
tests/test_workbench_navigation.py / tests/test_fetched_analyze_button.py).
Where AppTest cannot drive the behavior deterministically (the A5
fragment rerun needs a live background job subprocess), a unit test on
the extracted helper plus a source-inspection lock is used and noted.
"""

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from astraeus.analysis.logging import generate_dataset_hash
from app import _needs_terminal_rerun, _vetting_verdict_display
from ui.pages.detective import (
    _build_workspace_planet_frame,
    _resolve_stellar_mass,
    _secondary_eclipse_status,
)
from ui.pages.simulator import (
    _PLANET_WIDGET_PREFIXES,
    _default_planet,
    _make_planet,
    _planet_widget_keys,
)


def _peek(at, key, default=None):
    """Safe session_state read (AppTest's wrapper raises on missing keys)."""
    try:
        return at.session_state[key]
    except KeyError:
        return default


def _navigate_to(at, feature):
    """Click the sidebar navigation button whose label contains *feature*."""
    btn = None
    for b in at.sidebar.get("button"):
        if feature in b.label:
            btn = b
            break
    assert btn is not None, f"{feature} sidebar button not found"
    btn.click().run()


def _find_button(at, key=None, label_contains=None):
    for b in at.get("button"):
        if key is not None and b.key == key:
            return b
        if label_contains is not None and label_contains in b.label:
            return b
    return None


def _find_slider(at, key):
    for s in at.slider:
        if s.key == key:
            return s
    return None


# ---------------------------------------------------------------------------
# Fix A4: verdict rendering helper
# ---------------------------------------------------------------------------
class TestFixA4VettingVerdictDisplay:
    def test_verified_is_green_bold_and_verbatim(self):
        color, label, bold = _vetting_verdict_display(
            {"vetting_status": "Verified Planet Candidate"}
        )
        assert (color, label, bold) == ("green", "Verified Planet Candidate", True)

    def test_atmospheric_occultation_variant_is_green_bold(self):
        color, label, bold = _vetting_verdict_display(
            {"vetting_status": "Verified Planet Candidate (Atmospheric Occultation Detected)"}
        )
        assert color == "green"
        assert label == "Verified Planet Candidate (Atmospheric Occultation Detected)"
        assert bold is True

    def test_eclipsing_binary_is_red_verbatim(self):
        for status in (
            "Eclipsing Binary Detected",
            "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)",
        ):
            color, label, bold = _vetting_verdict_display({"vetting_status": status})
            assert color == "red"
            assert label == status
            assert bold is False

    def test_ambiguous_and_vshape_are_orange_verbatim(self):
        for status in (
            "Ambiguous/False Positive",
            "V-Shaped False Positive Risk (Potential Grazing Binary)",
            "rejected",
        ):
            color, label, bold = _vetting_verdict_display({"vetting_status": status})
            assert color == "orange"
            assert label == status
            assert bold is False

    def test_missing_status_falls_back_to_low_snr_baseline(self):
        for cand in ({}, {"vetting_status": None}, "not-a-dict"):
            color, label, bold = _vetting_verdict_display(cand)
            assert (color, label, bold) == ("orange", "Low SNR Candidate Baseline", False)

    def test_high_snr_cannot_rederive_a_verified_verdict(self):
        """The display-level SNR bypass must stay dead: a high-SNR rejected
        candidate still renders the pipeline's own verdict."""
        color, label, _ = _vetting_verdict_display(
            {"vetting_status": "rejected", "snr": 99.0}
        )
        assert color == "orange" and label == "rejected"

    def test_ledger_renders_pipeline_verdict_end_to_end(self):
        """Behavioral lock: with a red EB candidate carrying SNR 20 (above
        the old 12.0 display threshold) and a green verified candidate
        carrying SNR 5, the ledger must color by vetting_status."""
        at = AppTest.from_file("app.py", default_timeout=90)
        at.run(timeout=90)
        assert not at.exception, f"App failed to load: {at.exception}"
        _navigate_to(at, "Discover")

        at.session_state["discovery_payload"] = {
            "target": "KIC TEST",
            "total_iterations_executed": 2,
            "candidates": [
                {"iteration": 1, "period": 10.0, "snr": 20.0,
                 "vetting_status": "Eclipsing Binary Detected",
                 "depth": 0.001, "duration": 0.1, "t0": 1.0},
                {"iteration": 2, "period": 12.0, "snr": 5.0,
                 "vetting_status": "Verified Planet Candidate",
                 "depth": 0.001, "duration": 0.1, "t0": 2.0},
            ],
        }
        at.run(timeout=90)

        markdowns = [m.value for m in at.markdown]
        assert any(":red[Eclipsing Binary Detected]" in m for m in markdowns), (
            "EB candidate (SNR 20) must render red from vetting_status — the "
            "SNR-only display bypass is back" if any(
                ":green[**Verified Planet Candidate**]" in m for m in markdowns
            ) else "EB verdict not rendered red"
        )
        assert any(":green[**Verified Planet Candidate**]" in m for m in markdowns), (
            "Verified candidate must render green/bold from vetting_status"
        )
        # The old SNR-derived fallback label must not appear for candidates
        # that carry a real verdict.
        assert not any("Low SNR Candidate Baseline" in m for m in markdowns)


# ---------------------------------------------------------------------------
# Fix A5: terminal-state rerun-once guard
# ---------------------------------------------------------------------------
class TestFixA5TerminalRerunGuard:
    def test_running_state_never_triggers(self):
        assert _needs_terminal_rerun("RUNNING", None, "job1") is False
        assert _needs_terminal_rerun("PENDING", None, "job1") is False

    def test_terminal_state_triggers_once_per_job(self):
        assert _needs_terminal_rerun("DONE", None, "job1") is True
        assert _needs_terminal_rerun("DONE", "job1", "job1") is False
        assert _needs_terminal_rerun("FAILED", "job1", "job1") is False
        assert _needs_terminal_rerun("CANCELLED", "job1", "job1") is False

    def test_new_job_after_previous_flag_retriggers(self):
        assert _needs_terminal_rerun("DONE", "job0", "job1") is True

    def test_app_source_wires_scope_app_rerun_and_flag(self):
        """Source lock (last resort): the fragment must call
        st.rerun(scope="app") guarded by the once-per-job flag. AppTest
        cannot drive a real background job subprocess deterministically."""
        from pathlib import Path

        src = (Path(__file__).resolve().parent.parent / "app.py").read_text(
            encoding="utf-8"
        )
        assert 'st.rerun(scope="app")' in src
        assert '_job_final_rerun_done_for' in src
        assert "_needs_terminal_rerun(state" in src


# ---------------------------------------------------------------------------
# Fix A6: Clear Stale Job button
# ---------------------------------------------------------------------------
def test_fix_a6_clear_stale_job_button_pops_active_job_id():
    at = AppTest.from_file("app.py", default_timeout=90)
    at.run(timeout=90)
    assert not at.exception, f"App failed to load: {at.exception}"

    # The job-status fragment renders on the Discover route.
    _navigate_to(at, "Discover")

    # A job id the registry lost (e.g. server restart) -> "Job not found".
    at.session_state["active_job_id"] = "lost-job-id"
    at.run(timeout=90)

    stale_btn = _find_button(at, key="clear_stale_lost-job-id")
    assert stale_btn is not None, (
        "'Clear Stale Job' button not rendered in the Job-not-found branch — "
        "active_job_id would be stuck forever"
    )
    stale_btn.click().run(timeout=90)

    assert _peek(at, "active_job_id") is None, "active_job_id was not cleared"
    # The Run button branch must be reachable again.
    assert _find_button(at, label_contains="Run Live Analysis") is not None


# ---------------------------------------------------------------------------
# Fix A7: dataset-hash wiring + namespaced restore
# ---------------------------------------------------------------------------
EXP_ID = "abcdef12-3456-7890-abcd-ef1234567890"


def _history_entry():
    metadata = {"dataset": "kepler-90-lightcurve", "cadence": "long"}
    return {
        "id": EXP_ID,
        "timestamp": "2026-08-21T00:00:00Z",
        "dataset_hash": generate_dataset_hash(metadata),
        "params": {"snr": 12.0, "period": 3.3},
        "metadata": metadata,
        "fig_paths": [],
    }


@pytest.fixture()
def patched_history(monkeypatch):
    entry = _history_entry()
    monkeypatch.setattr(
        "ui.pages.history.load_experiment_history", lambda: [entry]
    )
    return entry


def test_fix_a7_restore_namespaces_params_and_shows_summary(patched_history):
    at = AppTest.from_file("app.py", default_timeout=90)
    at.run(timeout=90)
    _navigate_to(at, "History")

    # Sentinel: the Simulator's live "snr" must NOT be hijacked.
    at.session_state["snr"] = 777
    at.session_state["current_dataset_hash"] = patched_history["dataset_hash"]
    at.run(timeout=90)

    restore_btn = _find_button(at, key=f"restore_{EXP_ID}")
    assert restore_btn is not None, "Restore button not rendered"
    restore_btn.click().run(timeout=90)

    # Params land under the restored_param_ namespace...
    assert _peek(at, "restored_param_snr") == 12.0
    assert _peek(at, "restored_param_period") == 3.3
    # ...and the live widget state is untouched.
    assert _peek(at, "snr") == 777

    successes = " ".join(s.value for s in at.success)
    assert "Restored 2 parameter(s)" in successes
    assert "snr" in successes and "period" in successes  # shows what was restored


def test_fix_a7_restore_warns_on_hash_mismatch(patched_history):
    at = AppTest.from_file("app.py", default_timeout=90)
    at.run(timeout=90)
    _navigate_to(at, "History")

    at.session_state["current_dataset_hash"] = "deadbeef" + "0" * 32
    at.run(timeout=90)

    restore_btn = _find_button(at, key=f"restore_{EXP_ID}")
    restore_btn.click().run(timeout=90)

    warnings = " ".join(w.value for w in at.warning)
    assert "mismatch" in warnings or "missing" in warnings
    assert _peek(at, "restored_param_snr") is None


def test_fix_a7_detective_stamps_dataset_hash_and_workspace_frame():
    """After a successful Detective analysis the session must carry the
    exact dataset hash the experiment log stores (fix A7) plus the real
    workspace frame / target for the Simulator (fix A10)."""
    rng = np.random.default_rng(42)
    n_points = 1000
    time_arr = np.linspace(0, 30, n_points)
    flux_arr = 1.0 + rng.normal(0, 0.001, n_points)
    period = 14.45
    phases = time_arr % period
    in_transit = (phases < 0.1) | (phases > period - 0.1)
    flux_arr[in_transit] -= 0.005
    meta = {
        "pl_name": "Kepler-90",
        "orbital_period": period,
        "stellar_radius": 1.2,
        "transit_depth": 0.005,
        "stellar_mass": 1.2,
    }

    at = AppTest.from_file("app.py", default_timeout=120)
    at.run(timeout=120)
    assert not at.exception, f"App failed to load: {at.exception}"
    _navigate_to(at, "Detective")

    # Bypass the MAST fetch (same pattern as tests/test_fetched_analyze_button.py).
    for inp in at.text_input:
        if inp.key == "search_target":
            inp.set_value("Kepler-90").run(timeout=120)
            break
    at.session_state["fetched_target_data"] = {
        "status": "success",
        "metadata": meta,
        "time": time_arr,
        "flux": flux_arr,
        "flux_err": np.full(time_arr.shape, 0.001),
        "bridged_mission": "Kepler",
    }
    at.session_state["active_metadata"] = meta
    at.run(timeout=120)

    analyze_btn = _find_button(at, key="detective_analyze_fetched")
    assert analyze_btn is not None
    analyze_btn.click().run(timeout=120)

    # Fix A7: hash matches generate_dataset_hash of the SAME metadata the
    # detector handed to save_experiment_log.
    stamped = _peek(at, "current_dataset_hash")
    assert stamped == generate_dataset_hash(meta), (
        "current_dataset_hash must be generate_dataset_hash(metadata) of the "
        "analysis metadata so History restore can validate the dataset"
    )

    # Fix A10: workspace frame + target derived from real analysis output.
    frame = _peek(at, "active_dataframe")
    assert frame is not None and not frame.empty, (
        "active_dataframe must be published from real analysis candidates"
    )
    assert {"period_days", "eccentricity", "radius"} <= set(frame.columns)
    # BLS period-grid resolution is coarser than the injected period; the
    # recovered candidate just has to be the same signal.
    assert abs(float(frame.iloc[0]["period_days"]) - period) < 0.5
    assert _peek(at, "selected_kic") == "Kepler-90"

    # Fix A9 (end-to-end): the diagnostic card surfaces the pipeline's
    # adaptive threshold (and its mode) rather than a silent 800 ppm.
    markdowns = " ".join(m.value for m in at.markdown)
    assert "Threshold:" in markdowns and "ppm" in markdowns


# ---------------------------------------------------------------------------
# Fix A8: stellar-mass fallback chain
# ---------------------------------------------------------------------------
class TestFixA8StellarMassFallback:
    def test_prefers_legacy_stellar_mass_key(self):
        assert _resolve_stellar_mass({"stellar_mass": 0.8}) == 0.8

    def test_falls_back_to_archive_st_mass(self):
        assert _resolve_stellar_mass({"st_mass": 0.0898}) == pytest.approx(0.0898)

    def test_none_stellar_mass_falls_through_to_st_mass(self):
        assert _resolve_stellar_mass({"stellar_mass": None, "st_mass": 1.2}) == 1.2

    def test_falsy_zero_stellar_mass_falls_through(self):
        assert _resolve_stellar_mass({"stellar_mass": 0, "st_mass": 0.5}) == 0.5

    def test_missing_keys_default_to_solar_mass(self):
        assert _resolve_stellar_mass({}) == 1.0
        assert _resolve_stellar_mass(None) == 1.0


# ---------------------------------------------------------------------------
# Fix A9: adaptive secondary-eclipse threshold
# ---------------------------------------------------------------------------
class TestFixA9SecondaryEclipseStatus:
    def test_low_snr_passes_regardless_of_depth(self):
        assert _secondary_eclipse_status(2.0, 0.05, 800.0) == "Pass"

    def test_adaptive_threshold_above_legacy_800ppm_passes(self):
        """Depth 1200 ppm sits between the hardcoded 800 ppm and a
        physically-derived 1500 ppm threshold: must PASS with the adaptive
        value (the old hardcoded comparison wrongly failed it)."""
        assert (
            _secondary_eclipse_status(6.0, 0.0012, 1500.0)
            == "Pass (Atmospheric Occultation Detected)"
        )

    def test_depth_above_adaptive_threshold_fails(self):
        assert _secondary_eclipse_status(6.0, 0.0020, 1500.0) == "Fail (Eclipse Detected)"

    def test_fallback_800ppm_boundary(self):
        assert _secondary_eclipse_status(5.0, 0.0007, 800.0) == (
            "Pass (Atmospheric Occultation Detected)"
        )
        assert _secondary_eclipse_status(5.0, 0.0009, 800.0) == "Fail (Eclipse Detected)"

    def test_detective_reads_threshold_from_result_dict(self):
        """Source lock (last resort): the page must pull the threshold out
        of the pipeline result dict instead of a literal."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parent.parent / "ui" / "pages" / "detective.py"
        ).read_text(encoding="utf-8")
        assert "res.get('secondary_eclipse_threshold_ppm', 800.0)" in src
        assert "res.get('secondary_eclipse_threshold_mode')" in src
        assert "< 0.0008" not in src


# ---------------------------------------------------------------------------
# Fix A10 helper: workspace planet frame from real candidates
# ---------------------------------------------------------------------------
class TestFixA10WorkspacePlanetFrame:
    def test_builds_frame_from_multi_planet_results(self):
        results = [
            {"period_days": 3.5, "eccentricity": 0.05, "planet_radius_earth": 1.2},
            {"period": 8.1, "planet_radius_earth": 2.4},  # legacy period key
        ]
        frame = _build_workspace_planet_frame(results)
        assert list(frame["period_days"]) == [3.5, 8.1]
        assert list(frame["eccentricity"]) == [0.05, 0.0]
        assert list(frame["radius"]) == [1.2, 2.4]

    def test_empty_or_junk_results_return_none_not_fake_data(self):
        assert _build_workspace_planet_frame(None) is None
        assert _build_workspace_planet_frame([]) is None
        assert _build_workspace_planet_frame([{"snr": 9.9}]) is None
        assert _build_workspace_planet_frame(["junk", 42]) is None


# ---------------------------------------------------------------------------
# Fix U1: stable per-planet uids
# ---------------------------------------------------------------------------
class TestFixU1PlanetUids:
    def test_make_planet_assigns_unique_nonempty_uid(self):
        planets = [_make_planet(f"P{i}", 0.1, 3.0, 0.0, 88.5) for i in range(20)]
        uids = [p["uid"] for p in planets]
        assert all(isinstance(uid, str) and uid for uid in uids)
        assert len(set(uids)) == len(uids)

    def test_default_planet_carries_uid(self):
        assert _default_planet()["uid"]

    def test_widget_keys_are_uid_scoped(self):
        keys = _planet_widget_keys("cafe01")
        assert keys == {prefix + "cafe01" for prefix in _PLANET_WIDGET_PREFIXES}
        for expected in ("rr_cafe01", "pd_cafe01", "ecc_cafe01", "inc_cafe01",
                         "edit_name_cafe01", "remove_cafe01"):
            assert expected in keys

    def test_simulator_source_binds_widgets_to_uid_not_index(self):
        """Source lock (supplement): sliders/buttons must key off uid."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parent.parent / "ui" / "pages" / "simulator.py"
        ).read_text(encoding="utf-8")
        assert 'key=f"rr_{uid}"' in src
        assert 'key=f"rr_{i}"' not in src
        assert 'key=f"remove_{uid}"' in src
        assert 'key=f"remove_{i}"' not in src

    def test_remove_planet_does_not_leak_slider_state_to_survivor(self):
        """Behavioral lock for the original bug: set planet 1's radius
        slider to 0.15, remove it, and confirm planet 2's slider still
        shows planet 2's own value (pre-fix it inherited 0.15 via rr_0)."""
        at = AppTest.from_file("app.py", default_timeout=120)
        at.run(timeout=120)
        assert not at.exception, f"App failed to load: {at.exception}"

        planets = at.session_state.multi_planets
        assert len(planets) == 1
        uid0 = planets[0]["uid"]

        add_btn = _find_button(at, key="simulator_add_planet")
        add_btn.click().run(timeout=120)
        planets = at.session_state.multi_planets
        assert len(planets) == 2
        uid1 = planets[1]["uid"]
        assert uid1 != uid0, "each planet dict must carry a unique stable uid"

        rr0 = _find_slider(at, key=f"rr_{uid0}")
        assert rr0 is not None, f"slider rr_{uid0} not found"
        rr0.set_value(0.15).run(timeout=120)

        remove_btn = _find_button(at, key=f"remove_{uid0}")
        assert remove_btn is not None
        remove_btn.click().run(timeout=120)

        planets = at.session_state.multi_planets
        assert len(planets) == 1 and planets[0]["uid"] == uid1

        rr1 = _find_slider(at, key=f"rr_{uid1}")
        assert rr1 is not None
        assert rr1.value == pytest.approx(0.05), (
            "surviving planet inherited the removed planet's slider state — "
            "per-planet widgets are index-keyed again (fix U1 regressed)"
        )


# ---------------------------------------------------------------------------
# Fix U2: Reset restores SNR and evicts persisted widget state
# ---------------------------------------------------------------------------
def test_fix_u2_reset_restores_snr_and_pops_planet_widget_state():
    at = AppTest.from_file("app.py", default_timeout=120)
    at.run(timeout=120)
    assert not at.exception, f"App failed to load: {at.exception}"

    uid0 = at.session_state.multi_planets[0]["uid"]

    snr_slider = _find_slider(at, key="simulator_snr")
    assert snr_slider is not None, "SNR slider must carry an explicit key for Reset"
    snr_slider.set_value(123).run(timeout=120)
    assert at.session_state.snr == 123

    rr0 = _find_slider(at, key=f"rr_{uid0}")
    rr0.set_value(0.19).run(timeout=120)

    reset_btn = _find_button(at, key="simulator_reset_to_default")
    reset_btn.click().run(timeout=120)

    # SNR default restored in session state AND on the widget itself (the
    # old unkeyed slider kept mirroring the stale value).
    assert at.session_state.snr == 200
    snr_after = _find_slider(at, key="simulator_snr")
    assert snr_after.value == 200

    # Planet list reset with a FRESH uid, and every OLD widget key evicted
    # so nothing can override the new defaults. (The new planet's own keys
    # legitimately reappear once its widgets render.)
    planets = at.session_state.multi_planets
    assert len(planets) == 1
    new_uid = planets[0]["uid"]
    assert new_uid != uid0
    for stale_key in (f"rr_{uid0}", f"pd_{uid0}", f"ecc_{uid0}", f"inc_{uid0}",
                      f"edit_name_{uid0}", f"remove_{uid0}"):
        assert _peek(at, stale_key) is None, f"stale widget key {stale_key} survived Reset"

    rr_new = _find_slider(at, key=f"rr_{new_uid}")
    assert rr_new.value == pytest.approx(0.10), "reset planet must use default radius ratio"
