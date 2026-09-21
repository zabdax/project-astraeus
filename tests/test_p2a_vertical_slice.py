"""P2-A vertical-slice backend test: one real target end to end.

PRD v4.1 §21 Phase 2 gate: one real target, real data, honest progress,
downloadable result — with the capability snapshot visible enough to state
truthfully whether TLS ran.

This test drives the cached Kepler-90 light curve (real photometry,
network-free) through the full Phase 1 stack — API → supervisor → worker
subprocess → engine — and asserts the structural properties P2-A exists
to prove:

* the job reaches COMPLETED with *measured* progress events
  (``running`` → ``iteration`` → exactly one ``done``);
* the downloadable ``AnalysisResult`` carries dataset identity and a
  candidate list (possibly empty — a clean zero-candidate run is still
  COMPLETED, never a stuck job);
* provenance is attached with the capability snapshot and an honest
  ``tls_outcome`` (``ran_pass``/``ran_fail``, never a silent pass).

One test, one pipeline run: the 45k-point curve costs minutes (BLS grid
+ serial TLS). Marked ``slow``: out of the fast gate, in the weekly
blocking gate.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from astraeus.api.auth import DEFAULT_OWNER, AuthState
from astraeus.jobs.store import JobStore
from astraeus.jobs.supervisor import JobSupervisor

pytestmark = pytest.mark.slow

_CACHE_PATH = "benchmarks/cache/Kepler_90.npz"


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from astraeus.api.main import create_app

    store = JobStore(tmp_path / "astraeus.db")
    supervisor = JobSupervisor(store, artifact_root=tmp_path / "artifacts")
    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    app = create_app(auth=auth, supervisor=supervisor)
    return TestClient(app)


@pytest.fixture
def token() -> str:
    from astraeus.api.auth import create_access_token

    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    return create_access_token(auth, DEFAULT_OWNER)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _kepler90_inline() -> dict:
    data = np.load(_CACHE_PATH)
    return {
        "time": [float(v) for v in data["time"]],
        "flux": [float(v) for v in data["flux"]],
        "flux_err": [float(v) for v in data["flux_err"]],
        "target_name": "Kepler-90",
    }


def _wait_for_completion(client, token: str, job_id: str, *, timeout: float) -> dict:
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}", headers=_auth(token))
        assert resp.status_code == 200
        if resp.json()["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return resp.json()
        _time.sleep(5.0)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_p2a_real_target_end_to_end(client, token):
    resp = client.post(
        "/jobs",
        json={"dataset": _kepler90_inline(), "max_signals": 1},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["job_id"]

    record = _wait_for_completion(client, token, job_id, timeout=1500)
    assert record["status"] == "COMPLETED", f"job failed: {record.get('error')}"

    # Downloadable result with dataset identity and a candidate list.
    result = client.get(f"/jobs/{job_id}/result", headers=_auth(token))
    assert result.status_code == 200, result.text
    body = result.json()
    assert "dataset_id" in body["result"]
    assert body["result"]["status"] == "COMPLETED"
    assert isinstance(body["result"].get("candidates"), list)

    # Provenance states truthfully whether TLS ran.  Run-level `tls`
    # is a roll-up (attempted + counts); per-candidate detail lives on
    # each candidate's `tls.outcome` (contracts/analysis_result.py:517).
    provenance = body["provenance"]
    assert provenance is not None
    capability = provenance.get("capability_snapshot") or {}
    assert capability.get("tls") is True, f"TLS backend must be present: {capability!r}"
    tls_block = body["result"].get("tls", {})
    assert tls_block.get("attempted") is True, f"TLS must have run: {tls_block!r}"
    assert (tls_block.get("n_ran_pass", 0) + tls_block.get("n_ran_fail", 0)) >= 1, (
        f"at least one measured TLS outcome required: {tls_block!r}"
    )
    for cand in body["result"]["candidates"]:
        assert cand.get("tls", {}).get("outcome") in ("ran_pass", "ran_fail"), (
            f"candidate TLS outcome must be measured: {cand.get('tls')!r}"
        )

    # Honest event trail: measured progress, exactly one terminal event.
    with client.stream("GET", f"/jobs/{job_id}/events", headers=_auth(token)) as stream:
        text = b"".join(stream.iter_bytes()).decode("utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("data: ")]
    types = [json.loads(ln[len("data: "):])["type"] for ln in lines]
    assert "running" in types
    assert "iteration" in types
    assert types.count("done") == 1
    assert "error" not in types
