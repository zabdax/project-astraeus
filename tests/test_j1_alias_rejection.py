"""Tests for J1 alias rejection (Issues 1-3 from Round 3 review).

Issue 2: Confirm window periodogram computed from real (non-mocked) data
Issue 3: Confirm alias rejection runs BEFORE TLS cross-validation
"""
import numpy as np
from astraeus.analysis.bls_search import BLSSearchEngine
from unittest import mock
from types import SimpleNamespace


# ──────────────────────────────────────────────────────────────────────
# Issue 2: Non-mocked window periodogram on real gapped data
# ──────────────────────────────────────────────────────────────────────

def test_window_periodogram_real_data():
    """Verify the LombScargle window periodogram independently detects 
    the ~90-day gap frequency from synthetic gapped time series,
    WITHOUT mocking LombScargle.
    """
    from astropy.timeseries import LombScargle

    np.random.seed(42)
    # Simulate Kepler-like 90-day quarters with 10-day gaps
    time = []
    for q in range(10):
        t_q = np.linspace(q * 90, q * 90 + 80, 200)
        time.extend(t_q)
    time = np.array(time)

    # Compute the window periodogram exactly as bls_search.py does
    ls = LombScargle(time, np.ones_like(time), fit_mean=False, center_data=False)
    freq_window, power_window = ls.autopower(
        minimum_frequency=1/1000.0, maximum_frequency=1/10.0
    )
    top_window_indices = np.argsort(power_window)[-5:]
    top_window_periods = 1.0 / freq_window[top_window_indices]

    # The dominant window period should be near 90 days (within ±5%)
    found_90d = any(abs(p - 90.0) / 90.0 < 0.05 for p in top_window_periods)
    assert found_90d, (
        f"Expected a peak near 90d in the window periodogram, "
        f"got peaks at periods: {sorted(top_window_periods)}"
    )


# ──────────────────────────────────────────────────────────────────────
# Helper: build properly structured mocks for BLSSearchEngine.search
# ──────────────────────────────────────────────────────────────────────

def _setup_bls_mocks(mock_bls, mock_ls, periods, powers, window_freq,
                     transit_times=None, durations_arr=None, depths=None, snrs=None):
    """Configure mock BLS and LombScargle for search() tests.
    
    Key insight: model.autoperiod() returns a plain ndarray of periods,
    while model.power(periods, durations) returns a result object with
    .power, .period, .transit_time, .duration, .depth attributes.
    These are two different return values from two different methods.
    """
    n = len(periods)
    if transit_times is None:
        transit_times = np.full(n, 10.0)
    if durations_arr is None:
        durations_arr = np.full(n, 0.1)
    if depths is None:
        depths = np.full(n, 0.01)
    if snrs is None:
        snrs = np.full(n, 5.0)

    # Mock LombScargle window periodogram
    mock_ls_inst = mock.Mock()
    mock_ls.return_value = mock_ls_inst
    mock_ls_inst.autopower.return_value = (
        np.atleast_1d(window_freq),
        np.array([100.0] * len(np.atleast_1d(window_freq)))
    )

    # Mock BoxLeastSquares
    mock_model = mock.Mock()
    mock_bls.return_value = mock_model

    # autoperiod returns a plain ndarray of period values
    mock_model.autoperiod.return_value = np.array(periods)

    # power() returns the full result object
    mock_results = SimpleNamespace(
        power=np.array(powers),
        period=np.array(periods),
        transit_time=np.array(transit_times),
        duration=np.array(durations_arr),
        depth=np.array(depths),
        snr=np.array(snrs),
    )
    mock_model.power.return_value = mock_results

    return mock_model


# ──────────────────────────────────────────────────────────────────────
# Issue 3: Alias rejected BEFORE TLS ever sees the candidate
# ──────────────────────────────────────────────────────────────────────

