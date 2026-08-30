"""Integration test: detect_transit_candidate must write an experiment record.

The autouse fixture ``_suppress_save_experiment_log_during_tests``
(tests/conftest.py) patches ``astraeus.analysis.detection.save_experiment_log``
to a no-op for the whole suite so detector invocations stay hermetic w.r.t.
``logs/experiments.json``. That is the right hygiene default, but it leaves
the detector -> experiment-log integration completely untested: if the
``save_experiment_log(params, metadata, fig_paths)`` argument contract drifts,
nothing fails — yet the History page (``ui/pages``) consumes these records.

This module re-enables the real ``save_experiment_log`` for itself by
re-patching the detection call-site attribute with the underlying
logging-module function, and redirects
``astraeus.analysis.logging.LOG_FILE`` into ``tmp_path`` so the repo's
``logs/experiments.json`` is never touched. It then runs
``detect_transit_candidate`` on a small synthetic light curve and asserts
exactly one well-formed experiment record is written.

Run just this gate with::

    pytest tests/test_detector_experiment_log_integration.py -q
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import astraeus.analysis.logging as astraeus_logging
from astraeus.analysis.detection import detect_transit_candidate


def _synthetic_lightcurve(n_points: int = 800):
    """Small deterministic curve with a deep box transit at P=14.45d.

    Same shape as the fixture in ``tests/test_fetched_analyze_button.py``
    but fewer cadences: the 0.5% depth against 500 ppm noise is enough for
    BLS/TLS to recover the signal quickly (sub-minute, hence ``smoke``).
    """
    rng = np.random.default_rng(7)
    time_arr = np.linspace(0, 30, n_points)
    flux_arr = 1.0 + rng.normal(0, 0.0005, n_points)
    period, duration, depth = 14.45, 0.2, 0.005
    phases = time_arr % period
    in_transit = (phases < duration / 2) | (phases > period - duration / 2)
    flux_arr[in_transit] -= depth
    return time_arr, flux_arr


@pytest.mark.smoke
def test_detect_transit_candidate_writes_experiment_record(tmp_path, monkeypatch):
    """One detector call must append exactly one experiment-log record whose
    params carry the keys downstream consumers read.

    Patching happens in the test body (not a fixture) so it is guaranteed to
    run AFTER the conftest autouse no-op patch is already installed. Teardown
    stays consistent: monkeypatch restores the no-op lambda first, then the
    conftest fixture's context manager restores the original symbol.
    """
    # Undo the conftest no-op: bind the REAL logging-module function back
    # onto the detection call site (detection imports the symbol by name,
    # so the live binding lives on astraeus.analysis.detection).
    real_save = astraeus_logging.save_experiment_log
    monkeypatch.setattr(
        "astraeus.analysis.detection.save_experiment_log", real_save
    )
    # LOG_FILE is a module constant read at call time by
    # save_experiment_log/load_experiment_history — point it at tmp_path.
    log_file = tmp_path / "experiments.json"
    monkeypatch.setattr(astraeus_logging, "LOG_FILE", str(log_file))

    time_arr, flux_arr = _synthetic_lightcurve()
    result = detect_transit_candidate(
        time=time_arr,
        flux=flux_arr,
        target_name="EXPLOG-INTEGRATION",
        data_source="synthetic",
        metadata={"dataset": "synthetic_explog", "points": int(len(time_arr))},
    )

    # Sanity: the detector ran the full analysis path (an input-guard
    # early-return would be an empty dict and skip the log call).
    assert isinstance(result, dict) and result, (
        "detect_transit_candidate returned an empty result — the synthetic "
        "curve did not reach the analysis path, so this test verifies nothing"
    )

    assert log_file.exists(), (
        "detect_transit_candidate did not write the experiment log — "
        "save_experiment_log was never invoked by the detector (argument "
        "drift or the call was dropped)"
    )
    records = json.loads(log_file.read_text(encoding="utf-8"))
    assert len(records) == 1, (
        f"expected exactly 1 experiment record per detector call, "
        f"got {len(records)}"
    )
    params = records[0]["params"]
    for key in ("target_name", "period", "snr", "is_valid_candidate"):
        assert key in params, (
            f"experiment record params missing load-bearing key {key!r} "
            f"(got keys: {sorted(params)}); the History page consumes "
            "these records"
        )
    assert params["target_name"] == "EXPLOG-INTEGRATION"
    assert isinstance(params["is_valid_candidate"], bool), (
        f"is_valid_candidate should be a bool, got "
        f"{type(params['is_valid_candidate']).__name__}"
    )
