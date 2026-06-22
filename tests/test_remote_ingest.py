"""Smoke test: HAT-P-11 b metadata round-trip via RemoteDiscoveryEngine.

The original ``scripts/manual_tests/test_ingest.py`` (14 lines) was a
print-only sanity check on ``RemoteDiscoveryEngine.fetch_data``. Bucket
5 converts it to a proper pytest test with explicit assertions.

The test is marked ``@pytest.mark.network`` (excluded from the fast
CI gate) but NOT ``@slow`` — a single metadata fetch is typically
sub-30s.
"""
from __future__ import annotations

import pytest

from astraeus.core.ingestion import RemoteDiscoveryEngine


@pytest.mark.network
def test_hat_p_11_b_metadata_round_trip():
    """HAT-P-11 b metadata fetch returns a recognised status with non-empty keys."""
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
