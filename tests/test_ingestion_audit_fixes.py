"""Offline regression tests for the 2026-08-21 data-ingestion audit fixes.

Locks the following fixes (all OFFLINE — requests / lightkurve seams are
monkeypatched; no test in this module makes a network call):

  1. lightkurve_client Kepler loop: downloading must iterate ALL
     ``_MAX_DOWNLOAD_SEGMENTS`` segments (the old ``if lc_list: break``
     stopped after the FIRST successful quarter).
  2. lightkurve_client Kepler retry loop: a timed-out ``row.download()``
     must be retried (the stray unconditional ``break`` killed retries).
  3. ``_call_with_timeout`` timeouts are distinguishable (``_TIMEOUT_SENTINEL``)
     and ``download_pipeline`` translates them into ``"Network Timeout"``.
  4. BJD epoch offsets come from ``astraeus.core.time_units`` (K2 would be
     wrong by 2167 days under the old inline ternary).
  5. HD/HIP/GJ designations are SPACE-separated in pscomppars; both
     separator forms are tried as candidates.
  6. Hostname queries order by ``pl_orbper asc`` and record the ROW's
     ``pl_name`` (deterministic innermost planet).
  7. Null ``pl_orbper`` never adopts the ``pl_orbpererr1`` ERROR column.
  8. Bridge classifier's final else is "Download failed".
  9. Per-mission errors are accumulated (a real TESS diagnostic survives a
     silent Kepler attempt).
  10. ``load_config`` catches OSError in addition to JSONDecodeError.
  11. Fixture recorder uses the real ``?uri=`` contract and the actual
      response status in fixture filenames.
"""
from __future__ import annotations

import inspect
import time

import numpy as np
import pytest

import astraeus.core.clients._net as net_module
import astraeus.core.lightkurve_client as lkc_module
import astraeus.core.nasa_archive as nasa_archive_module
from astraeus.core.config import load_config
from astraeus.core.ingestion import RemoteDiscoveryEngine
from astraeus.core.lightkurve_client import (
    _MAX_DOWNLOAD_SEGMENTS,
    _TIMEOUT_SENTINEL,
    LightkurveClient,
)
from astraeus.core.nasa_archive import NASAExoplanetArchive


# ---------------------------------------------------------------------------
# Shared fakes (patterns follow tests/test_audit_regression.py::patched_tap)
# ---------------------------------------------------------------------------


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
        "pl_trandep": 0.7378,
        "pl_ratror": None,
    }
    row.update(overrides)
    return [row]


@pytest.fixture()
def recording_tap(monkeypatch):
    """Fake NASA TAP: records every query string, serves a mutable payload."""
    holder = {"payload": _archive_row(), "queries": []}

    def _fake_get(url, params=None, timeout=None):
        if params and "query" in params:
            holder["queries"].append(params["query"])
        return _FakeResponse(holder["payload"])

    monkeypatch.setattr(nasa_archive_module.requests, "get", _fake_get)
    return holder


class _Arr:
    """Duck-typed lightkurve Quantity container (``.value``)."""

    def __init__(self, value):
        self.value = value

    def __len__(self):
        return len(self.value)


class _FakeLc:
    """Minimal light curve for the Kepler accumulate loop (just appended)."""

    def __init__(self):
        self.flux = _Arr(np.array([1.0, 0.99]))
        self.meta = {}


class _FakeTessLc:
    """Minimal light curve passing the TESS per-sector validation."""

    def __init__(self):
        self.flux = _Arr(np.array([1.0, 0.999]))
        self.flux_err = _Arr(np.array([1e-6, 1e-6]))
        self.meta = {}


class _FakeFlat:
    """Duck-typed stitched light curve exposing time/flux/flux_err."""

    def __init__(self, bkjd_time):
        self.time = _Arr(np.asarray(bkjd_time, dtype=np.float64))
        self.flux = _Arr(np.ones_like(self.time.value))
        self.flux_err = _Arr(np.full_like(self.time.value, 1e-6))

    def normalize(self):
        return self

    def remove_nans(self):
        return self


class _FakeCollection:
    """Duck-typed lk.LightCurveCollection for the stitch boundary."""

    def __init__(self, lcs):
        self._lcs = lcs

    def stitch(self, corrector_func=None):
        return _FakeFlat([1700.0, 1866.0])


class _FakeSearch:
    """Duck-typed SearchResult: len + iteration + slice of N rows."""

    def __init__(self, n):
        self.rows = [object() for _ in range(n)]

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, key):
        return self.rows[key]


