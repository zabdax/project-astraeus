"""End-to-end multi-planet search against real NASA Exoplanet Archive data.

These tests hit the network (MAST, NASA Exoplanet Archive TAP). Marked
``@pytest.mark.network`` and ``@pytest.mark.slow`` so they are excluded
from the fast CI gate via ``pytest -m "not network and not slow"``.

The two tests cover both real-data entry points the bucket-7 handoff
scripts exercised:

  - ``test_kepler90_multi_planet_via_universal_loader`` — uses
    ``universal_load_lightcurve("api", target, mission="Kepler")`` (from
    ``scripts/manual_tests/test_orchestrator.py``).

  - ``test_kepler90_multi_planet_via_load_nasa_lightcurve_uniqueness`` —
    uses ``load_nasa_lightcurve(target, mission="Kepler")`` and adds the
    pairwise period-uniqueness check (``abs(p_i/p_j - 1) >= 0.05``) that
    was implicit in ``scripts/manual_tests/run_test.py``.

The new tests live in a dedicated file rather than being consolidated
into ``tests/test_pipeline_smoke.py`` because that file is synthetic
(single planet, no network, marked ``@pytest.mark.smoke``); the
bucket5 plan's "consolidate where overlap exists" rule does not apply
to genuinely parallel coverage at a different abstraction level
(orchestrator + real data vs. detector + synthetic data).
"""
from __future__ import annotations

import pytest

from astraeus.core.orchestrator import run_multi_planet_search
from astraeus.data.loader import load_nasa_lightcurve, universal_load_lightcurve


_KEPLER_90 = "KIC 11442793"
_PERIOD_UNIQUE_TOLERANCE = 0.05  # |p_i/p_j - 1| < 0.05 = duplicate


def _build_raw_lightcurve(time, flux, target_name, source):
    return {
        "time": time,
        "flux": flux,
        "target_name": target_name,
        "data_source": source,
        "metadata": {},
    }


@pytest.mark.network
@pytest.mark.slow
def test_kepler90_multi_planet_via_universal_loader():
    """Kepler-90 multi-planet search via universal_load_lightcurve API path.

    Asserts at least one candidate is returned, each candidate has
    positive period + vetting_status + snr.
    """
    t, f, _e = universal_load_lightcurve("api", _KEPLER_90, mission="Kepler")
    raw = _build_raw_lightcurve(t, f, _KEPLER_90, "NASA Exoplanet Archive")
    results = run_multi_planet_search(raw, max_signals=5, snr_floor=5.0)

    assert results is not None
    assert len(results) >= 1, f"expected >=1 candidate, got {len(results) if results else 0}"

    for cand in results:
        period = cand.get("period")
        assert period is not None and period > 0, (
            f"candidate missing positive period: {cand.get('period')!r}"
        )
        assert cand.get("vetting_status"), (
            f"candidate missing vetting_status: {cand.get('vetting_status')!r}"
        )
        snr = cand.get("snr")
        assert snr is not None, f"candidate missing snr: {snr!r}"


@pytest.mark.network
@pytest.mark.slow
def test_kepler90_multi_planet_via_load_nasa_lightcurve_uniqueness():
    """Kepler-90 multi-planet search via load_nasa_lightcurve + uniqueness check.

    Asserts at least one candidate is returned AND no two candidates
    have periods within 5% of each other (the implicit duplicate-period
    invariant from the original ``run_test.py`` script).
    """
    t, f, _e = load_nasa_lightcurve(_KEPLER_90, mission="Kepler")
    raw = _build_raw_lightcurve(t, f, _KEPLER_90, "MAST")
    results = run_multi_planet_search(raw, max_signals=6, snr_floor=5.0)

    assert results is not None
    assert len(results) >= 1, f"expected >=1 candidate, got {len(results) if results else 0}"

    periods = [
        c.get("period", 0.0) for c in results if c.get("period")
    ]
    for i, p_i in enumerate(periods):
        for j, p_j in enumerate(periods):
            if i == j or p_j <= 0:
                continue
            ratio = p_i / p_j
            assert abs(ratio - 1.0) >= _PERIOD_UNIQUE_TOLERANCE, (
                f"duplicate periods: c{i}={p_i:.4f}d, c{j}={p_j:.4f}d, ratio={ratio:.4f}"
            )
