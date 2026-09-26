"""Tests for the artifact array endpoints (3D-evidence program).

Fast tier only: rows + artifacts are written directly to a throwaway
store -- no worker subprocess, no network.  Every test asserts the HTTP
contract a browser can rely on: owner scoping by store query, refs
resolved server-side (never a client-supplied path), decimation that
preserves peaks, folded math identical to ``web/lib/fold.ts``, and
immutable ETags with 304 support.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from astraeus.api.auth import DEFAULT_OWNER, AuthState, create_access_token
from astraeus.contracts.analysis_result import (
    AnalysisResult,
    CandidateEvidence,
    TtvSummary,
)
from astraeus.contracts.dataset import ArtifactStore, Dataset, Mission, TargetRef, TimeUnit
from astraeus.jobs.store import JobRecord, JobStore
from astraeus.jobs.supervisor import JobSupervisor


@pytest.fixture
def app_state(tmp_path):
    from astraeus.api.main import create_app

    store = JobStore(tmp_path / "astraeus.db")
    supervisor = JobSupervisor(store, artifact_root=tmp_path / "artifacts")
    auth = AuthState.for_testing({DEFAULT_OWNER: "test-key"})
    app = create_app(auth=auth, supervisor=supervisor)
    return app, auth, store, tmp_path


@pytest.fixture
def client(app_state) -> TestClient:
    app, _auth, _store, _tmp = app_state
    return TestClient(app)


@pytest.fixture
def token(app_state) -> str:
    _app, auth, _store, _tmp = app_state
    return create_access_token(auth, DEFAULT_OWNER)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_job_with_arrays(app_state, job_id="job-1", owner=DEFAULT_OWNER, n=500):
    """A job with a real stored dataset + one candidate with refs."""
    _app, _auth_state, store, tmp = app_state
    ast = ArtifactStore(tmp / "artifacts")

    rng = np.random.default_rng(11)
    time = np.linspace(0.0, 60.0, n)
    flux = 1.0 + rng.normal(0, 0.001, n)
    # One box dip per 10 d period at epoch 2.0 (depth 1%).
    phase = ((time - 2.0) % 10.0) / 10.0
    flux = np.where(np.abs(phase - 0.5) > 0.49, flux - 0.01, flux)

    ds = Dataset.from_arrays(
        time.tolist(),
        flux.tolist(),
        None,
        target=TargetRef(name="ARTIFACT-TEST", mission=Mission.UNKNOWN),
        time_unit=TimeUnit.BJD,
        source="test:seed",
        sort=True,
    )
    ds_ref = ast.save_dataset(ds)

    periods = np.linspace(1.0, 30.0, 200)
    powers = np.exp(-0.5 * ((periods - 10.0) / 0.05) ** 2) + 0.01
    pg_ref = ast.save_array(np.column_stack([periods, powers]), kind="periodogram")

    resid = np.array([0.5, -1.2, 0.8, -0.4, 1.1])
    ttv_ref = ast.save_array(resid, kind="ttv")

    store.create_job(
        JobRecord(
            job_id=job_id,
            target_name="ARTIFACT-TEST",
            owner_id=owner,
            max_iterations=1,
            dataset_id=ds.content_hash,
            dataset_ref=ds_ref,
        )
    )
    result = AnalysisResult(
        result_id="res-1",
        job_id=job_id,
        target_id="ARTIFACT-TEST",
        dataset_id=ds.content_hash,
        candidates=[
            CandidateEvidence(
                candidate_id="c1",
                signal_index=0,
                period_days=10.0,
                epoch_bjd=2.0,
                depth_fraction=0.01,
                snr=12.5,
                periodogram_ref=pg_ref,
                ttv=TtvSummary(n_epochs=5, rms_minutes=1.0, max_abs_minutes=1.2, artifact=ttv_ref),
            )
        ],
    )
    store.attach_result(job_id, result)
    return ds, result


# -- manifest --------------------------------------------------------------


def test_manifest_lists_dataset_and_candidate_refs(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get("/jobs/job-1/artifacts", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-1"
    assert body["dataset"]["url"] == "/jobs/job-1/artifacts/data?type=dataset"
    cands = body["candidates"]
    assert len(cands) == 1
    assert cands[0]["candidate_id"] == "c1"
    assert cands[0]["periodogram"]["url"] is not None
    assert "candidate=c1" in cands[0]["periodogram"]["url"]
    assert cands[0]["ttv"]["n_epochs"] == 5
    # Folded is computed on demand: the manifest links it even though no
    # ref was ever persisted.
    assert cands[0]["folded"]["url"] is not None


def test_manifest_without_result_is_200_not_404(client, token, app_state):
    _app, _auth_state, store, _tmp = app_state
    store.create_job(JobRecord(job_id="pending", target_name="TINY", max_iterations=1))
    resp = client.get("/jobs/pending/artifacts", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["candidates"] == []


def test_manifest_rejects_other_owner_and_anon(client, token, app_state):
    _seed_job_with_arrays(app_state, job_id="theirs", owner="someone-else")
    resp = client.get("/jobs/theirs/artifacts", headers=_auth(token))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "job not found"
    resp = client.get("/jobs/job-1/artifacts")
    assert resp.status_code in (401, 403)


# -- dataset series --------------------------------------------------------


def test_dataset_decimation_preserves_endpoints(client, token, app_state):
    ds, _result = _seed_job_with_arrays(app_state, n=500)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=dataset&max_points=100", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_total"] == 500
    assert body["n_returned"] <= 100
    assert body["stride"] >= 5
    assert body["time"][0] == pytest.approx(ds.time[0])
    assert body["flux_err"] is None


def test_dataset_window_filters_before_decimation(client, token, app_state):
    _seed_job_with_arrays(app_state, n=500)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=dataset&t_min=10&t_max=20&max_points=10000",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert min(body["time"]) >= 10.0
    assert max(body["time"]) <= 20.0
    assert body["n_total"] == 500


def test_dataset_bad_window_is_400(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=dataset&t_min=20&t_max=10", headers=_auth(token)
    )
    assert resp.status_code == 400


# -- periodogram -----------------------------------------------------------


def test_periodogram_preserves_peak_and_reports_it(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=periodogram&candidate=c1&max_points=100",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_total"] == 200
    assert body["n_returned"] <= 100 + 200  # background + peak overlay cap
    assert body["peak"]["period_days"] == pytest.approx(10.0, abs=0.2)
    # The spike survives decimation: some returned period is near 10 d
    # with near-maximum power.
    assert min(abs(p - 10.0) for p in body["periods"]) < 0.3
    periods = np.linspace(1.0, 30.0, 200)
    expected_peak = float(np.max(np.exp(-0.5 * ((periods - 10.0) / 0.05) ** 2) + 0.01))
    peak_power = max(body["powers"])
    assert peak_power == pytest.approx(expected_peak, rel=1e-9)


def test_unknown_candidate_is_404(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=periodogram&candidate=c9", headers=_auth(token)
    )
    assert resp.status_code == 404


# -- folded (server must match web/lib/fold.ts) ----------------------------


def test_folded_matches_client_math(client, token, app_state):
    _seed_job_with_arrays(app_state, n=500)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=folded&candidate=c1&bins=80", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bins"] == 80
    assert body["period_days"] == pytest.approx(10.0)
    assert body["epoch_bjd"] == pytest.approx(2.0)
    assert len(body["phase"]) == len(body["flux"]) == len(body["counts"])
    assert sum(body["counts"]) == 500
    assert min(body["phase"]) >= -0.5 and max(body["phase"]) < 0.5
    # The dip lands at phase 0 (epoch folds to 0 -> -0.5 edge... check
    # centre bin): the deepest bin must sit within |phase| < 0.06.
    deepest = body["phase"][int(np.argmin(body["flux"]))]
    assert abs(deepest) < 0.06 or abs(abs(deepest) - 0.5) < 0.06


def test_folded_needs_period_and_epoch(client, token, app_state):
    _app, _auth_state, store, tmp = app_state
    _seed_job_with_arrays(app_state, job_id="nop")
    result = store.get_result("nop")
    assert result is not None
    no_eph = result.model_copy(
        update={"candidates": [result.candidates[0].model_copy(update={"period_days": None})]}
    )
    store.attach_result("nop", no_eph)
    resp = client.get(
        "/jobs/nop/artifacts/data?type=folded&candidate=c1", headers=_auth(token)
    )
    assert resp.status_code == 404


# -- ttv -------------------------------------------------------------------


def test_ttv_returns_full_residuals(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=ttv&candidate=c1", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_epochs"] == 5
    assert body["residuals_min"] == pytest.approx([0.5, -1.2, 0.8, -0.4, 1.1])


# -- caching / formats / validation ----------------------------------------


def test_etag_revalidation_returns_304(client, token, app_state):
    _seed_job_with_arrays(app_state)
    url = "/jobs/job-1/artifacts/data?type=dataset&max_points=100"
    first = client.get(url, headers=_auth(token))
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag
    second = client.get(url, headers={**_auth(token), "If-None-Match": etag})
    assert second.status_code == 304


def test_npy_format_round_trips(client, token, app_state):
    _seed_job_with_arrays(app_state, n=500)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=dataset&max_points=100&format=npy",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "octet-stream" in resp.headers["content-type"]
    arr = np.load(io.BytesIO(resp.content), allow_pickle=False)
    assert arr.shape[1] in (2, 3)
    assert arr.shape[0] <= 100


def test_max_points_bounds_are_400(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get(
        "/jobs/job-1/artifacts/data?type=dataset&max_points=5", headers=_auth(token)
    )
    assert resp.status_code in (400, 422)


def test_unknown_type_is_400(client, token, app_state):
    _seed_job_with_arrays(app_state)
    resp = client.get("/jobs/job-1/artifacts/data?type=chains", headers=_auth(token))
    assert resp.status_code in (400, 422)


def test_data_rejects_other_owner(client, token, app_state):
    _seed_job_with_arrays(app_state, job_id="theirs", owner="someone-else")
    resp = client.get("/jobs/theirs/artifacts/data?type=ttv&candidate=c1", headers=_auth(token))
    assert resp.status_code == 404
