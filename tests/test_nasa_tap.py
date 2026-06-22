"""Smoke test: direct NASA Exoplanet Archive TAP query for Kepler-90 b.

The original ``scripts/manual_tests/test_nasa.py`` (13 lines) was a
print-only direct ``requests.get`` against the NASA TAP endpoint. Bucket
5 converts it to a proper pytest test with explicit assertions.

Marked ``@pytest.mark.network``.
"""
from __future__ import annotations

import pytest
import requests


_NASA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


@pytest.mark.network
def test_nasa_tap_kepler_90_b_query():
    """Direct TAP query for Kepler-90 b returns JSON with at least one row."""
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
