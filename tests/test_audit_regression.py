"""Regression tests for the 2026-08-21 full-codebase audit criticals.

Locks the following fixes (see AUDIT_LOGBOOK.md):
- C1: pscomppars ``pl_trandep`` is ALWAYS percent -> meta["transit_depth"]
  must be a fraction and meta["pl_trandep"] must stay percent.
- C2: curated KIC table must map Kepler-4 / Kepler-11 to their real KICs.
- M6: target->TIC prefix resolution must respect name boundaries
  ("Kepler-9" must NOT resolve to Kepler-90's star).
- C3: app.py "Run Live Analysis" must pass an astropy Quantity duration.
- C4: astraeus.dashboard.services.action_deck must be importable and its
  export_retrieval_report must produce a PDF artifact.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import astraeus.core.nasa_archive as nasa_archive_module
from astraeus.core.nasa_archive import NASAExoplanetArchive


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _archive_row(**overrides):
    row = {
        "pl_name": "TRAPPIST-1 b",
        "pl_orbper": 1.51087081,
        "pl_orbpererr1": 1e-6,
        "st_rad": 0.1192,
        "st_raderr1": 0.0033,
        "st_lum": -2.59,
        "st_teff": 2566.0,
        "st_mass": 0.0898,
        "sy_jmag": 11.354,
        "pl_trandep": 0.7378,   # PERCENT, as pscomppars stores it
        "pl_ratror": None,
    }
    row.update(overrides)
    return [row]


@pytest.fixture()
def patched_tap(monkeypatch):
    """Replace the TAP HTTP call with an in-memory row."""
    holder = {"payload": _archive_row()}

    def _fake_get(url, params=None, timeout=None):
        return _FakeResponse(holder["payload"])

    monkeypatch.setattr(nasa_archive_module.requests, "get", _fake_get)
    return holder


class TestC1TransitDepthUnits:
    def test_shallow_depth_percent_converted_to_fraction(self, patched_tap):
        """TRAPPIST-1 b: archive says 0.7378 percent -> fraction 0.007378.

        The old `>= 1.0` heuristic left this unconverted (100x too large).
        """
        meta, err = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert err is None
        assert meta["transit_depth"] == pytest.approx(0.007378, rel=1e-9)
        # ppm rendering contract (ui/pages/detective.py multiplies by 1e6)
        assert meta["transit_depth"] * 1e6 == pytest.approx(7378.0, rel=1e-3)

    def test_pl_trandep_key_stays_percent_for_detection_crosscheck(self, patched_tap):
        """analysis/detection.py divides meta['pl_trandep'] by 100 — the key
        must therefore remain in percent."""
        meta, _ = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert meta["pl_trandep"] == pytest.approx(0.7378, rel=1e-9)

    def test_deep_depth_also_converted(self, patched_tap):
        patched_tap["payload"] = _archive_row(pl_trandep=1.5)
        meta, _ = NASAExoplanetArchive.fetch_metadata("HD 209458 b")
        assert meta["transit_depth"] == pytest.approx(0.015, rel=1e-9)
        assert meta["pl_trandep"] == pytest.approx(1.5, rel=1e-9)

    def test_ratror_fallback_emits_fraction_and_percent(self, patched_tap):
        patched_tap["payload"] = _archive_row(pl_trandep=None, pl_ratror=0.05)
        meta, _ = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert meta["transit_depth_source"] == "pl_ratror_squared"
        assert meta["transit_depth"] == pytest.approx(0.0025, rel=1e-9)
        assert meta["pl_trandep"] == pytest.approx(0.25, rel=1e-9)


class TestC2CuratedKICTable:
    def test_kepler4_maps_to_real_kic(self):
        from astraeus.core.lightkurve_client import _TARGET_TIC_TABLE
        # SIMBAD-verified: Kepler-4 = KIC 11853905. The old entry held
        # 006541920, which is KEPLER-11's star.
        assert _TARGET_TIC_TABLE["Kepler-4"] == "011853905"

    def test_kepler11_maps_to_real_kic(self):
        from astraeus.core.lightkurve_client import _TARGET_TIC_TABLE
        assert _TARGET_TIC_TABLE["Kepler-11"] == "006541920"

    def test_kepler_table_ids_are_nine_digits(self):
        """The cache-first FITS path rejects resolved KICs shorter than 9
        digits, so every Kepler entry must be zero-padded to 9."""
        from astraeus.core.lightkurve_client import _TARGET_TIC_TABLE
        for host, tic in _TARGET_TIC_TABLE.items():
            assert tic.isdigit(), f"{host} -> {tic!r}"
            if host.startswith("Kepler"):
                assert len(tic) == 9, f"{host} -> {tic!r} (must be 9 digits)"


class TestM6TICResolutionBoundaries:
    def test_exact_host_resolves(self):
        from astraeus.core.lightkurve_client import _resolve_target_to_tic
        assert _resolve_target_to_tic("Kepler-90") == "011442793"

    def test_planet_letter_suffix_resolves_to_host(self):
        from astraeus.core.lightkurve_client import _resolve_target_to_tic
        assert _resolve_target_to_tic("Kepler-90 b") == "011442793"
        assert _resolve_target_to_tic("Kepler-11 d") == "006541920"

    def test_prefix_collision_rejected(self):
        """'Kepler-9' (a different star, TrES-2's host) must not silently
        resolve to Kepler-90's cached FITS files."""
        from astraeus.core.lightkurve_client import _resolve_target_to_tic
        assert _resolve_target_to_tic("Kepler-9") == ""
        assert _resolve_target_to_tic("Kepler-1") == ""
        assert _resolve_target_to_tic("Kepler-2") == ""

    def test_unknown_target_returns_empty(self):
        from astraeus.core.lightkurve_client import _resolve_target_to_tic
        assert _resolve_target_to_tic("WASP-999 b") == ""
        assert _resolve_target_to_tic("") == ""


class TestC3RunLiveAnalysisQuantity:
    def test_app_passes_quantity_duration(self):
        """The demo scenario duration must be an astropy Quantity; a bare
        float crashed _generate_time_grid on every button click."""
        app_source = Path(__file__).resolve().parent.parent / "app.py"
        src = app_source.read_text(encoding="utf-8")
        assert "SyntheticTransitScenario(duration=100.0 * u.day)" in src, (
            "app.py must construct SyntheticTransitScenario with an astropy "
            "Quantity duration (bare float raises AttributeError at runtime)"
        )
        assert "from astropy import units as u" in src

    def test_scenario_accepts_quantity_and_produces_series(self):
        from astropy import units as u
        from astraeus.simulation.synthetic import (
            SyntheticTransitScenario,
            generate_synthetic_transit_series,
        )
        series = generate_synthetic_transit_series(
            SyntheticTransitScenario(duration=100.0 * u.day)
        )
        assert series.time_days is not None and len(series.time_days) > 0


class TestC4ActionDeckImportAndExport:
    def test_action_deck_imports_cleanly(self):
        import astraeus.dashboard.services.action_deck as action_deck

        assert hasattr(action_deck, "export_retrieval_report")

    def test_export_retrieval_report_writes_pdf(self, tmp_path, monkeypatch):
        import astraeus.dashboard.services.action_deck as action_deck

        monkeypatch.chdir(tmp_path)
        summary = {
            "params": {"radius_ratio": 0.1, "inclination_deg": 89.0, "u1": 0.4, "u2": 0.2},
            "uncertainties": {},
            "residuals": {"rms": 1e-4, "mean": 0.0, "std": 1e-4},
        }
        out = action_deck.export_retrieval_report(
            summary, {"summary": "test"}, "pdf"
        )
        path = Path(out)
        assert path.exists() and path.stat().st_size > 0
        assert path.suffix == ".pdf"

    def test_export_rejects_unsupported_format(self, tmp_path, monkeypatch):
        import astraeus.dashboard.services.action_deck as action_deck

        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError):
            action_deck.export_retrieval_report({"params": {}}, {}, "docx")


class TestC5ChaosSuiteCollectedByPytest:
    def test_chaos_module_defines_pytest_tests(self):
        chaos_source = (
            Path(__file__).resolve().parent / "test_chaos_integration_suite.py"
        ).read_text(encoding="utf-8")
        assert "def test_chaos_vector(" in chaos_source, (
            "chaos suite lost its pytest shim — the adversarial vectors are "
            "invisible to CI again"
        )
