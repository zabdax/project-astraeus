"""P4-B detection-floor FAP calibration tests (measurement-only, TDD).

These tests characterize the BLS confidence statistic
(``BLSSearchEngine.search`` ``confidence_score`` = peak power / median)
on synthetic fixtures. They assert:

1. Determinism: the seeded noise-only runner reproduces exactly.
2. Monotonicity: empirical FAP is non-increasing in confidence threshold.
3. Gap: the recommended floor sits strictly inside the measured
   noise-max / signal-min gap, with FAP 0.0 and efficiency 1.0 there.

Measurement-only: nothing here changes any detection gate
(``DETECTION_CONFIDENCE_FLOOR`` stays 7.0).

Runtime: 28 short-baseline BLS runs at ~1s each (frequency_factor=5.0
coarsened grid, 30 d baseline, 1200 cadences); well under 180 s total.
"""

import numpy as np

from astraeus.analysis import fap_calibration as fc


def test_noise_confidences_deterministic_under_seed():
    first = fc.run_noise_confidences(n_trials=4, seed=777)
    second = fc.run_noise_confidences(n_trials=4, seed=777)
    np.testing.assert_array_equal(first, second)


def test_empirical_fap_monotonic_in_confidence():
    noise = fc.run_noise_confidences(n_trials=8, seed=20240)
    assert noise.size == 8
    assert np.all(np.isfinite(noise))

    thresholds = np.linspace(float(noise.min()) - 0.5, float(noise.max()) + 0.5, 9)
    faps = np.array([fc.empirical_fap(noise, t) for t in thresholds])

    # FAP is non-increasing as the threshold rises.
    assert np.all(faps[:-1] >= faps[1:])
    # Boundary semantics: everything passes a zero threshold, nothing
    # passes strictly above the observed noise maximum.
    assert fc.empirical_fap(noise, 0.0) == 1.0
    assert fc.empirical_fap(noise, float(noise.max()) + 1.0) == 0.0


def test_recommended_floor_inside_noise_signal_gap():
    noise = fc.run_noise_confidences(n_trials=8, seed=4242)
    signal = fc.run_signal_confidences(n_trials=4, seed=9001)

    floor, rationale = fc.recommend_floor(noise, signal)

    assert float(noise.max()) < float(floor) < float(signal.min())
    assert isinstance(rationale, str) and rationale.strip() != ""

    # At the recommended floor: zero false alarms on the measured noise
    # realizations and full recovery of the injected signals.
    assert fc.empirical_fap(noise, floor) == 0.0
    assert fc.detection_efficiency(signal, floor) == 1.0

    # Detection efficiency is non-increasing in threshold.
    grid = np.linspace(float(noise.min()), float(signal.max()), 7)
    effs = fc.efficiency_vs_threshold(signal, grid)
    assert np.all(effs[:-1] >= effs[1:])
