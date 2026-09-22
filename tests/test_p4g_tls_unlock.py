"""P4-G TLS multiprocessing unlock: flag-gated, default-off, daemon-proof.

The P05-A measurement (1.06x-2.08x, not 6-8x) scopes this bucket: the
unlock is a performance change behind `ASTRAEUS_TLS_THREADS`, never a
default. Unset/invalid env -> serial. Daemonic processes -> serial by
construction (the nested-pool crash becomes impossible, not merely
avoided). Production enablement additionally requires the Linux
re-measure (stated, not executed here).
"""

import pytest

from astraeus.analysis.detection import _tls_thread_count


def test_default_is_serial(monkeypatch):
    monkeypatch.delenv("ASTRAEUS_TLS_THREADS", raising=False)
    assert _tls_thread_count() == 1


@pytest.mark.parametrize("raw", ["0", "-3", "abc", "", "2.5"])
def test_invalid_env_falls_back_to_serial(monkeypatch, raw):
    monkeypatch.setenv("ASTRAEUS_TLS_THREADS", raw)
    assert _tls_thread_count() == 1


def test_valid_env_honored_up_to_cpu(monkeypatch):
    import multiprocessing

    monkeypatch.setenv("ASTRAEUS_TLS_THREADS", "2")
    assert _tls_thread_count() == 2
    monkeypatch.setenv("ASTRAEUS_TLS_THREADS", str(10**9))
    assert _tls_thread_count() == multiprocessing.cpu_count()


def test_explicit_argument_beats_env(monkeypatch):
    monkeypatch.setenv("ASTRAEUS_TLS_THREADS", "2")
    assert _tls_thread_count(None) == 2
    assert _tls_thread_count(4) == 4
    assert _tls_thread_count(0) == 1


def test_daemon_process_forces_serial(monkeypatch):
    """The J2 nested-pool crash is impossible by construction: a daemonic
    caller gets 1 no matter what was requested."""
    import multiprocessing

    monkeypatch.setenv("ASTRAEUS_TLS_THREADS", "8")

    class _DaemonProc:
        daemon = True

    monkeypatch.setattr(multiprocessing, "current_process",
                        lambda: _DaemonProc())
    assert _tls_thread_count(8) == 1


@pytest.mark.slow
def test_parallel_matches_serial_on_tiny_curve():
    """Bit-identical SDE/period across thread counts (performance change
    only). Marked slow: pays the TLS floor twice."""
    import numpy as np

    from astraeus.analysis import detection as det

    rng = np.random.default_rng(11)
    period, depth, dur = 5.0, 0.01, 0.2
    time = np.sort(rng.uniform(0, 60, 1500))
    phase = (time % period) / period
    flux = np.ones_like(time)
    flux[np.abs(phase - 0.5) < dur / period / 2] -= depth
    flux = flux + rng.normal(0, 0.0005, len(time))

    serial = det.detect_transit_candidate(
        time, flux, target_name="P4G-EQ", tls_threads=1)
    parallel = det.detect_transit_candidate(
        time, flux, target_name="P4G-EQ", tls_threads=2)
    assert serial["tls_sde"] == parallel["tls_sde"]
    assert serial["tls_period"] == parallel["tls_period"]
    assert serial["tls_outcome"] == parallel["tls_outcome"]
