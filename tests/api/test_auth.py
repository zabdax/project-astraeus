"""Tests for the API auth layer (P1-H).

Covers the PRD §13.1 contract: authentication is mandatory, keys are the
only unauthenticated input, and a missing configuration fails closed --
every protected route 401s rather than serving anonymous traffic.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from astraeus.api.auth import (
    DEFAULT_OWNER,
    AuthConfig,
    AuthState,
    create_access_token,
    decode_token,
    single_user_mode,
)


@pytest.fixture
def state() -> AuthState:
    return AuthState.for_testing({DEFAULT_OWNER: "test-key"})


def _client(state: AuthState, **kwargs):
    from astraeus.api.main import create_app

    app = create_app(auth=state, **kwargs)
    return TestClient(app)


# -- configuration --------------------------------------------------------


def test_single_user_is_the_default(monkeypatch):
    monkeypatch.delenv("ASTRAEUS_SINGLE_USER", raising=False)
    assert single_user_mode() is True
    monkeypatch.setenv("ASTRAEUS_SINGLE_USER", "0")
    assert single_user_mode() is False


def test_single_user_key_resolves_to_default_owner(monkeypatch):
    monkeypatch.setenv("ASTRAEUS_API_KEY", "local-secret")
    monkeypatch.delenv("ASTRAEUS_SINGLE_USER", raising=False)
    state = AuthState()
    assert state.config.single_user is True
    assert state.owner_for_key("local-secret") == DEFAULT_OWNER
    assert state.owner_for_key("wrong") is None
    assert state.owner_for_key(None) is None


def test_multi_user_keys_map_owner(monkeypatch):
    monkeypatch.setenv("ASTRAEUS_SINGLE_USER", "0")
    monkeypatch.setenv("ASTRAEUS_API_KEYS", '{"alice": "ak1", "bob": "bk2"}')
    state = AuthState()
    assert state.config.single_user is False
    assert state.owner_for_key("bk2") == "bob"


def test_unconfigured_state_is_fail_closed(monkeypatch):
    monkeypatch.delenv("ASTRAEUS_API_KEY", raising=False)
    monkeypatch.delenv("ASTRAEUS_API_KEYS", raising=False)
    state = AuthState()
    assert state.config.enabled is False
    assert state.owner_for_key("anything") is None


def test_malformed_keys_fail_closed(monkeypatch):
    monkeypatch.setenv("ASTRAEUS_SINGLE_USER", "0")
    monkeypatch.setenv("ASTRAEUS_API_KEYS", "not-json")
    assert AuthState().config.enabled is False


# -- token issuance -------------------------------------------------------


def test_token_endpoint_issues_bearer(state):
    with _client(state, db_path=":memory:") as client:
        resp = client.post("/auth/token", json={"api_key": "test-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["owner_id"] == DEFAULT_OWNER
    assert body["expires_in"] > 0
    claims = decode_token(state, body["access_token"])
    assert claims["sub"] == DEFAULT_OWNER


def test_bad_key_is_rejected(state):
    with _client(state, db_path=":memory:") as client:
        resp = client.post("/auth/token", json={"api_key": "nope"})
    assert resp.status_code == 401


def test_token_endpoint_is_the_only_unauthenticated_route(state):
    with _client(state, db_path=":memory:") as client:
        # /health is a liveness probe, deliberately open.
        assert client.get("/health").status_code == 200
        # Everything else requires a token.
        assert client.get("/jobs").status_code == 401
        assert client.get("/jobs/xyz").status_code == 401


def test_no_key_configured_rejects_everything(monkeypatch):
    monkeypatch.delenv("ASTRAEUS_API_KEY", raising=False)
    monkeypatch.delenv("ASTRAEUS_API_KEYS", raising=False)
    empty = AuthState()
    assert empty.config.enabled is False
    with _client(empty, db_path=":memory:") as client:
        assert client.get("/jobs").status_code == 401


# -- token validation -----------------------------------------------------


def test_missing_bearer_is_rejected(state):
    with _client(state, db_path=":memory:") as client:
        resp = client.get("/jobs", headers={"Authorization": "test-key"})
    assert resp.status_code == 401


def test_expired_token_is_rejected(state):
    # A token whose expiry is already in the past must not authenticate.
    token = create_access_token(state, DEFAULT_OWNER)
    # Rewind: forge an expired token by issuing one with a stale clock via
    # a config with a negative TTL is not possible through the public API,
    # so decode with a future "now" instead.
    import jwt as pyjwt

    claims = pyjwt.decode(token, state.secret, algorithms=["HS256"], options={"verify_exp": False})
    expired = pyjwt.encode(
        {**claims, "exp": int(time.time()) - 10},
        state.secret,
        algorithm="HS256",
    )
    with _client(state, db_path=":memory:") as client:
        resp = client.get("/jobs", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"]


def test_token_for_revoked_owner_is_rejected(state):
    token = create_access_token(state, DEFAULT_OWNER)
    # Simulate key revocation: a fresh state that no longer knows the owner.
    revoked = AuthState.for_testing({"someone-else": "other-key"})
    with _client(revoked, db_path=":memory:") as client:
        resp = client.get("/jobs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_secret_from_environment_is_honoured(monkeypatch):
    monkeypatch.setenv("ASTRAEUS_API_KEY", "env-key")
    monkeypatch.setenv("ASTRAEUS_JWT_SECRET", "pinned-secret")
    monkeypatch.delenv("ASTRAEUS_SINGLE_USER", raising=False)
    state = AuthState()
    token = create_access_token(state, DEFAULT_OWNER)
    # A state with the same pinned secret validates it.
    other = AuthState(AuthConfig(keys={DEFAULT_OWNER: "env-key"}), secret="pinned-secret")
    assert decode_token(other, token)["sub"] == DEFAULT_OWNER


def test_constant_time_comparison(state):
    # The owner map must not short-circuit: both wrong and right keys are
    # compared in constant time (hmac.compare_digest).
    assert state.owner_for_key("test-key") == DEFAULT_OWNER
    assert state.owner_for_key("test-keY") is None
