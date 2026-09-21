"""Tests for the API job routes (P1-H).

Two tiers, matching the repo's convention:

* **Validation / ownership / scoping** tests insert job rows directly into
  the store -- they assert the HTTP contract without paying for a pipeline
  run, so they stay in the fast gate.
* **End-to-end** tests submit a real job through the worker subprocess and
  carry the ``smoke`` marker (the real pipeline runs; TLS has a fixed
  floor cost, P05-A).

The PRD §13.1 properties under test: owner scoping by store query (not
post-hoc filtering), fail-closed auth, input validation on target IDs, and
404s that do not distinguish "not found" from "not yours".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from astraeus.api.auth import DEFAULT_OWNER, AuthState
from astraeus.jobs.store import JobRecord, JobStore
from astraeus.jobs.supervisor import JobSupervisor

pytestmark = pytest.mark.smoke

_TTL_HEADERS = {"Authorization": "Bearer {}"}


@pytest.fixture
def app_state(tmp_path):
    """An app whose supervisor talks to a throwaway store + artifact root."""
    from astraeus.api.main import create_app

    store = JobStore(tmp_path / "astraeus.db")
    supervisor = JobSupervisor(store, artifact_root=tmp_path / "artifacts")
    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    app = create_app(auth=auth, supervisor=supervisor)
    return app, auth, store


@pytest.fixture
def client(app_state):
    app, _auth, _store = app_state
    return TestClient(app)


@pytest.fixture
def token(app_state) -> str:
    _app, auth, _store = app_state
    from astraeus.api.auth import create_access_token

    return create_access_token(auth, DEFAULT_OWNER)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _noise_curve(n: int = 120, days: float = 10.0, seed: int = 7) -> dict:
    import numpy as np

    rng = np.random.default_rng(seed)
    time = np.linspace(0.0, days, n).tolist()
    flux = (1.0 + rng.normal(0, 0.001, n)).tolist()
    return {"time": time, "flux": flux, "target_name": "TINY-API-NOISE"}


# -- unauthenticated / health --------------------------------------------


def test_health_is_open_and_leaks_nothing(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["auth_enabled"] is True
    assert "key" not in str(body)


# -- validation ----------------------------------------------------------


def test_rejects_neither_dataset_nor_target(client, token):
    resp = client.post("/jobs", json={"max_signals": 2}, headers=_auth(token))
    assert resp.status_code == 422


def test_rejects_both_dataset_and_target(client, token):
    body = {
        "dataset": _noise_curve(),
        "target": {"name": "Kepler-90", "mission": "Kepler"},
    }
    resp = client.post("/jobs", json=body, headers=_auth(token))
    assert resp.status_code == 422


def test_rejects_short_arrays(client, token):
    bad = {"time": [1.0, 2.0], "flux": [1.0, 1.0], "target_name": "TINY"}
    resp = client.post("/jobs", json={"dataset": bad}, headers=_auth(token))
    assert resp.status_code == 422


def test_rejects_inconsistent_error_column(client, token):
    bad = {"time": [1.0] * 20, "flux": [1.0] * 20, "flux_err": [0.1] * 5, "target_name": "TINY"}
    resp = client.post("/jobs", json={"dataset": bad}, headers=_auth(token))
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "target",
    [
        "Kepler;90",      # shell metacharacter
        "../../etc/passwd",  # path traversal
        "Kepler-90\nrm",  # newline injection
        "",               # empty
        "x" * 100,        # too long
    ],
)
def test_rejects_hostile_target_ids(client, token, target):
    resp = client.post(
        "/jobs",
        json={"target": {"name": target, "mission": "Kepler"}},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_rejects_unknown_mission(client, token):
    resp = client.post(
        "/jobs",
        json={"target": {"name": "Kepler-90", "mission": "TESSSCOPE"}},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_rejects_out_of_range_max_signals(client, token):
    resp = client.post(
        "/jobs",
        json={"dataset": _noise_curve(), "max_signals": 99},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_rejects_oversized_body(client, token, monkeypatch):
    monkeypatch.setattr("astraeus.api.main.MAX_REQUEST_BYTES", 1024)
    big = {"dataset": _noise_curve(n=2000), "max_signals": 1}
    resp = client.post("/jobs", json=big, headers=_auth(token))
    assert resp.status_code == 413


# -- scoping and ownership -----------------------------------------------


def _seed_job(store, owner=DEFAULT_OWNER, job_id="job-1"):
    return store.create_job(
        JobRecord(job_id=job_id, target_name="TINY", owner_id=owner, max_iterations=1)
    )


def test_list_jobs_scoped_to_owner(client, token, app_state):
    _app, _auth_state, store = app_state
    _seed_job(store, owner=DEFAULT_OWNER, job_id="mine")
    _seed_job(store, owner="someone-else", job_id="theirs")
    resp = client.get("/jobs", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    ids = {j["job_id"] for j in body["jobs"]}
    assert ids == {"mine"}
    assert body["count"] == 1


def test_other_owners_job_is_404_not_403(client, token, app_state):
    _app, _auth_state, store = app_state
    _seed_job(store, owner="someone-else", job_id="theirs")
    resp = client.get("/jobs/theirs", headers=_auth(token))
    assert resp.status_code == 404
    # The message must not confirm existence.
    assert resp.json()["detail"] == "job not found"


def test_missing_job_is_404(client, token):
    resp = client.get("/jobs/does-not-exist", headers=_auth(token))
    assert resp.status_code == 404


def test_result_before_completion_is_404(client, token, app_state):
    _app, _auth_state, store = app_state
    _seed_job(store, job_id="pending")
    resp = client.get("/jobs/pending/result", headers=_auth(token))
    assert resp.status_code == 404


def test_cancel_terminal_job_is_409(client, token, app_state):
    from astraeus.contracts.analysis_result import JobStage, JobStatus

    _app, _auth_state, store = app_state
    store.create_job(JobRecord(job_id="done", target_name="TINY", max_iterations=1))
    store.transition("done", JobStatus.COMPLETED, JobStage.COMPLETED)
    resp = client.post("/jobs/done/cancel", headers=_auth(token))
    assert resp.status_code == 409


# -- end to end (real worker subprocess) ---------------------------------


def test_submit_and_read_back_result(client, token):
    """The vertical-slice contract: submit -> stream events -> read result
    with provenance attached (PRD §5/§7)."""
    resp = client.post(
        "/jobs",
        json={"dataset": _noise_curve(), "max_signals": 1, "snr_floor": 7.0},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["job_id"]
    assert resp.json()["owner_id"] == DEFAULT_OWNER

    # A noise curve yields a clean COMPLETED run with zero candidates --
    # the "DONE / 0 candidates" distinction the PRD gate cares about.
    record = _wait_for_completion(client, token, job_id, timeout=180)
    assert record["status"] == "COMPLETED"

    result = client.get(f"/jobs/{job_id}/result", headers=_auth(token))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["result"]["status"] == "COMPLETED"
    # Every API result carries provenance (PRD §5/§7).
    assert body["provenance"] is not None
    assert "dataset_id" in body["result"]


def test_events_stream_replays_the_trail(client, token):
    resp = client.post(
        "/jobs",
        json={"dataset": _noise_curve(), "max_signals": 1},
        headers=_auth(token),
    )
    job_id = resp.json()["job_id"]
    _wait_for_completion(client, token, job_id, timeout=180)

    with client.stream("GET", f"/jobs/{job_id}/events", headers=_auth(token)) as stream:
        text = b"".join(stream.iter_bytes()).decode("utf-8")
    # The replay must include the terminal event, and must not duplicate it.
    lines = [ln for ln in text.splitlines() if ln.startswith("data: ")]
    types = []
    import json as _json

    for line in lines:
        types.append(_json.loads(line[len("data: "):])["type"])
    assert "done" in types
    assert types.count("done") == 1


def _wait_for_completion(client, token, job_id, *, timeout: float) -> dict:
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}", headers=_auth(token))
        assert resp.status_code == 200
        if resp.json()["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return resp.json()
        _time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")
