"""Network tests for the NASA Exoplanet Archive / MAST fetch paths.

Consolidated from three previous single-test files (Bucket 5 follow-up
correction):

  - tests/test_remote_ingest.py  (RemoteDiscoveryEngine.fetch_data, HAT-P-11 b)
  - tests/test_remote_fetch.py   (NASAExoplanetArchive.fetch_metadata, Kepler-90)
  - tests/test_nasa_tap.py       (direct requests.get against NASA TAP endpoint)

All three test the same underlying NASA archive / MAST fetch path; the
previous one-file-per-script structure fragmented the same subsystem
across three modules. The consolidation also fills the
``astraeus/core/ingestion.py`` coverage gap (no currently-collected
test exercised it before bucket 5; the per-target RemoteDiscoveryEngine
calls below do).

All three tests are marked ``@pytest.mark.network`` (excluded from the
fast CI gate via ``pytest -m "not network and not slow"``) but NOT
``@slow`` — a single metadata fetch is typically sub-30s.

Originals moved to ``deprecated/`` (the three pre-existing
``scripts/manual_tests/test_ingest.py``, ``test_fetch.py``,
``test_nasa.py`` scripts were already deprecate-not-deleted per the
global rule).
"""
from __future__ import annotations

import pytest
import requests

from astraeus.core.ingestion import RemoteDiscoveryEngine
from astraeus.core.nasa_archive import NASAExoplanetArchive


_NASA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


@pytest.mark.network
def test_nasa_archive_metadata_round_trip():
    """HAT-P-11 b metadata fetch via RemoteDiscoveryEngine.fetch_data.

    Ported from scripts/manual_tests/test_ingest.py.

    Asserts:
      - result is not None
      - status in {success, no_time_series, metadata_only}
      - metadata dict is non-empty
      - pl_orbper > 0 and st_rad > 0 when those keys are present
    """
    result = RemoteDiscoveryEngine.fetch_data("HAT-P-11 b", mission="Kepler")

    assert result is not None
    assert result.get("status") in {"success", "no_time_series", "metadata_only"}, (
        f"unexpected status: {result.get('status')!r}"
    )

    meta = result.get("metadata", {})
    assert isinstance(meta, dict)
    assert len(meta) > 0, "metadata dict is empty"

    if "pl_orbper" in meta:
        assert meta["pl_orbper"] > 0, f"pl_orbper must be > 0, got {meta['pl_orbper']}"
    if "st_rad" in meta:
        assert meta["st_rad"] > 0, f"st_rad must be > 0, got {meta['st_rad']}"


@pytest.mark.network
def test_kepler_90_archive_metadata_fetch():
    """Kepler-90 metadata fetch via NASAExoplanetArchive.fetch_metadata.

    Ported from scripts/manual_tests/test_fetch.py.

    Asserts:
      - err is None
      - meta is non-empty
    """
    meta, err = NASAExoplanetArchive.fetch_metadata("kepler-90")

    assert err is None, f"fetch_metadata returned error: {err!r}"
    assert meta is not None and len(meta) > 0, (
        f"expected non-empty metadata, got {meta!r}"
    )


@pytest.mark.network
def test_nasa_tap_direct_query():
    """Direct NASA Exoplanet Archive TAP query for Kepler-90 b.

    Ported from scripts/manual_tests/test_nasa.py.

    Asserts:
      - HTTP 2xx response
      - JSON response is a list with >= 1 row
      - each row has pl_name and hostname keys
    """
    params = {
        "query": "select pl_name, hostname from ps where pl_name='Kepler-90 b'",
        "format": "json",
    }
    resp = requests.get(_NASA_TAP, params=params, timeout=30)

    assert resp.ok, f"TAP query failed: {resp.status_code} {resp.text[:200]!r}"

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1, f"expected >=1 row, got {len(data)}"

    first = data[0]
    assert "pl_name" in first, f"missing pl_name key in row: {first!r}"
    assert "hostname" in first, f"missing hostname key in row: {first!r}"
