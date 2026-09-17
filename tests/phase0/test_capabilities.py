"""Phase 0: scientific backend capability snapshot and TLS outcome model.

Covers PRD v4.1 §5 (capability snapshot), §4.2 item 3 (tls_outcome enum)
and §22 (capability state carried on results).

The core invariant under test: the system reports structured, per-backend
availability -- never a single vague boolean -- and the TLS gate has four
mutually exclusive scientific states that cannot be confused with each
other.
"""

from __future__ import annotations

import json

import pytest

from astraeus.core.capabilities import (
    BackendId,
    BackendUnavailable,
    CapabilitySnapshot,
    TlsOutcome,
    capability_snapshot,
    is_backend_available,
    require_backend,
)


# ---------------------------------------------------------------------------
# Capability snapshot
# ---------------------------------------------------------------------------


def test_capability_snapshot_has_structured_per_backend_availability():
    """PRD §5: availability must be structured, not one global boolean."""
    snap = CapabilitySnapshot.current()
    payload = snap.to_dict()

    # The exact PRD §22 payload shape.
    assert set(payload) == {"batman", "wotan", "tls", "snapshot_version"}
    for key in ("batman", "wotan", "tls"):
        assert isinstance(payload[key], bool), f"{key} must be a bool"
    assert payload["snapshot_version"] >= 1


def test_capability_snapshot_is_json_serializable():
    """The payload must round-trip through JSON (result/provenance path)."""
    payload = CapabilitySnapshot.current().to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_capability_snapshot_distinguishes_backends():
    """PRD §5: 'wotan present but TLS missing' is a different situation
    from 'everything missing'. missing() must report exactly the absent
    subset, not a single boolean."""
    snap = CapabilitySnapshot(
        batman=True, wotan=True, tls=False,
    )
    assert snap.missing([BackendId.TLS]) == [BackendId.TLS]
    assert snap.missing([BackendId.WOTAN]) == []
    assert snap.missing([BackendId.WOTAN, BackendId.TLS]) == [BackendId.TLS]


def test_is_backend_available_returns_bool_for_every_backend():
    for backend in BackendId:
        assert isinstance(is_backend_available(backend), bool)


def test_capability_snapshot_probes_live_environment():
    """In this verified environment all three backends are installed, so
    the snapshot must report them present (this is the environment the
    282-test baseline runs in)."""
    snap = capability_snapshot()
    assert snap.wotan is True
    assert snap.tls is True


def test_capability_snapshot_extends_without_rewrite():
    """PRD §5: adding a future backend must not require rewriting the
    concept. Enumerating BackendId is the whole discovery surface."""
    assert {b.value for b in BackendId} == {"batman", "wotan", "tls"}


# ---------------------------------------------------------------------------
# TLS outcome model
# ---------------------------------------------------------------------------


def test_tls_outcome_has_exactly_four_mutually_exclusive_states():
    """PRD §4.2 item 3 / §6: the four states replace boolean tls_valid
    as the authoritative scientific state."""
    values = {o.value for o in TlsOutcome}
    assert values == {"ran_pass", "ran_fail", "env_unavailable", "not_attempted"}


def test_tls_outcome_renders_as_plain_string_on_results():
    """The enum must serialize to a plain string on a result dict so
    existing JSON consumers keep working."""
    assert TlsOutcome.RAN_PASS.value == "ran_pass"
    assert isinstance(TlsOutcome.ENV_UNAVAILABLE.value, str)


# ---------------------------------------------------------------------------
# require_backend / fail-closed
# ---------------------------------------------------------------------------


def test_require_backend_passes_when_available():
    """An available backend must not raise."""
    require_backend(BackendId.WOTAN)  # no exception expected


def test_require_backend_raises_structured_error_when_missing(monkeypatch):
    """PRD §4.2 item 2: a missing required backend is a structured
    failure with an identifiable backend, never a silent substitution."""
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    with pytest.raises(BackendUnavailable) as excinfo:
        require_backend(BackendId.TLS)

    err = excinfo.value
    assert err.backend is BackendId.TLS
    # The message must be human-readable and actionable.
    assert "transitleastsquares" in str(err) or "tls" in str(err)


def test_require_backend_skips_raise_when_operator_opts_into_diagnostics(monkeypatch):
    """ASTRAEUS_ALLOW_MISSING_BACKENDS=1 admits an explicitly
    non-production diagnostic run; production paths must never use it."""
    monkeypatch.setattr(
        "astraeus.core.capabilities.is_backend_available",
        lambda backend: False,
    )
    monkeypatch.setenv("ASTRAEUS_ALLOW_MISSING_BACKENDS", "1")
    require_backend(BackendId.TLS)  # must NOT raise


def test_missing_backends_allowed_is_false_by_default(monkeypatch):
    monkeypatch.delenv("ASTRAEUS_ALLOW_MISSING_BACKENDS", raising=False)
    from astraeus.core import capabilities as caps

    assert caps.missing_backends_allowed() is False
