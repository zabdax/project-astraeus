"""6-layer pipeline cascade for (target, source) matrix.

The original ``tests/solid_matrix_diagnostic.py`` was a 440-line
diagnostic that ran the full 6-layer pipeline on 12 tracks (3 targets
x 4 sources) using ``multiprocessing`` for hard timeouts. Bucket 5
converts it to a parametrized pytest module.

The per-layer invariants from the original script are preserved as
explicit ``assert`` statements. The ``multiprocessing``-based hard
timeout is dropped (pytest will surface hangs via its own collection
timeout if needed; the slow marker excludes these from the fast gate).

All 12 tracks hit the network (NASA Exoplanet Archive, MAST) and are
marked ``@pytest.mark.network`` and ``@pytest.mark.slow``.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.core.ingestion import RemoteDiscoveryEngine


_R_SUN_TO_R_EARTH = 109.2

_TARGETS = ("WASP-12 b", "Kepler-13 b", "HAT-P-11 b")
_SOURCES = (
    "NASA Exoplanet Archive",
    "TESS",
    "Kepler",
    "Combined Baseline (Kepler + TESS)",
)

_MATRIX = [(t, s) for t in _TARGETS for s in _SOURCES]


def _as_valid_array(values, label: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    assert arr.ndim == 1 and len(arr) >= 10, (
        f"{label} must be a 1D array with at least 10 samples"
    )
    assert np.all(np.isfinite(arr)), f"{label} contains NaN or infinite values"
    return arr


def _classify_vetting(depth_fraction, metrics, orbital_period_days, snr):
    is_ultra_short_period = orbital_period_days < 1.5
    sec_depth = metrics.get("secondary_eclipse_depth", 0.0)
    if depth_fraction < 0.03:
        return "Verified Planet Candidate"
    if (
        metrics.get("v_shape_metric", 0.0) > 0.85
        and metrics.get("secondary_eclipse_detected")
        and (snr <= 20.0 or sec_depth >= 0.0008)
    ):
        return "Eclipsing Binary Detected"
    if (
        snr <= 20.0
        and not is_ultra_short_period
        and (
            metrics.get("v_shape_metric", 0.0) > 0.8
            or metrics.get("flat_bottom_fraction", 1.0) < 0.05
        )
    ):
        return "V-Shaped False Positive Risk (Potential Grazing Binary)"
    if metrics.get("secondary_eclipse_detected"):
        if sec_depth < 0.0008:
            return "Verified Planet Candidate (Atmospheric Occultation Detected)"
        return "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
    return "Planet Candidate Requires Follow-Up"


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.parametrize("target,source", _MATRIX)
def test_cascade_track(target: str, source: str):
    """Run the full 6-layer pipeline for one (target, source) track.

    Layer-by-layer invariants:
      L1: payload status, finite time/flux arrays of length >= 10.
      L2: detrended flux median within 2% of 1.0.
      L3: BLS period > 0 and finite; depth > 0 and finite.
      L4: GeometricValidator duration > 0; classification non-empty.
      L5: PhysicalPropertiesEngine model_radius matches
          st_rad * sqrt(depth) * 109.2 within 1e-4 R_Earth atol.
      L6: TTVAnalyzer returns non-empty list with epoch+residual fields.

    For metadata-only sources, the test only checks that archival keys
    (``st_rad``, ``pl_orbper``) are present. For ``no_time_series``
    payloads, the analysis layers are skipped (the source has no live
    data for this target).
    """
    payload = RemoteDiscoveryEngine._fetch_data_impl(target, source)
    status = str(payload.get("status", "")).lower()
    meta = payload.get("metadata", {}) or {}

    if source == "NASA Exoplanet Archive":
        # Metadata-only source: just check archival keys are present.
        assert status in {"no_time_series", "metadata_only", "success"}, (
            f"Layer 1 archive metadata fetch failed; status={payload.get('status')!r}"
        )
        assert isinstance(meta, dict) and meta, (
            f"Layer 1 archive metadata payload is empty; "
            f"archive_error={payload.get('archive_error')!r}"
        )
        for key in ("pl_orbper", "st_rad"):
            assert key in meta, f"Layer 1 archive metadata missing key {key!r}"
        return

    if status == "no_time_series" and not payload.get("mast_error"):
        # The source has no live data for this target; analysis skipped.
        return

    # Layers 1-6 below require a live light curve.
    assert status == "success", (
        f"Layer 1 ingestion did not fetch live arrays; status={payload.get('status')!r}"
    )

    time_arr = _as_valid_array(payload.get("time"), "Layer 1 time")
    flux_arr = _as_valid_array(payload.get("flux"), "Layer 1 flux")
    assert len(time_arr) == len(flux_arr), (
        "Layer 1 time and flux arrays have different lengths"
    )
    finite_mask = np.isfinite(time_arr) & np.isfinite(flux_arr)
    assert np.count_nonzero(finite_mask) >= 10, (
        "Layer 1 payload has fewer than 10 finite paired samples"
    )
    time_arr = time_arr[finite_mask]
    flux_arr = flux_arr[finite_mask]

    # Layer 2: detrending
    rotation_period = DetrendingEngine.estimate_stellar_rotation(time_arr, flux_arr)
    clean_flux = np.asarray(
        DetrendingEngine.detrend(time_arr, flux_arr, rotation_period), dtype=float
    )
    assert np.all(np.isfinite(clean_flux)), (
        "Layer 2 detrended flux contains NaN or infinite values"
    )
    median_flux = float(np.median(clean_flux))
    assert math.isclose(median_flux, 1.0, rel_tol=0.02, abs_tol=0.02), (
        f"Layer 2 detrended flux median is {median_flux:.6f}, expected 1.0"
    )

    # Layer 3: BLS
    bls_result = BLSSearchEngine.search(time_arr, clean_flux)
    period_days = float(bls_result.get("period", 0.0))
    assert math.isfinite(period_days) and period_days > 0, (
        f"Layer 3 BLS returned invalid period: {period_days!r}"
    )
    depth_raw = float(bls_result.get("depth", 0.0))
    depth_fraction = depth_raw / 100.0 if depth_raw > 0.1 else depth_raw
    assert math.isfinite(depth_fraction) and depth_fraction > 0, (
        f"Layer 3 BLS returned invalid depth: {depth_fraction!r}"
    )

    # Layer 4: geometric vetting
    duration = float(bls_result.get("duration", 0.0))
    transit_time = float(bls_result.get("t0", 0.0))
    assert duration > 0 and math.isfinite(duration), (
        f"Layer 4 received invalid duration: {duration!r}"
    )
    geom_metrics = GeometricValidator.validate(
        time_arr, clean_flux, period_days, transit_time, duration, depth_fraction
    )
    classification = _classify_vetting(
        depth_fraction, geom_metrics, period_days, snr=float(bls_result.get("snr", 0.0))
    )
    assert isinstance(classification, str) and classification.strip(), (
        "Layer 4 failed to assign a classification string"
    )

    # Layer 5: physical properties
    st_rad = float(meta.get("st_rad") or meta.get("stellar_radius") or 0.0)
    assert st_rad > 0, f"Layer 5 missing archival stellar radius in metadata: {meta!r}"
    expected_radius = st_rad * math.sqrt(depth_fraction) * _R_SUN_TO_R_EARTH
    phys = PhysicalPropertiesEngine.derive(
        period_days,
        depth_fraction,
        st_rad,
        float(meta.get("st_teff") or 5778.0),
        float(meta.get("st_mass") or 1.0),
        float(meta.get("sy_jmag") or 10.0),
    )
    model_radius = float(phys.get("planet_radius_earth", 0.0))
    assert math.isclose(model_radius, round(expected_radius, 4), rel_tol=0.0, abs_tol=1e-4), (
        f"Layer 5 radius scaling mismatch: model={model_radius}, "
        f"expected={expected_radius:.4f}, constant={_R_SUN_TO_R_EARTH}"
    )
    assert model_radius > 0.1, f"Layer 5 planet radius too small: {model_radius:.4f} R_Earth"

    # Layer 6: TTV
    ttv_data = TTVAnalyzer.calculate(
        time_arr, clean_flux, period_days, transit_time, duration
    )
    assert isinstance(ttv_data, list) and len(ttv_data) > 0, (
        "Layer 6 TTV compiler produced no renderable data points"
    )
    assert all("epoch" in point and "ttv_residual_min" in point for point in ttv_data), (
        "Layer 6 TTV points are missing epoch or residual fields"
    )