@pytest.fixture()
def offline_pipeline(monkeypatch):
    """Neutralize the cache/stitch seams so download_pipeline runs offline."""
    monkeypatch.setattr(
        LightkurveClient,
        "_try_serve_from_cache",
        staticmethod(lambda t, m, d: (None, None)),
    )
    monkeypatch.setattr(lkc_module.lk, "LightCurveCollection", _FakeCollection)
    monkeypatch.setattr(
        LightkurveClient,
        "_prioritize_search_results",
        staticmethod(lambda s, m: s),
    )
    return monkeypatch


# ---------------------------------------------------------------------------
# Fix 5 — HD/HIP/GJ space-separated archive convention
# ---------------------------------------------------------------------------


class TestFix5CatalogNameSpacing:
    def test_normalize_emits_space_form_for_hd_hip_gj(self):
        # pscomppars stores these SPACE-separated (verified live 2026-08-21:
        # the hyphenated form matches zero rows).
        assert NASAExoplanetArchive.normalize_target_name("HD 209458 b") == "HD 209458 b"
        assert NASAExoplanetArchive.normalize_target_name("hd-209458 b") == "HD 209458 b"
        assert NASAExoplanetArchive.normalize_target_name("GJ 1214 b") == "GJ 1214 b"
        assert NASAExoplanetArchive.normalize_target_name("HIP 12345 c") == "HIP 12345 c"

    def test_normalize_keeps_hyphen_for_planet_hunt_prefixes(self):
        assert NASAExoplanetArchive.normalize_target_name("WASP-12 b") == "WASP-12 b"
        assert NASAExoplanetArchive.normalize_target_name("HAT-P-11 b") == "HAT-P-11 b"
        assert NASAExoplanetArchive.normalize_target_name("Kepler-11 b") == "Kepler-11 b"

    def test_candidates_include_space_form_when_given_hyphen(self):
        cands = NASAExoplanetArchive._metadata_name_candidates("HD-209458 b")
        assert "HD 209458 b" in cands

    def test_candidates_include_hyphen_form_when_given_space(self):
        cands = NASAExoplanetArchive._metadata_name_candidates("HD 209458 b")
        assert "HD-209458 b" in cands

    def test_fetch_metadata_tries_space_form_candidate(self, recording_tap):
        recording_tap["payload"] = []
        NASAExoplanetArchive.fetch_metadata("HD-209458 b")
        joined = " | ".join(recording_tap["queries"])
        assert "pl_name='HD 209458 b'" in joined or "hostname='HD 209458 b'" in joined


# ---------------------------------------------------------------------------
# Fix 6 — deterministic host-star row (order by pl_orbper asc)
# ---------------------------------------------------------------------------


class TestFix6DeterministicHostRow:
    def test_pscomppars_query_orders_by_pl_orbper_asc(self, recording_tap):
        NASAExoplanetArchive.fetch_metadata("Kepler-11")
        pscomppars_queries = [
            q for q in recording_tap["queries"] if "pscomppars" in q
        ]
        assert pscomppars_queries, "no pscomppars query was issued"
        for q in pscomppars_queries:
            assert q.endswith("order by pl_orbper asc"), q

    def test_hostname_match_records_row_planet_name(self, recording_tap):
        # A hostname query's ordered first row is the innermost planet —
        # meta must record WHICH planet the row actually is.
        recording_tap["payload"] = _archive_row(pl_name="Kepler-11 d", pl_orbper=22.68)
        meta, err = NASAExoplanetArchive.fetch_metadata("Kepler-11")
        assert err is None
        assert meta["pl_name"] == "Kepler-11 d"

    def test_exact_pl_name_match_keeps_canonical_and_raw_dump(self, recording_tap):
        recording_tap["payload"] = _archive_row(pl_name="TRAPPIST-1 b")
        meta, _ = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert meta["pl_name"] == "TRAPPIST-1 b"
        assert isinstance(meta.get("raw_row_dump"), dict)


# ---------------------------------------------------------------------------
# Fix 7 — no garbage period fallbacks
# ---------------------------------------------------------------------------