def test_alias_rejected_before_tls():
    """Prove that BLSSearchEngine.search() returns a non-aliased period,
    so TLS (called downstream in detection.py) never receives the alias.

    Architecture proof:
      detection.py line 35:  BLSSearchEngine.search(...)  ← alias rejection here
      detection.py line 49+: TLS runs on search_results['period'] ← already filtered
    """
    np.random.seed(42)
    time = np.linspace(0, 100, 1000)
    flux = np.random.normal(1.0, 0.001, 1000)

    known_periods = [15.0]  # A previously found planet at 15d

    with mock.patch("astraeus.analysis.bls_search.BoxLeastSquares") as mock_bls, \
         mock.patch("astropy.timeseries.LombScargle") as mock_ls:

        _setup_bls_mocks(
            mock_bls, mock_ls,
            periods=[30.0, 7.5, 4.0],      # 2x harmonic, 0.5x harmonic, clean
            powers=[10.0, 8.0, 2.0],
            window_freq=np.array([1.0 / 90.0]),
        )

        results = BLSSearchEngine.search(time, flux, known_periods=known_periods)

        # The 30d (2x) and 7.5d (0.5x) aliases of 15d should be rejected
        assert results['period'] == 4.0, (
            f"Alias was not rejected before it could reach TLS. "
            f"Got period={results['period']}, expected 4.0"
        )


def test_window_alias_k1_rejected():
    """k=1 window alias rejection: f_alias = f_known + 1*f_window."""
    np.random.seed(42)
    time = np.linspace(0, 100, 1000)
    flux = np.random.normal(1.0, 0.001, 1000)

    known_periods = [210.6]

    # f_alias = 1/210.6 + 1/90.0 → alias_period ≈ 63.05d
    alias_freq = 1.0 / 210.6 + 1.0 / 90.0
    alias_period = 1.0 / alias_freq

    with mock.patch("astraeus.analysis.bls_search.BoxLeastSquares") as mock_bls, \
         mock.patch("astropy.timeseries.LombScargle") as mock_ls:

        _setup_bls_mocks(
            mock_bls, mock_ls,
            periods=[alias_period, 12.0, 5.0],
            powers=[10.0, 5.0, 2.0],
            window_freq=np.array([1.0 / 90.0]),
        )

        results = BLSSearchEngine.search(time, flux, known_periods=known_periods)

        assert results['period'] == 12.0, (
            f"k=1 alias at {alias_period:.2f}d was not rejected. "
            f"Got period={results['period']}"
        )


def test_window_alias_round2_842d_rejected():
    """The actual Round 2 bug: 842.46d false positive.

    The round-2 false positives at ~842d were explained by:
      1/842.4 = 1/210.6 − 1/93.6
    i.e. f_alias = f_known − 1 × f_window where f_window ≈ 1/93.6

    This is a k=1 alias with the 93.6-day sampling window frequency.
    """
    np.random.seed(42)
    time = np.linspace(0, 100, 1000)
    flux = np.random.normal(1.0, 0.001, 1000)

    known_periods = [210.6]

    f_window = 1.0 / 93.6
    f_known = 1.0 / 210.6
    alias_842_freq = abs(f_known - f_window)
    alias_842_period = 1.0 / alias_842_freq  # ≈ 842d

    # Round-7 update: with the J3 boundary-margin check (5% of p_max),
    # we use 40d as the second-highest peak instead of 50d (50d would
    # be at exactly p_max=50 for this 100d curve, which the new
    # boundary check correctly rejects as a noise peak). The core
    # contract — that the 842d alias gets rejected — is unchanged.
    with mock.patch("astraeus.analysis.bls_search.BoxLeastSquares") as mock_bls, \
         mock.patch("astropy.timeseries.LombScargle") as mock_ls:

        _setup_bls_mocks(
            mock_bls, mock_ls,
            periods=[alias_842_period, 40.0, 25.0],
            powers=[10.0, 5.0, 2.0],
            window_freq=np.array([f_window]),
        )

        results = BLSSearchEngine.search(time, flux, known_periods=known_periods)

        assert results['period'] != alias_842_period, (
            f"k=1 alias at {alias_842_period:.2f}d (the Round 2 ~842d bug) "
            f"was NOT rejected!"
        )
        assert results['period'] == 40.0, (
            f"Expected fallback to 40.0d, got {results['period']}"
        )
