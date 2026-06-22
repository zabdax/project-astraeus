"""Smoke test: Kepler-90 metadata fetch via NASAExoplanetArchive.

The original ``scripts/manual_tests/test_fetch.py`` (8 lines) was a
print-only sanity check on ``NASAExoplanetArchive.fetch_metadata``.
Bucket 5 converts it to a proper pytest test with explicit assertions.

Marked ``@pytest.mark.network``.
"""
from __future__ import annotations

import pytest

from astraeus.core.nasa_archive import NASAExoplanetArchive


@pytest.mark.network
def test_kepler_90_archive_metadata_fetch():
    """Kepler-90 metadata fetch returns no error and non-empty metadata."""
    meta, err = NASAExoplanetArchive.fetch_metadata("kepler-90")

    assert err is None, f"fetch_metadata returned error: {err!r}"
    assert meta is not None and len(meta) > 0, (
        f"expected non-empty metadata, got {meta!r}"
    )