class TestFix7PeriodFallbacksRemoved:
    def test_null_period_does_not_adopt_err_column(self, recording_tap):
        # Old bug: null pl_orbper fell back to the ERROR column value 1e-6.
        recording_tap["payload"] = _archive_row(pl_orbper=None, pl_orbpererr1=1e-6)
        meta, err = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert err is None
        # Proper chain: ps-table refetch (also null under the fake) -> 0.0.
        assert meta["pl_orbper"] == 0.0
        assert meta["orbital_period"] == 0.0

    def test_null_period_uses_ps_table_fallback(self, recording_tap, monkeypatch):
        recording_tap["payload"] = _archive_row(pl_orbper=None)

        def _fake_get(url, params=None, timeout=None):
            q = (params or {}).get("query", "")
            if " from ps " in q:
                return _FakeResponse(
                    [{"pl_name": "TRAPPIST-1 b", "pl_orbper": 1.51}]
                )
            return _FakeResponse(recording_tap["payload"])

        monkeypatch.setattr(nasa_archive_module.requests, "get", _fake_get)
        meta, _ = NASAExoplanetArchive.fetch_metadata("TRAPPIST-1 b")
        assert meta["pl_orbper"] == pytest.approx(1.51)

    def test_ps_orbital_period_helper_ignores_err_column(self, monkeypatch):
        monkeypatch.setattr(
            nasa_archive_module.requests,
            "get",
            lambda url, params=None, timeout=None: _FakeResponse(
                [{"pl_name": "X", "pl_orbper": None, "pl_orbpererr1": 2.5}]
            ),
        )
        assert NASAExoplanetArchive._fetch_ps_orbital_period("X") is None

    def test_dead_period_fallback_tokens_removed_from_source(self):
        # Behavioral seams cannot distinguish which fallback fired when the
        # fake serves both columns, so pin the removal at source level too
        # (the exact old call patterns, not the bare tokens — comments may
        # legitimately cite the audit).
        src = inspect.getsource(NASAExoplanetArchive)
        assert "row.get('pl_period')" not in src
        assert "pl_orbper = row.get('pl_orbpererr1')" not in src


# ---------------------------------------------------------------------------
# Fixes 1 + 2 — Kepler multi-quarter loop and timeout retries
# ---------------------------------------------------------------------------


class TestFix1KeplerMultiQuarterBaseline:
    def test_all_segments_downloaded_not_just_first_quarter(
        self, offline_pipeline, monkeypatch
    ):
        calls = {"stream": 0, "download": 0}

        def fake_stream(row, download_dir, read_timeout=180.0):
            calls["stream"] += 1
            return "staged.fits", None

        def fake_download(row, timeout=180.0, download_dir=None):
            calls["download"] += 1
            return _FakeLc()

        monkeypatch.setattr(
            LightkurveClient, "_stream_mast_download", staticmethod(fake_stream)
        )
        monkeypatch.setattr(
            LightkurveClient, "_download_with_timeout", staticmethod(fake_download)
        )
        monkeypatch.setattr(
            lkc_module.lk, "search_lightcurve", lambda *a, **k: _FakeSearch(14)
        )

        data, err = LightkurveClient.download_pipeline("Kepler-90", "Kepler")
        assert err is None
        assert data is not None
        # Old bug: `if lc_list: break` stopped after the FIRST successful
        # quarter (download calls == 1). All capped segments must iterate.
        assert calls["download"] == min(14, _MAX_DOWNLOAD_SEGMENTS) == 12
        assert calls["stream"] == calls["download"]


