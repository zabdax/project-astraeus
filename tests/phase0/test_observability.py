"""Phase 0: scientific observability (PRD v4.1 §11 / §21 / §22).

Requirements under test:

* A scientific backend failure must become observable through logging --
  never a silent substitution or a swallowed exception.
* A result must carry which detrending estimator and which subtraction
  backend actually ran, so a fallback execution is never represented as
  the preferred scientific backend.
* The wotan fallback is permitted only as an explicitly non-production
  path, and must be logged rather than silent.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pytest

from astraeus.analysis.detrending import (
    METHOD_SCIPY_MEDIAN,
    METHOD_WOTAN_BIWEIGHT,
    DetrendingEngine,
)
from astraeus.core.capabilities import (
    SUBTRACTION_BACKEND_BATMAN,
    SUBTRACTION_BACKEND_TRAPEZOID,
    BackendId,
    get_logger,
)


def _flat_curve(n: int = 400, seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=seed)
    t = np.arange(n, dtype=np.float64) * 0.05
    flux = 1.0 + 0.02 * rng.standard_normal(n)
    return t, flux


# ---------------------------------------------------------------------------
# Which estimator actually ran
# ---------------------------------------------------------------------------


def test_detrend_reports_wotan_when_available():
    """The preferred backend must be identifiable on the result."""
    t, flux = _flat_curve()
    _, method = DetrendingEngine.detrend_with_method(t, flux, stellar_rotation_period_days=2.0)
    assert method == METHOD_WOTAN_BIWEIGHT


def test_detrend_reports_scipy_when_wotan_unavailable(monkeypatch):
    """The fallback must be labelled distinctly -- a scipy median-filter
    run is NOT equivalent to wotan biweight (PRD §9)."""
    # Patch the single authoritative probe so the fail-closed gate and
    # the branch decision agree (detrending delegates at call time).
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    t, flux = _flat_curve()
    _, method = DetrendingEngine.detrend_with_method(t, flux, 2.0)
    assert method == METHOD_SCIPY_MEDIAN


def test_detrend_fallback_is_logged_not_silent(monkeypatch, caplog):
    """A non-production substitution must be observable (PRD §9)."""
    # Patch the single authoritative probe so the fail-closed gate and
    # the branch decision agree (detrending delegates at call time).
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    t, flux = _flat_curve()
    with caplog.at_level(logging.WARNING, logger="astraeus"):
        DetrendingEngine.detrend_with_method(t, flux, 2.0)
    assert any("wotan" in r.message.lower() for r in caplog.records), (
        "The scipy median-filter fallback must log a WARNING naming wotan."
    )


def test_detrend_fails_closed_when_required_and_missing(monkeypatch):
    """require_wotan=True must fail closed instead of substituting."""
    # Patch the single authoritative probe so the fail-closed gate and
    # the branch decision agree (detrending delegates at call time).
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    t, flux = _flat_curve()
    with pytest.raises(Exception) as excinfo:  # BackendUnavailable
        DetrendingEngine.detrend_with_method(t, flux, 2.0, require_wotan=True)
    assert "wotan" in str(excinfo.value).lower()


def test_installed_but_failing_wotan_is_not_silent(monkeypatch, caplog):
    """PRD §9: an installed-but-raising backend must not be silently
    transformed into a different algorithm without observability."""
    import wotan

    monkeypatch.setattr(
        wotan, "flatten",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic wotan failure")),
    )
    t, flux = _flat_curve()
    with caplog.at_level(logging.ERROR, logger="astraeus"):
        # Non-production path: logs + falls back.
        DetrendingEngine.detrend_with_method(t, flux, 2.0, require_wotan=False)
    assert any("wotan" in r.message.lower() and r.levelno >= logging.WARNING
               for r in caplog.records)


def test_installed_but_failing_wotan_raises_in_production(monkeypatch):
    import wotan

    monkeypatch.setattr(
        wotan, "flatten",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic wotan failure")),
    )
    t, flux = _flat_curve()
    with pytest.raises(RuntimeError):
        DetrendingEngine.detrend_with_method(t, flux, 2.0, require_wotan=True)


# ---------------------------------------------------------------------------
# Which subtraction backend actually ran
# ---------------------------------------------------------------------------


def test_subtraction_records_batman_when_available():
    from astraeus.core.orchestrator import subtract_planetary_signal

    t = np.arange(500, dtype=np.float64) * 0.02
    flux = np.ones(500)
    record: dict = {}
    subtract_planetary_signal(
        flux, t, period=2.0, epoch=0.5, duration=0.1, depth_ppm=2000.0,
        metadata={}, record=record,
    )
    assert record["subtraction_backend"] == SUBTRACTION_BACKEND_BATMAN
    assert record["subtraction_backend_available"] is True


def test_subtraction_records_trapezoid_when_batman_unavailable(monkeypatch):
    """PRD §10: a fallback execution must be labelled so it is never
    represented as equivalent to the preferred scientific backend."""
    monkeypatch.setattr(
        "astraeus.core.orchestrator.is_backend_available",
        lambda backend: False if backend is BackendId.BATMAN else True,
    )
    from astraeus.core.orchestrator import subtract_planetary_signal

    t = np.arange(500, dtype=np.float64) * 0.02
    flux = np.ones(500)
    record: dict = {}
    subtract_planetary_signal(
        flux, t, period=2.0, epoch=0.5, duration=0.1, depth_ppm=2000.0,
        metadata={}, record=record,
    )
    assert record["subtraction_backend"] == SUBTRACTION_BACKEND_TRAPEZOID
    assert record["subtraction_backend_available"] is False


def test_batman_absence_is_logged_not_silent(monkeypatch, caplog):
    monkeypatch.setattr(
        "astraeus.core.orchestrator.is_backend_available",
        lambda backend: False if backend is BackendId.BATMAN else True,
    )
    from astraeus.core.orchestrator import subtract_planetary_signal

    t = np.arange(200, dtype=np.float64) * 0.02
    flux = np.ones(200)
    with caplog.at_level(logging.WARNING, logger="astraeus"):
        subtract_planetary_signal(flux, t, 2.0, 0.5, 0.1, 2000.0)
    assert any("batman" in r.message.lower() for r in caplog.records)


def test_subtraction_without_record_still_returns_flux():
    """Backwards compatibility: the record out-param is optional."""
    from astraeus.core.orchestrator import subtract_planetary_signal

    t = np.arange(200, dtype=np.float64) * 0.02
    flux = np.ones(200)
    out = subtract_planetary_signal(flux, t, 2.0, 0.5, 0.1, 2000.0)
    assert isinstance(out, np.ndarray)
    assert out.shape == flux.shape


# ---------------------------------------------------------------------------
# Logging plumbing
# ---------------------------------------------------------------------------


def test_astraeus_logger_emits_to_current_stdout(monkeypatch, capsys):
    """The logging handler resolves sys.stdout dynamically, so worker
    warnings reach the caller and captured-stdout contract tests work
    (PRD §4.2 item 5)."""
    get_logger("probe").error("[OBSERVABILITY-PROBE] sentinel")
    captured = capsys.readouterr()
    assert "[OBSERVABILITY-PROBE]" in captured.out


def test_astraeus_logger_is_configured_once():
    """Idempotency: repeated get_logger calls must not stack handlers."""
    import logging as logging_mod

    get_logger("a")
    get_logger("b")
    root = logging_mod.getLogger("astraeus")
    from astraeus.core.capabilities import _StdoutHandler

    handlers = [h for h in root.handlers if isinstance(h, _StdoutHandler)]
    assert len(handlers) == 1
