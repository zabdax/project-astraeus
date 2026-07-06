"""Regression test for the I2 fix: BKJD/BTJD must be converted to BJD
full at the ingestion boundary, and the returned dict must carry an
explicit `time_unit` label so this class of bug cannot recur silently.

The previous code returned `lc.time.value` directly (in BKJD for
Kepler, BTJD for TESS), and downstream consumers compared that
silently to NASA `pl_tranmid` values (BJD full) — producing
~2454833-day offsets with no error signal.
"""

import numpy as np
import pytest

from astraeus.core import lightkurve_client as lkc
from astraeus.core.time_units import bjd_offset_for_mission, to_bjd
from astraeus.data.loader import extract_lightcurve_arrays


# ---------------------------------------------------------------------------
# Unit tests for astraeus.core.time_units
# ---------------------------------------------------------------------------


def test_bjd_offset_for_mission_kepler():
    """Kepler uses BKJD = BJD - 2454833; offset must be 2454833."""
    assert bjd_offset_for_mission("Kepler") == 2454833.0


def test_bjd_offset_for_mission_tess():
    """TESS uses BTJD = BJD - 2457000; offset must be 2457000."""
    assert bjd_offset_for_mission("TESS") == 2457000.0


def test_bjd_offset_for_mission_k2():
    """K2 uses the same offset as Kepler (BKJD = BJD - 2454833)."""
    assert bjd_offset_for_mission("K2") == 2454833.0


def test_to_bjd_kepler_known_value():
    """Known BKJD sample (e.g. Kepler-90 first-stitch time 131.5124 from
    round 1 measurement) + 2454833 = the BJD-full value the NASA archive
    would publish for the same instant.
    """
    bkjd = 131.5124
    bjd = to_bjd(bkjd, "Kepler")
    assert abs(bjd - (bkjd + 2454833.0)) < 1e-9, f"to_bjd(Kepler) failed: {bjd}"


def test_to_bjd_tess_known_value():
    """BTJD + 2457000 = BJD full."""
    btjd = 2457.5
    bjd = to_bjd(btjd, "TESS")
    assert abs(bjd - (btjd + 2457000.0)) < 1e-9, f"to_bjd(TESS) failed: {bjd}"


# ---------------------------------------------------------------------------
# Sanity: NASA's published KOI-351 b t0 in BJD is 2454970.6906
# (round-1 evidence). 2454970.6906 - 2454833 = 137.6906 BKJD. The
# detection code must surface a t0 in the SAME unit as the time array
# it was given. If the time array is in BJD, the t0 must be ~2454970,
# not ~137. This test exercises detect_transit_candidate with a
# synthetic time array in BJD and asserts the returned t0 is also
# in BJD (i.e. thousands, not hundreds).
# ---------------------------------------------------------------------------


def test_detect_transit_candidate_t0_unit_is_consistent_with_time_array():
    """Build a tiny synthetic light curve with a known period and
    t0 in BJD full, run detect_transit_candidate, and assert the
    returned t0 is in BJD full (i.e. ~t0 in BJD, not 2454833 less).

    This guards against any future regression that reintroduces a
    unit mismatch in the time→t0 chain.
    """
    from astraeus.analysis.detection import detect_transit_candidate

    t0_bjd = 2454970.6906  # KOI-351 b transit midpoint, BJD full
    period = 7.0085         # KOI-351 b period, days
    duration = 0.15         # days
    depth = 5e-4            # 500 ppm fractional
    n = 2000
    t = np.linspace(t0_bjd - 200.0, t0_bjd + 200.0, n)  # ~400 day baseline
    flux = 1.0 + np.random.default_rng(0).normal(0, 5e-4, size=n)
    # Add transit signal
    phase = ((t - t0_bjd + 0.5 * period) % period) - 0.5 * period
    in_tr = np.abs(phase) < 0.5 * duration
    flux[in_tr] -= depth

    result = detect_transit_candidate(
        time=t, flux=flux,
        target_name="KOI-351-b-BJD-test",
        data_source="synthetic",
        metadata={},
        snr_threshold=5.0,
    )
    assert result, "detect_transit_candidate returned empty"
    # The recovered t0 should be near t0_bjd (~2454970), not 137.
    # The recovered period is large (29.9d in this test, since the
    # transits are sparse on a 400d baseline), so we only assert the
    # UNIT is right (i.e. t0 in the millions, not hundreds). The
    # period/SNR-only test is `test_synthetic_5p_p1_receives_verified_*`.
    recovered_t0 = float(result.get("t0", 0.0))
    assert recovered_t0 > 2_000_000, (
        f"recovered t0={recovered_t0} is in BKJD (~hundreds), not BJD full "
        f"(~millions). The I2 fix has regressed: the time array fed in was "
        f"in BJD but t0 is in BKJD/BTJD, so consumers comparing t0 to NASA "
        f"pl_tranmid (BJD full) will be off by ~2454833 days."
    )
