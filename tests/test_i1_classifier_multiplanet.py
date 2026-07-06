"""Regression test for the I1 fix: cross-vetting branches must run for
detected peaks even when DETECTION_CONFIDENCE_FLOOR is unmet, so the
multi-planet case (where a real peak loses periodogram-wide significance
to the other planets' periodic power) still receives a vetting verdict.

Symptom this test guards: in the round-2 SYN-5P run, the cross-vetting
block in `detect_transit_candidate` was gated on `is_valid = (snr>thresh)
and (confidence_score >= 7.0)`. For p1 (SNR 10.92, confidence_score 3.74)
in a 5-planet synthetic curve, this left `is_valid=False`, so the
cross-vetting branches were skipped, and `vetting_status` remained stuck
at the shape-vetting result `'Likely Planet'` instead of being upgraded
to `'Verified Planet Candidate'`. The orchestrator's guardrail 1 then
trips on `'Likely Planet'.startswith('Verified Planet Candidate') ==
False`, starving the search.

The fix: run the cross-vetting block unconditionally (the shape vet
already runs unconditionally on the line above), and let the existing
`is_valid` gate only control the *emission* flags (`candidate_found` /
`is_candidate`) and the line-79 default `vetting_status`.
"""

import numpy as np
import pytest

from astraeus.analysis.detection import detect_transit_candidate
from astraeus.core.constants import DETECTION_CONFIDENCE_FLOOR


# SYN-5P scenario (periods 12/45/120/300/600d, depths 500/1000/800/1500/2000
# ppm, 1500d baseline, 30k samples, 500 ppm Gaussian noise). Reused exactly
# from scratch/h23_5planet_injection.py.
N_SAMPLES = 30000
T_SPAN = 1500.0
INJECTED = [
    ("p1", 12.0,  500,  5.0,   0.15),
    ("p2", 45.0,  1000, 22.0,  0.25),
    ("p3", 120.0, 800,  80.0,  0.40),
    ("p4", 300.0, 1500, 200.0, 0.60),
    ("p5", 600.0, 2000, 450.0, 0.80),
]


def _build_synthetic_5p():
    rng = np.random.default_rng(42)
    time = np.linspace(0, T_SPAN, N_SAMPLES)
    flux = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)
    for name, period, depth_ppm, t0, dur in INJECTED:
        phase = ((time - t0) % period) - period / 2.0
        in_tr = np.abs(phase) < dur / 2.0
        flux[in_tr] -= depth_ppm / 1e6
    return time, flux


def test_synthetic_5p_p1_receives_verified_planet_candidate_verdict():
    """A 5-planet synthetic with all 5 signals present: the strongest
    signal (p1 = 12.0d, 500 ppm) MUST be classified as 'Verified Planet
    Candidate' once shape vetting returns 'Likely Planet', even when the
    periodogram-wide confidence_score is reduced by the other planets
    adding power to the periodogram.

    Pre-fix bug: gating the cross-vetting block on `is_valid` (which
    depends on confidence_score >= DETECTION_CONFIDENCE_FLOOR=7.0) caused
    this to be skipped, so `vetting_status` stayed at 'Likely Planet'.
    """
    time, flux = _build_synthetic_5p()
    result = detect_transit_candidate(
        time=time, flux=flux,
        target_name="SYN-5P-regression",
        data_source="synthetic",
        metadata={},
        snr_threshold=5.0,
    )
    assert result, "detect_transit_candidate returned empty dict"
    # The first BLS peak on a 5-planet curve is the strongest signal (p1).
    # Its period must be 12.0d +/- 1% (BLS resolution at 30k samples is
    # far better than 1% for short periods).
    period = float(result.get("period", 0.0))
    assert abs(period - 12.0) < 0.5, (
        f"BLS did not find p1 first: got period={period:.4f}d, expected 12.0d"
    )
    # The shape vet on a clean U-shape at this depth returns 'Likely Planet'.
    # The cross-vetting branch 1 (depth<0.03) MUST fire and upgrade this
    # to 'Verified Planet Candidate'.
    assert result["vetting_status"] == "Verified Planet Candidate", (
        f"cross-vetting was skipped; vetting_status={result['vetting_status']!r}. "
        f"snr={result.get('snr'):.3f}, confidence_score={result.get('confidence_score'):.3f}, "
        f"is_valid would have been (snr>{5.0}={result.get('snr', 0) > 5.0}) AND "
        f"(conf>={DETECTION_CONFIDENCE_FLOOR}={result.get('confidence_score', 0) >= DETECTION_CONFIDENCE_FLOOR}). "
        f"This is the round-2 I1 regression: see logs/diagnostic_run_round2_*.json."
    )
