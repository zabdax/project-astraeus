"""Phase 0: the four TLS outcomes, produced by the real detection path.

Covers PRD v4.1 §6 (TLS outcome model) and the fail-closed correction at
`detection.py`. These tests drive `detect_transit_candidate` directly so
every outcome is produced by the production code path, not a mock of it.

The distinction under test (PRD §7):
    environment failure  !=  scientific rejection  !=  valid negative result
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from astraeus.core.capabilities import TlsOutcome


def _synthetic_curve(n: int = 300, seed: int = 20260917) -> tuple[np.ndarray, np.ndarray]:
    """Small seeded light curve with one injected transit (BLS period > 0)."""
    rng = np.random.default_rng(seed=seed)
    t = np.arange(n, dtype=np.float64) * 0.02
    flux = 1.0 + 1e-3 * rng.standard_normal(n)
    period, t0, duration, depth = 1.2, 0.3, 0.05, 0.008
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    flux[np.abs(phase) < 0.5 * duration] -= depth
    return t, flux


def _block_module(monkeypatch, name: str) -> None:
    """Make `import <name>` raise ImportError in the code under test.

    Setting sys.modules[name] = None is the standard mechanism: CPython's
    import system raises ModuleNotFoundError for a None entry.
    """
    monkeypatch.setitem(sys.modules, name, None)


# ---------------------------------------------------------------------------
# env_unavailable -- missing backend (was: tls_valid = True "fail open")
# ---------------------------------------------------------------------------


def test_missing_tls_backend_produces_env_unavailable(monkeypatch):
    """PRD §4.2: missing transitleastsquares must NOT yield a validated
    candidate. Before Phase 0 this site set tls_valid = True."""
    _block_module(monkeypatch, "transitleastsquares")
    from astraeus.analysis.detection import detect_transit_candidate

    t, flux = _synthetic_curve()
    result = detect_transit_candidate(
        time=t, flux=flux, target_name="phase0-probe", data_source="synthetic",
        metadata={},
    )

    assert result["tls_outcome"] == TlsOutcome.ENV_UNAVAILABLE.value
    # THE core fail-closed assertion: a missing gate is never a pass.
    assert result["tls_valid"] is False
    # And it is distinguishable from a scientific rejection.
    assert result["tls_environment_error"] is not None
    assert result["tls_scientific_error"] is None


def test_missing_tls_does_not_produce_validated_candidate(monkeypatch):
    """The emission gate must not emit a candidate when the TLS gate
    could not execute."""
    _block_module(monkeypatch, "transitleastsquares")
    from astraeus.analysis.detection import detect_transit_candidate

    t, flux = _synthetic_curve()
    result = detect_transit_candidate(time=t, flux=flux, metadata={})

    assert result["is_candidate"] is False
    assert not result["vetting_status"].startswith("Verified Planet Candidate")


def test_missing_tls_result_carries_capability_snapshot(monkeypatch):
    """PRD §22: the result must report which backends were actually
    available so a caller can never mistake the run for a complete one."""
    _block_module(monkeypatch, "transitleastsquares")
    from astraeus.analysis.detection import detect_transit_candidate

    result = detect_transit_candidate(*_synthetic_curve(), metadata={})
    assert result["backends_available"]["tls"] is False
    assert result["backends_available"]["wotan"] is True


# ---------------------------------------------------------------------------
# env_unavailable -- installed-but-raising (the J2c infra failure mode)
# ---------------------------------------------------------------------------


def _install_fake_tls_that_raises(monkeypatch, exc_type, message):
    """Patch transitleastsquares so model.power raises exc_type."""
    class _FakeModel:
        def power(self, **kwargs):
            raise exc_type(message)

    class _FakeTLS:
        def transitleastsquares(self, t, y):
            return _FakeModel()

    fake = types.ModuleType("transitleastsquares")
    fake.transitleastsquares = _FakeTLS().transitleastsquares
    monkeypatch.setitem(sys.modules, "transitleastsquares", fake)


@pytest.mark.parametrize(
    "exc_type",
    [AssertionError, RuntimeError],
)
def test_tls_infra_failure_is_env_unavailable(monkeypatch, exc_type):
    """An infrastructure failure (the Windows nested-multiprocessing
    AssertionError, or OOM/fork failures) is an environment failure, not
    a scientific rejection. Locked jointly with
    test_tls_call_path_contract.py."""
    _install_fake_tls_that_raises(
        monkeypatch, exc_type, "daemonic processes are not allowed to have children",
    )
    from astraeus.analysis.detection import detect_transit_candidate

    result = detect_transit_candidate(*_synthetic_curve(), metadata={})

    assert result["tls_outcome"] == TlsOutcome.ENV_UNAVAILABLE.value
    assert result["tls_valid"] is False
    assert exc_type.__name__ in (result["tls_environment_error"] or "")
    assert result["tls_scientific_error"] is None


def test_tls_infra_failure_is_observable_on_stdout(monkeypatch, capsys):
    """The [TLS-INFRA-ERROR] sentinel must reach stdout so a job's
    warnings reach the caller (PRD §4.2 item 5). Mirrors the existing
    contract test, via the logging handler rather than print()."""
    _install_fake_tls_that_raises(monkeypatch, AssertionError, "infra failure")
    from astraeus.analysis.detection import detect_transit_candidate

    detect_transit_candidate(*_synthetic_curve(), metadata={})
    captured = capsys.readouterr()
    assert "[TLS-INFRA-ERROR]" in captured.out


def test_tls_scientific_failure_is_ran_fail(monkeypatch):
    """A genuine scientific failure (TLS ran but could not produce a
    verdict) is ran_fail, distinct from env_unavailable."""
    _install_fake_tls_that_raises(monkeypatch, ValueError, "numba type error")
    from astraeus.analysis.detection import detect_transit_candidate

    result = detect_transit_candidate(*_synthetic_curve(), metadata={})

    assert result["tls_outcome"] == TlsOutcome.RAN_FAIL.value
    assert result["tls_valid"] is False
    assert result["tls_scientific_error"] is not None
    assert result["tls_environment_error"] is None


# ---------------------------------------------------------------------------
# not_attempted + the tls_valid derivation contract
# ---------------------------------------------------------------------------


def test_not_attempted_when_no_period_to_validate(monkeypatch):
    """When BLS yields no period, the gate is intentionally not run."""
    from astraeus.analysis import detection as detection_mod

    monkeypatch.setattr(
        detection_mod.BLSSearchEngine,
        "search",
        staticmethod(lambda t, f, known_periods=None: {
            "period": 0.0, "snr": 0.0, "depth": 0.0, "t0": 0.0,
            "duration": 0.0, "confidence_score": 0.0, "periodogram": None,
        }),
    )
    result = detection_mod.detect_transit_candidate(*_synthetic_curve(), metadata={})
    assert result["tls_outcome"] == TlsOutcome.NOT_ATTEMPTED.value
    assert result["tls_valid"] is False


def test_tls_valid_is_true_only_on_ran_pass(monkeypatch):
    """Derivation contract: tls_valid may be True ONLY when the gate
    actually passed. This is the property that makes the boolean safe to
    keep as a derived field."""
    _block_module(monkeypatch, "transitleastsquares")
    from astraeus.analysis.detection import detect_transit_candidate

    result = detect_transit_candidate(*_synthetic_curve(), metadata={})
    assert result["tls_outcome"] != TlsOutcome.RAN_PASS.value
    assert result["tls_valid"] is False


def test_real_detection_reports_a_valid_tls_outcome():
    """Against the installed backend, a real run must report one of the
    four states (never a missing or invalid key)."""
    from astraeus.analysis.detection import detect_transit_candidate

    result = detect_transit_candidate(*_synthetic_curve(), metadata={})
    valid = {o.value for o in TlsOutcome}
    assert result["tls_outcome"] in valid
    assert result["tls_valid"] == (result["tls_outcome"] == TlsOutcome.RAN_PASS.value)
