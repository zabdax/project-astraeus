"""Fast end-to-end smoke test for the ASTRAEUS transit pipeline.

This is intentionally a *smoke* test, not a coverage expansion: a single
synthetic transit with exact, reproducible ground truth is run through the
real :func:`detect_transit_candidate` entry point and the recovered period,
depth, and vetting status are checked against sane tolerances. A tiny
report-generation call is also exercised so a regression in the reporting
module would surface here too.

Run just this gate with::

    pytest tests/test_pipeline_smoke.py -m smoke -v
"""

from __future__ import annotations

import functools

import pytest

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.reporting import generate_academic_report
from astraeus.simulation.synthetic import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)

# ---------------------------------------------------------------------------
# Injected ground truth. Only ``samples`` is reduced from the default 4000 for
# speed (see bucket6_summary.md); every other scenario field stays at its
# default so the injected period / radius-ratio remain exact and reproducible
# (seed=42). radius_ratio=0.1  ->  geometric depth = 0.1**2 = 0.01.
# ---------------------------------------------------------------------------
_INJECTED_PERIOD_DAYS = 3.0
_INJECTED_DEPTH_FRACTION = 0.01
_SAMPLES = 2000


@functools.lru_cache(maxsize=1)
def _run_pipeline() -> dict:
    """Build the synthetic series once and run the full detection pipeline.

    Cached so both smoke tests share a single pipeline invocation rather than
    paying the (small) cost twice.
    """

    scenario = SyntheticTransitScenario(samples=_SAMPLES)
    light_curve = generate_synthetic_transit_series(scenario)
    return detect_transit_candidate(
        light_curve.time_days,
        light_curve.observed_flux,
        target_name="SMOKE",
        data_source="synthetic",
    )


@pytest.mark.smoke
def test_full_pipeline_recovers_synthetic_planet() -> None:
    """Recovered period/depth/vetting must match the injected truth."""

    result = _run_pipeline()

    # Contract: the result dict exposes the canonical analysis keys.
    for key in (
        "period_days",
        "transit_depth",
        "vetting_status",
        "ttv_data",
        "periodogram",
    ):
        assert key in result, f"missing expected key in pipeline result: {key!r}"

    # Period within 1% of the injected 3.0-day signal.
    recovered_period = float(result["period_days"])
    assert (
        abs(recovered_period - _INJECTED_PERIOD_DAYS) / _INJECTED_PERIOD_DAYS <= 0.01
    ), f"period {recovered_period} outside 1% of {_INJECTED_PERIOD_DAYS}"

    # Depth within a factor of 2 of the injected 0.01: synthetic noise makes
    # a tighter bound fragile, but a factor-of-2 is still specific enough to
    # catch a depth-estimator regression.
    recovered_depth = float(result["transit_depth"])
    assert (
        _INJECTED_DEPTH_FRACTION / 2.0
        <= recovered_depth
        <= _INJECTED_DEPTH_FRACTION * 2.0
    ), f"depth {recovered_depth} outside factor-of-2 of {_INJECTED_DEPTH_FRACTION}"

    # Vetting must be a planet-candidate label, NOT an eclipsing-binary label.
    vetting = str(result["vetting_status"])
    assert vetting.startswith("Verified Planet Candidate"), (
        f"unexpected vetting_status: {vetting!r}"
    )
    assert "Binary" not in vetting, (
        f"vetting_status flagged as binary: {vetting!r}"
    )

    # The candidate must actually be flagged as valid and carry TTV output.
    assert result["is_candidate"], "pipeline did not flag a candidate"
    assert isinstance(result["ttv_data"], list), "ttv_data must be a list"


@pytest.mark.smoke
def test_reporting_does_not_crash_on_minimal_payload() -> None:
    """The PDF report builder must succeed on a tiny valid payload."""

    result = _run_pipeline()

    payload = {
        "star_id": "SMOKE-1",
        "candidates": [
            {
                "candidate_id": "SMOKE-1 b",
                "period": float(result["period_days"]),
                "snr": float(result["snr"]),
                "depth": float(result["transit_depth"]),
                "epoch": float(result["t0"]),
            }
        ],
    }

    buffer = generate_academic_report(payload)  # no figures -> fully offline
    assert buffer is not None, "report generator returned None"

    # The in-memory buffer should hold a real PDF (magic header %PDF).
    data = buffer.read(8) if hasattr(buffer, "read") else bytes(buffer)[:8]
    assert data.startswith(b"%PDF"), f"output is not a PDF (first bytes: {data!r})"
