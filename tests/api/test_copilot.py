"""Tests for the copilot endpoint (P3-G).

Fast by construction: with no provider configured the endpoint streams an
honest UNAVAILABLE message without calling any LLM. A copilot that needs
a network/credential to test is a copilot that lies in CI.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from astraeus.api.auth import DEFAULT_OWNER, AuthState, create_access_token
from astraeus.jobs.store import JobStore
from astraeus.jobs.supervisor import JobSupervisor

pytestmark = pytest.mark.smoke


@pytest.fixture
def client(tmp_path):
    from astraeus.api.main import create_app

    store = JobStore(tmp_path / "astraeus.db")
    supervisor = JobSupervisor(store, artifact_root=tmp_path / "artifacts")
    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    return TestClient(create_app(auth=auth, supervisor=supervisor))


@pytest.fixture
def token() -> str:
    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    return create_access_token(auth, DEFAULT_OWNER)


def _result() -> dict:
    return {
        "schema_version": "1",
        "job_id": "j",
        "target_id": "Kepler-90",
        "dataset_id": "d",
        "status": "COMPLETED",
        "candidates": [],
        "tls": {"attempted": True, "n_ran_pass": 0, "n_ran_fail": 1,
                "n_env_unavailable": 0, "n_not_attempted": 0,
                "environment_error": None},
        "capability_snapshot": {"tls": True},
        "warnings": [],
    }


def _stream_events(resp) -> list[dict]:
    return [json.loads(line[len("data: "):])
            for line in resp.text.splitlines() if line.startswith("data: ")]


def test_explain_without_provider_streams_unavailable(client, token):
    resp = client.post(
        "/copilot/explain",
        json={"result": _result()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    events = _stream_events(resp)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "evidence"
    assert "n_ran_fail" in events[0]["digest"]
    assert kinds[-1] == "done"
    text = next(e["delta"] for e in events if e["kind"] == "text")
    assert text.startswith("UNAVAILABLE")


def test_explain_requires_auth(client):
    resp = client.post("/copilot/explain", json={"result": _result()})
    assert resp.status_code in (401, 403)
