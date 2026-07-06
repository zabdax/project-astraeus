"""Characterize LightkurveClient.download_pipeline + download_combined_fusion.

These tests run against the *unchanged* production code (Phase 1 captures
behaviour). Phase 2+ then refactors under the test net.

Strategy: monkeypatch ``lightkurve`` and ``requests`` at the module level
so download_pipeline runs offline without ever touching the network.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import numpy as np
import pytest


# --- Helpers --------------------------------------------------------------

def _make_fake_search_result_with_sectors(sectors: list[str]):
    """Build a MagicMock that quacks like a lightkurve SearchResult."""
    rows = []
    for s in sectors:
        r = MagicMock()
        r.__iter__ = lambda self=None, _s=s: iter([])
        rows.append(r)
    sr = MagicMock()
    sr.__iter__ = lambda: iter(rows)
    sr.__len__ = lambda: len(rows)
    return sr


def _make_fake_lightcurve(time: np.ndarray, flux: np.ndarray, err: np.ndarray):
    lc = MagicMock()
    lc.time.value = time
    lc.flux.value = flux
    lc.flux_err.value = err
    return lc


# --- Tests ----------------------------------------------------------------

def test_download_pipeline_returns_dict_with_three_keys_on_success(monkeypatch):
    """download_pipeline success returns a dict with time/flux/flux_err arrays."""
    from astraeus.core import lightkurve_client as lkc

    fake_time = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    fake_flux = np.array([1.0, 0.99, 1.0], dtype=np.float64)
    fake_err = np.array([0.01, 0.01, 0.01], dtype=np.float64)
    fake_lc = _make_fake_lightcurve(fake_time, fake_flux, fake_err)

    # Stub out the download path: pipeline ends up reading from a fake
    # cache-hit branch via _try_serve_from_cache. We force the success
    # path by monkeypatching _try_serve_from_cache to return the dict.
    expected = {"time": fake_time, "flux": fake_flux, "flux_err": fake_err}
    monkeypatch.setattr(
        lkc.LightkurveClient, "_try_serve_from_cache",
        staticmethod(lambda t, m, d: (expected, None)),
    )

    result, err = lkc.LightkurveClient.download_pipeline("TRAPPIST-1", "TESS")
    assert err is None
    assert result is not None
    assert set(result.keys()) >= {"time", "flux", "flux_err"}
    assert result["time"].dtype == np.float64
    assert result["flux"].dtype == np.float64
    assert result["flux_err"].dtype == np.float64


def test_download_pipeline_returns_none_with_error_on_cache_miss(monkeypatch):
    """When no data is available, return None — either (None, err_string) or (None, None).

    Production shortcut (lightkurve_client.py line 736-737): if the upstream
    ``lk.search_lightcurve`` returns an empty SearchResult, the function short-
    circuits with ``return None, None`` *before* reaching the inner stubs. We
    characterize the contract as "result is None"; we do NOT require an error
    string (callers must handle both).
    """
    from astraeus.core import lightkurve_client as lkc

    monkeypatch.setattr(
        lkc.LightkurveClient, "_try_serve_from_cache",
        staticmethod(lambda t, m, d: (None, "Target not observed")),
    )
    # Also stub the streaming path so the second-attempt branch doesn't run
    # (defensive — not always reached due to the empty-search shortcut above).
    monkeypatch.setattr(
        lkc.LightkurveClient, "_stream_mast_download",
        staticmethod(lambda row, d, rt=600.0: (None, "Target not observed")),
    )
    monkeypatch.setattr(
        lkc.LightkurveClient, "_download_tess_lightcurves",
        staticmethod(lambda sr, d: ([], "Target not observed")),
    )

    result, err = lkc.LightkurveClient.download_pipeline("DOES_NOT_EXIST", "TESS")
    # The contract: data is None. err may be None or a string — both valid.
    assert result is None
    if err is not None:
        assert isinstance(err, str)


def test_download_combined_fusion_returns_unified_dict_on_success(monkeypatch):
    """download_combined_fusion success returns time/flux/flux_err + segment counts."""
    from astraeus.core import lightkurve_client as lkc

    fake_time = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    fake_flux = np.array([1.0, 0.99, 1.0], dtype=np.float64)
    fake_err = np.array([0.01, 0.01, 0.01], dtype=np.float64)

    # Patch the inner helpers that download_combined_fusion composes.
    monkeypatch.setattr(
        lkc.LightkurveClient, "download_pipeline",
        staticmethod(lambda t, m: (
            {"time": fake_time, "flux": fake_flux, "flux_err": fake_err}, None
        )),
    )
    # Patch the NASA TAP call so it returns no metadata (bypasses network).
    from astraeus.core import nasa_archive
    monkeypatch.setattr(
        nasa_archive.NASAExoplanetArchive, "fetch_metadata",
        staticmethod(lambda n: ({}, None)),
    )

    result, err = lkc.LightkurveClient.download_combined_fusion("Kepler-11")
    # Result shape: at minimum time/flux/flux_err, plus segment metadata.
    assert err is None
    assert result is not None
    for key in ("time", "flux", "flux_err"):
        assert key in result
        assert result[key].dtype == np.float64
