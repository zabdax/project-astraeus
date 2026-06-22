"""4-phase ingestion + detection matrix across (target, source) combinations.

The original ``tests/global_matrix_stress_test.py`` was a diagnostic
script that ran 11 (phase, target, source, timeout) tracks and printed
a JSON report. Bucket 5 converts it to a parametrized pytest module.

Phase semantics:
  - Phase 1: metadata-only (NASA Exoplanet Archive). Expects
    ``status == "no_time_series"``; must include ``st_rad`` and
    ``pl_orbper`` in metadata.
  - Phase 2: full ingestion (TESS). Expects ``status == "success"`` and
    a positive ``planet_radius_earth`` from the Mandel-Agol layer.
  - Phase 3: full ingestion (Kepler). WASP-12 b has no Kepler light
    curve and falls back to ``no_time_series``; the other two
    targets expect ``status == "success"`` and a positive
    ``transit_depth``.
  - Phase 4: combined Kepler+TESS baseline. Expects ``status ==
    "success"`` and at least one TTV data point compiled.

This module hits the network (NASA Exoplanet Archive, MAST). All tests
are marked ``@pytest.mark.network`` and ``@pytest.mark.slow`` so they
are excluded from the fast CI gate.

The original script's flaky Phase 1 timing assertion
(``execution_time >= 1.5s -> FAILED``) is dropped — the source comment
flagged it as network-dependent, not a real test.
"""
from __future__ import annotations

import os
import sys

import pytest

# Add project root to path so `astraeus.*` imports resolve when this file
# is run directly (e.g., `python tests/test_global_matrix_stress_test.py`).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.core.ingestion import RemoteDiscoveryEngine


# (phase, target, source) tuples. Timeouts dropped (no longer used in
# pytest; network variability would cause spurious failures).
_MATRIX = [
    # Phase 1: metadata-only
    (1, "WASP-12 b", "NASA Exoplanet Archive"),
    (1, "Kepler-13 b", "NASA Exoplanet Archive"),
    (1, "HAT-P-11 b", "NASA Exoplanet Archive"),
    # Phase 2: TESS
    (2, "WASP-12 b", "TESS"),
    (2, "Kepler-13 b", "TESS"),
    (2, "HAT-P-11 b", "TESS"),
    # Phase 3: Kepler (WASP-12 b has no Kepler light curve)
    (3, "WASP-12 b", "Kepler"),
    (3, "Kepler-13 b", "Kepler"),
    (3, "HAT-P-11 b", "Kepler"),
    # Phase 4: combined Kepler + TESS
    (4, "Kepler-13 b", "Combined Baseline (Kepler + TESS)"),
    (4, "HAT-P-11 b", "Combined Baseline (Kepler + TESS)"),
]


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.parametrize("phase,target,source", _MATRIX)
def test_matrix_phase_track(phase: int, target: str, source: str):
    """Run a single (phase, target, source) track and assert the
    expected outcome for that phase.
    """
    data = RemoteDiscoveryEngine._fetch_data_impl(target, source)
    status = data.get("status", "unknown")
    meta = data.get("metadata", {})

    if phase == 1:
        # Metadata-only: must return no_time_series, must include
        # the required archival keys.
        assert "st_rad" in meta, "Root key 'st_rad' missing"
        assert "pl_orbper" in meta, "Root key 'pl_orbper' missing"
        assert status == "no_time_series", (
            f"Phase 1 expected 'no_time_series', got '{status}'"
        )

    elif phase == 2:
        # Full ingestion: success expected, planet_radius > 0.
        assert status == "success", f"Phase 2 ingestion failed: {status}"
        cand = detect_transit_candidate(
            data["time"], data["flux"], target, source, meta
        )
        assert cand is not None, "detect_transit_candidate returned None"
        assert cand.get("planet_radius_earth", 0.0) > 0, (
            "Mandel-Agol output invalid (<=0)"
        )

    elif phase == 3:
        # Kepler phase: WASP-12 b has no Kepler light curve; other
        # targets expect success + positive transit_depth.
        if target == "WASP-12 b":
            assert status == "no_time_series", (
                f"Expected fallback 'no_time_series' for WASP-12 b, "
                f"got '{status}'"
            )
        else:
            assert status == "success", f"Phase 3 ingestion failed: {status}"
            cand = detect_transit_candidate(
                data["time"], data["flux"], target, source, meta
            )
            assert cand is not None
            assert cand.get("transit_depth", 0.0) > 0, (
                "Signal squashed by detrending"
            )

    elif phase == 4:
        # Combined baseline: success + TTV data points compiled.
        assert status == "success", f"Phase 4 ingestion failed: {status}"
        cand = detect_transit_candidate(
            data["time"], data["flux"], target, source, meta
        )
        assert cand is not None
        assert len(cand.get("ttv_data", [])) > 0, (
            "Layer 6 TTV points not compiled"
        )
