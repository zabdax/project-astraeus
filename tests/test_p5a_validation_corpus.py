"""P5-A validation corpus + injection-recovery CI gate (slow, weekly gate).

Two halves:
- CORPUS: cached REAL curves with pinned outcomes. Expectations below
  were measured by probe_p5a.py (see handoff), never assumed.
- INJECTION: synthetic curves with known truth. A recovered period must
  match within 5% and the TLS gate must have executed (ran_*); the
  vetting verdict is asserted only where the probe measured it.

Nothing here runs in the fast gate: real curves cost minutes.
"""

import numpy as np
import pytest

from astraeus.analysis.detection import detect_transit_candidate

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Corpus: expectations measured 2026-09-22 (probe_p5a.py), filled on return.
# ---------------------------------------------------------------------------

CORPUS = {
    # Real hot Jupiter: recovered at archive period, TLS-confirmed.
    "Kepler_4d": {"period": 3.2136, "snr_min": 100.0,
                  "tls": "ran_pass", "candidate": True},
    # Spurious long-period peak, TLS-rejected: the honest negative.
    "Kepler_90": {"period": 616.44, "snr_min": 10.0,
                  "tls": "ran_fail", "candidate": False},
    # BLS 1.384 d vs archive 1.51 d (alias-class miss); TLS SDE 7.68 but
    # period-disagreement rejects: gate working as designed, candidate False.
    "TRAPPIST_1": {"period": 1.384, "snr_min": 5.0,
                   "tls": "ran_fail", "candidate": False},
}


def test_corpus_outcomes():
    """Cached real curves reproduce their pinned outcomes."""
    for name, expected in CORPUS.items():
        data = np.load(f"benchmarks/cache/{name}.npz")
        result = detect_transit_candidate(
            np.asarray(data["time"], dtype=float),
            np.asarray(data["flux"], dtype=float),
            target_name=name, data_source="cache", metadata={},
        )
        assert result["tls_outcome"] == expected["tls"], (
            f"{name}: tls {result['tls_outcome']!r} != {expected['tls']!r}"
        )
        assert result["is_candidate"] is expected["candidate"], (
            f"{name}: candidate {result['is_candidate']!r}"
        )
        assert float(result["snr"]) >= expected["snr_min"]
        found = float(result["period_days"])
        assert abs(found - expected["period"]) / expected["period"] < 0.05, (
            f"{name}: period {found} vs {expected['period']}"
        )


def _inject(period: float, depth: float, seed: int, n: int = 1500,
            baseline: float = 60.0, sigma: float = 0.0005):
    rng = np.random.default_rng(seed)
    time = np.sort(rng.uniform(0, baseline, n))
    phase = (time % period) / period
    dur_phase = 0.2 / period
    flux = np.ones_like(time)
    flux[np.abs(phase - 0.5) < dur_phase / 2] -= depth
    return time, flux + rng.normal(0, sigma, n)


@pytest.mark.parametrize(("period", "depth", "seed"), [
    (5.0, 0.01, 101),
    (10.0, 0.005, 102),
    (2.5, 0.02, 103),
])
def test_injection_recovery(period, depth, seed):
    time, flux = _inject(period, depth, seed)
    result = detect_transit_candidate(
        time, flux, target_name="P5A-INJECT",
        data_source="synthetic", metadata={},
    )
    assert result["tls_outcome"] in ("ran_pass", "ran_fail"), (
        f"TLS gate must execute, got {result['tls_outcome']!r}"
    )
    found = float(result["period_days"])
    assert abs(found - period) / period < 0.05, (
        f"injected P={period}d, recovered {found}d"
    )