class TestFix2TimeoutRetryLoop:
    def _patch(self, monkeypatch, download_fn):
        monkeypatch.setattr(
            LightkurveClient,
            "_stream_mast_download",
            staticmethod(lambda row, download_dir, read_timeout=180.0: ("staged.fits", None)),
        )
        monkeypatch.setattr(
            LightkurveClient, "_download_with_timeout", staticmethod(download_fn)
        )
        monkeypatch.setattr(
            lkc_module.lk, "search_lightcurve", lambda *a, **k: _FakeSearch(1)
        )

    def test_timeout_is_retried_and_succeeds_on_third_attempt(
        self, offline_pipeline, monkeypatch
    ):
        attempts = {"n": 0}

        def fake_download(row, timeout=180.0, download_dir=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                return _TIMEOUT_SENTINEL
            return _FakeLc()

        self._patch(monkeypatch, fake_download)
        data, err = LightkurveClient.download_pipeline("Kepler-90", "Kepler")
        # The stray unconditional break stopped retries after attempt 1.
        assert attempts["n"] == 3
        assert data is not None
        assert err is None

    def test_persistent_timeout_reports_timed_out_reason(
        self, offline_pipeline, monkeypatch
    ):
        self._patch(
            monkeypatch,
            lambda row, timeout=180.0, download_dir=None: _TIMEOUT_SENTINEL,
        )
        data, err = LightkurveClient.download_pipeline("Kepler-90", "Kepler")
        assert data is None
        assert "timed out" in (err or "").lower()


# ---------------------------------------------------------------------------
# Fix 3 — distinguishable timeout -> "Network Timeout"
# ---------------------------------------------------------------------------


class TestFix3TimeoutDistinguishable:
    def test_call_with_timeout_returns_sentinel_on_overrun(self):
        def slow():
            time.sleep(0.5)
            return "late"

        res = LightkurveClient._call_with_timeout(slow, timeout=0.05, label="t")
        assert res is _TIMEOUT_SENTINEL

    def test_call_with_timeout_passes_through_genuine_empty_result(self):
        # An empty search result keeps its own falsy signal — it must be
        # distinguishable from the timeout sentinel.
        res = LightkurveClient._call_with_timeout(
            lambda: [], timeout=5.0, label="t"
        )
        assert res == []
        assert res is not _TIMEOUT_SENTINEL

    def test_search_timeout_translates_to_network_timeout_error(self, offline_pipeline):
        monkeypatch_sentinel = staticmethod(
            lambda fn, args=(), kwargs=None, timeout=15.0, label="op": _TIMEOUT_SENTINEL
        )
        # Simulate the overrun exactly at the seam _call_with_timeout occupies.
        offline_pipeline.setattr(
            LightkurveClient, "_call_with_timeout", monkeypatch_sentinel
        )
        data, err = LightkurveClient.download_pipeline("TRAPPIST-1", "TESS")
        assert data is None
        assert err == "Network Timeout"

    def test_ingestion_maps_timeout_error_to_network_timeout(self, monkeypatch):
        monkeypatch.setattr(
            NASAExoplanetArchive,
            "fetch_metadata",
            staticmethod(lambda n: ({"pl_name": "WASP-12 b"}, None)),
        )
        monkeypatch.setattr(
            LightkurveClient,
            "download_pipeline",
            staticmethod(lambda t, m: (None, "Network Timeout")),
        )
        res = RemoteDiscoveryEngine._fetch_data_impl("WASP-12 b", "TESS")
        assert res["status"] == "error"
        assert res["reason"] == "Network Timeout"


# ---------------------------------------------------------------------------
# Fix 4 — BJD offsets from the time_units single source of truth
# ---------------------------------------------------------------------------


class TestFix4MissionOffsetSingleSource:
    def test_tess_pipeline_applies_btjd_offset(self, offline_pipeline, monkeypatch):
        monkeypatch.setattr(
            LightkurveClient,
            "_stream_mast_download",
            staticmethod(lambda row, download_dir, read_timeout=120.0: ("staged.fits", None)),
        )
        monkeypatch.setattr(
            LightkurveClient,
            "_download_with_timeout",
            staticmethod(lambda row, timeout=30.0, download_dir=None: _FakeTessLc()),
        )
        monkeypatch.setattr(
            lkc_module.lk, "search_lightcurve", lambda *a, **k: _FakeSearch(2)
        )
        data, err = LightkurveClient.download_pipeline("TRAPPIST-1", "TESS")
        assert err is None
        assert data["bjd_epoch_offset_applied"] == 2457000.0
        assert data["time"][0] == pytest.approx(1700.0 + 2457000.0)

    def test_kepler_pipeline_applies_bkjd_offset(self, offline_pipeline, monkeypatch):
        monkeypatch.setattr(
            LightkurveClient,
            "_stream_mast_download",
            staticmethod(lambda row, download_dir, read_timeout=180.0: ("staged.fits", None)),
        )
        monkeypatch.setattr(
            LightkurveClient,
            "_download_with_timeout",
            staticmethod(lambda row, timeout=180.0, download_dir=None: _FakeLc()),
        )
        monkeypatch.setattr(
            lkc_module.lk, "search_lightcurve", lambda *a, **k: _FakeSearch(2)
        )
        data, err = LightkurveClient.download_pipeline("Kepler-90", "Kepler")
        assert err is None
        assert data["bjd_epoch_offset_applied"] == 2454833.0
        assert data["time"][0] == pytest.approx(1700.0 + 2454833.0)

    def test_inline_ternary_offset_removed_from_source(self):
        # K2 has no behavioral seam through download_pipeline (the mission
        # gate rejects it before the offset site), so pin the single source
        # of truth at source level; the VALUES are locked by
        # tests/test_i2_bjd_unit.py::test_bjd_offset_for_mission_k2.
        src = inspect.getsource(lkc_module)
        assert '2454833.0 if mission_type == "Kepler"' not in src
        assert "bjd_offset_for_mission(mission_type)" in src


# ---------------------------------------------------------------------------
# Fixes 8 + 9 — bridge failure classification
# ---------------------------------------------------------------------------


class TestFix8And9BridgeClassifier:
    @staticmethod
    def _run_bridge(monkeypatch, tess_result, kepler_result):
        def fake_pipeline(t, m):
            return tess_result if m == "TESS" else kepler_result

        monkeypatch.setattr(
            LightkurveClient, "download_pipeline", staticmethod(fake_pipeline)
        )
        return RemoteDiscoveryEngine._bridge_to_time_series(
            {"pl_name": "WASP-12 b"}, "WASP-12 b", "WASP-12 b", None,
        )

    def test_final_else_classifies_download_failed(self, monkeypatch):
        # Fix 8: the old elif/else pair both produced "Target not observed".
        res = self._run_bridge(
            monkeypatch, (None, "HTTP 500 server error"), (None, "HTTP 503")
        )
        assert res["status"] == "no_time_series"
        assert res["reason"] == "Download failed"

    def test_silent_second_mission_does_not_erase_timeout_diagnostic(
        self, monkeypatch
    ):
        # Fix 9's headline scenario: TESS times out, then Kepler returns
        # (None, None). The old last-write-wins scalar lost the diagnostic.
        res = self._run_bridge(monkeypatch, (None, "Network Timeout"), (None, None))
        assert res["reason"] == "Network Timeout"
        assert "TESS" in (res["mast_error"] or "")
        assert "timeout" in (res["mast_error"] or "").lower()

    def test_generic_failure_preferred_over_not_observed(self, monkeypatch):
        res = self._run_bridge(
            monkeypatch, (None, "Target not observed"), (None, "HTTP 403 forbidden")
        )
        assert res["reason"] == "Download failed"

    def test_both_silent_yields_not_observed(self, monkeypatch):
        res = self._run_bridge(monkeypatch, (None, None), (None, None))
        assert res["reason"] == "Target not observed"
        assert res["mast_error"] is None


# ---------------------------------------------------------------------------
# Fix 10 — load_config catches OSError
# ---------------------------------------------------------------------------


class TestFix10LoadConfigOSError:
    def test_invalid_json_returns_empty_dict(self, tmp_path):
        bad = tmp_path / "config.json"
        bad.write_text("{not valid json", encoding="utf-8")
        assert load_config(str(bad)) == {}

    def test_unreadable_file_returns_empty_dict(self, tmp_path):
        # Opening a directory raises PermissionError (Windows) /
        # IsADirectoryError (POSIX) — both OSError subclasses that
        # previously escaped the defensive-{} contract.
        assert load_config(str(tmp_path)) == {}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_config(str(tmp_path / "nope.json")) == {}


# ---------------------------------------------------------------------------
# Fix 11 — fixture recorder uses the real ?uri= contract + real status
# ---------------------------------------------------------------------------


class TestFix11FixtureRecorderUriAndStatus:
    def test_url_uses_uri_param_and_filename_carries_status(self, tmp_path, monkeypatch):
        captured_urls = []

        class _FakeHttpClient:
            def get(self, url, *, timeout=30.0, stream=False):
                captured_urls.append(url)
                return net_module.HttpResponse(
                    status_code=404, headers={}, body=b"nope", iter_chunks=None
                )

        monkeypatch.setattr(net_module, "RequestsHttpClient", _FakeHttpClient)
        paths = net_module._record_fixture(
            "TRAPPIST-1",
            "TESS",
            tmp_path,
            data_uri="mast:TESS/product/tess2019000000000-s0001-1-0.fits",
        )
        assert len(paths) == 1
        # The hardcoded "200" is gone: the ACTUAL status (404) lands in the name.
        assert paths[0].name == "mast_tess_trappist-1_404.json"
        assert captured_urls, "recorder issued no request"
        assert "uri=mast:TESS/product/tess2019000000000-s0001-1-0.fits" in captured_urls[0]
        assert "target=" not in captured_urls[0]

    def test_missing_data_uri_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            net_module._record_fixture("TRAPPIST-1", "TESS", tmp_path)
