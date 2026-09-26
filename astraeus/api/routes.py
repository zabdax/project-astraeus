"""Job routes for the ASTRAEUS API layer (P1-H).

The endpoints are deliberately thin: they validate (see ``schemas.py``),
translate a request into the engine's own records, and hand it to the
:class:`~astraeus.jobs.supervisor.JobSupervisor`.  No scientific logic
lives here, and the engine boundary stays unaware that HTTP exists
(PRD §4.1: the engine contract is invariant under the caller).

Owner scoping is enforced *by the store query*, not by filtering a full
list afterwards: ``list_jobs(owner_id=...)`` is the only query a request
can trigger, so a request can never read another owner's rows.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse

from astraeus.api.artifacts import (
    artifact_etag,
    decimate_1d,
    decimate_periodogram,
    fold_and_bin,
    stride_for,
)
from astraeus.api.auth import AuthState, CurrentUser, create_access_token, require_user
from astraeus.api.schemas import (
    ArtifactLink,
    ArtifactManifestResponse,
    ArtifactRefOut,
    CandidateArtifactEntry,
    DatasetManifest,
    DatasetSeries,
    ErrorResponse,
    FoldedSeries,
    JobListResponse,
    JobResponse,
    JobSubmission,
    PeriodogramPeak,
    PeriodogramSeries,
    ResultResponse,
    TokenRequest,
    TokenResponse,
    TtvManifest,
    TtvSeries,
)
from astraeus.contracts.dataset import ArtifactRef, ArtifactStore, Dataset, Mission, TargetRef, TimeUnit
from astraeus.jobs.store import JobRecord

__all__ = ["router", "build_router"]


def _auth_state(request: Request) -> AuthState:
    state: AuthState | None = getattr(request.app.state, "auth", None)
    if state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="auth not initialized")
    return state


def _supervisor(request: Request):
    from astraeus.jobs.supervisor import JobSupervisor

    supervisor: JobSupervisor | None = getattr(request.app.state, "supervisor", None)
    if supervisor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="job supervisor not initialized"
        )
    return supervisor


def _to_response(record: JobRecord) -> JobResponse:
    """Public projection of a job row.  Internal paths never leak."""
    result = record.result_id is not None
    return JobResponse(
        job_id=record.job_id,
        owner_id=record.owner_id,
        target_name=record.target_name,
        mission=record.mission,
        status=record.status.value,
        stage=record.stage.value,
        progress=record.progress,
        iteration=record.iteration,
        max_iterations=record.max_iterations,
        n_candidates=None,
        result_id=record.result_id,
        error=record.error,
        error_kind=record.error_kind,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def build_router() -> APIRouter:
    router = APIRouter()

    # -- authentication ---------------------------------------------------

    @router.post(
        "/auth/token",
        response_model=TokenResponse,
        responses={401: {"model": ErrorResponse}},
        summary="Exchange an API key for a bearer token",
    )
    def issue_token(body: TokenRequest, request: Request) -> TokenResponse:
        """The only unauthenticated route.  A bad key is a 401 with no hint
        about *which* key -- the response is identical for every failure so
        the endpoint cannot be used to probe configured owners."""
        state = _auth_state(request)
        owner = state.owner_for_key(body.api_key)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key"
            )
        token = create_access_token(state, owner)
        return TokenResponse(
            access_token=token,
            owner_id=owner,
            expires_in=int(state.config.ttl_hours * 3600),
        )

    # -- jobs -------------------------------------------------------------

    @router.post(
        "/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_201_CREATED,
        responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
        summary="Submit a transit search job",
    )
    async def submit_job(
        body: JobSubmission,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> JobResponse:
        supervisor = _supervisor(request)
        store = supervisor.store
        artifact_store = ArtifactStore(supervisor.artifact_root)

        # The job id is generated at the boundary; the client never names
        # one, so a submitted job id cannot collide with or impersonate
        # another owner's.
        job_id = str(uuid.uuid4())

        # One Job consumes one Dataset (PRD §5).  Either the arrays arrive
        # inline (translated to the canonical contract here) or the worker
        # fetches real data through the ingestion seam (P1-D/P1-G).
        if body.target is not None:
            record = JobRecord(
                job_id=job_id,
                target_name=body.target.name,
                mission=body.target.mission,
                owner_id=user.owner_id,
                max_iterations=body.max_signals,
            )
            submitted_id = await supervisor.submit(
                record,
                fetch_real_data=True,
                config={"snr_floor": body.snr_floor, "max_signals": body.max_signals},
            )
            return _to_response(store.require_job(submitted_id))

        inline = body.dataset
        dataset = Dataset.from_arrays(
            inline.time,
            inline.flux,
            inline.flux_err,
            target=TargetRef(name=inline.target_name, mission=Mission.UNKNOWN),
            time_unit=TimeUnit.BJD,
            source="api:inline",
            sort=True,
        )
        ref = artifact_store.save_dataset(dataset)
        record = JobRecord(
            job_id=job_id,
            target_name=inline.target_name,
            owner_id=user.owner_id,
            max_iterations=body.max_signals,
        )
        submitted_id = await supervisor.submit(
            record,
            dataset_ref=ref,
            config={"snr_floor": body.snr_floor, "max_signals": body.max_signals},
        )
        return _to_response(store.require_job(submitted_id))

    @router.get(
        "/jobs",
        response_model=JobListResponse,
        responses={401: {"model": ErrorResponse}},
        summary="List jobs for the authenticated owner",
    )
    def list_jobs(
        request: Request,
        limit: int = 50,
        user: CurrentUser = Depends(require_user_dep),
    ) -> JobListResponse:
        supervisor = _supervisor(request)
        limit = max(1, min(limit, 200))
        rows = supervisor.store.list_jobs(owner_id=user.owner_id, limit=limit)
        return JobListResponse(jobs=[_to_response(r) for r in rows], count=len(rows))

    @router.get(
        "/jobs/{job_id}",
        response_model=JobResponse,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
        summary="Get one job",
    )
    def get_job(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> JobResponse:
        record = _require_owned_job(request, job_id, user)
        return _to_response(record)

    @router.post(
        "/jobs/{job_id}/cancel",
        response_model=JobResponse,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
        summary="Cancel a running job",
    )
    async def cancel_job(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> JobResponse:
        record = _require_owned_job(request, job_id, user)
        if record.is_terminal():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"job is already {record.status.value}; only a live job can be cancelled",
            )
        supervisor = _supervisor(request)
        await supervisor.cancel(job_id)
        return _to_response(supervisor.store.require_job(job_id))

    @router.get(
        "/jobs/{job_id}/result",
        response_model=ResultResponse,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
        summary="Get the AnalysisResult and provenance for a completed job",
    )
    def get_result(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> ResultResponse:
        _require_owned_job(request, job_id, user)
        supervisor = _supervisor(request)
        result = supervisor.store.get_result(job_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job has no result yet" if not _is_terminal(request, job_id) else "job produced no result",
            )
        return ResultResponse(result=result.to_dict(), provenance=_provenance_dict(supervisor, job_id))

    @router.get(
        "/jobs/{job_id}/events",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            200: {"content": {"text/event-stream": {}}},
        },
        summary="Stream job events (SSE)",
    )
    async def stream_events(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> StreamingResponse:
        _require_owned_job(request, job_id, user)
        supervisor = _supervisor(request)

        async def generate() -> AsyncIterator[bytes]:
            # Replay the durable trail, then follow the live stream; the
            # supervisor owns the seam between them (PRD §5.1).
            async for event in supervisor.events(job_id):
                payload = json.dumps(event, default=str)
                yield f"data: {payload}\n\n".encode("utf-8")
                # Give the client a chance to disconnect cleanly.
                if await _client_disconnected(request):
                    return

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable proxy buffering
            },
        )

    # -- artifact arrays (3D-evidence program) ------------------------------

    @router.get(
        "/jobs/{job_id}/artifacts",
        response_model=ArtifactManifestResponse,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
        summary="List the array artifacts a job holds",
    )
    def list_artifacts(
        job_id: str,
        request: Request,
        user: CurrentUser = Depends(require_user_dep),
    ) -> ArtifactManifestResponse:
        """Manifest of servable arrays.  A job with no result yet returns
        its dataset (when stored) and an empty candidate list -- 200, not
        404.  URLs are templated server-side; the client must never build
        a store path."""
        record = _require_owned_job(request, job_id, user)
        supervisor = _supervisor(request)
        result = supervisor.store.get_result(job_id)

        dataset = DatasetManifest(dataset_id=record.dataset_id)
        if record.dataset_ref is not None:
            dataset = DatasetManifest(
                dataset_id=record.dataset_id,
                ref=_ref_out(record.dataset_ref),
                url=f"/jobs/{job_id}/artifacts/data?type=dataset",
            )

        candidates: list[CandidateArtifactEntry] = []
        if result is not None:
            for cand in result.candidates:
                periodogram = ArtifactLink()
                if cand.periodogram_ref is not None:
                    periodogram = ArtifactLink(
                        ref=_ref_out(cand.periodogram_ref),
                        url=(
                            f"/jobs/{job_id}/artifacts/data"
                            f"?type=periodogram&candidate={cand.candidate_id}"
                        ),
                    )
                folded = ArtifactLink(
                    url=(
                        f"/jobs/{job_id}/artifacts/data"
                        f"?type=folded&candidate={cand.candidate_id}"
                    )
                )
                ttv = TtvManifest()
                if cand.ttv is not None:
                    ttv = TtvManifest(
                        n_epochs=cand.ttv.n_epochs,
                        rms_minutes=cand.ttv.rms_minutes,
                        url=(
                            f"/jobs/{job_id}/artifacts/data"
                            f"?type=ttv&candidate={cand.candidate_id}"
                            if cand.ttv.artifact is not None
                            else None
                        ),
                    )
                candidates.append(
                    CandidateArtifactEntry(
                        candidate_id=cand.candidate_id,
                        period_days=cand.period_days,
                        periodogram=periodogram,
                        folded=folded,
                        ttv=ttv,
                    )
                )
        return ArtifactManifestResponse(job_id=job_id, dataset=dataset, candidates=candidates)

    @router.get(
        "/jobs/{job_id}/artifacts/data",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            400: {"model": ErrorResponse},
            200: {"content": {"application/json": {}, "application/octet-stream": {}}},
        },
        summary="Fetch decimated array data for charts",
    )
    def artifact_data(
        job_id: str,
        request: Request,
        type: Literal["dataset", "periodogram", "folded", "ttv"] = Query(...),
        candidate: str = Query("c1"),
        format: Literal["json", "npy"] = Query("json"),
        max_points: int = Query(2000, ge=100, le=10000),
        stride: int | None = Query(None, ge=1),
        bins: int = Query(80, ge=0, le=500),
        t_min: float | None = Query(None),
        t_max: float | None = Query(None),
        user: CurrentUser = Depends(require_user_dep),
    ):
        """Decimated series for charts.  Refs resolve from the job's own
        records -- the request carries no path, so there is nothing to
        traverse.  ``If-None-Match`` revalidates against the content ETag
        (304).  ``format=npy`` returns a real ``.npy`` payload for
        downloads, never raw bytes."""
        record = _require_owned_job(request, job_id, user)
        supervisor = _supervisor(request)
        store = ArtifactStore(supervisor.artifact_root)

        if t_min is not None and t_max is not None and not t_min < t_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="t_min must be strictly less than t_max",
            )

        if type == "dataset":
            ref = record.dataset_ref
            if ref is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="job has no dataset yet"
                )
            series, etag, npy_arr = _dataset_series(store, ref, job_id, record, max_points, stride, t_min, t_max)
        else:
            result = supervisor.store.get_result(job_id)
            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="job has no result yet"
                )
            cand = next((c for c in result.candidates if c.candidate_id == candidate), None)
            if cand is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"no candidate {candidate!r} on this job",
                )
            if type == "periodogram":
                if cand.periodogram_ref is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"candidate {candidate!r} has no periodogram",
                    )
                series, etag, npy_arr = _periodogram_series(
                    store, cand.periodogram_ref, job_id, candidate, max_points, stride
                )
            elif type == "ttv":
                if cand.ttv is None or cand.ttv.artifact is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"candidate {candidate!r} has no TTV residuals",
                    )
                series, etag, npy_arr = _ttv_series(
                    store, cand.ttv.artifact, job_id, candidate, cand.ttv
                )
            else:  # folded: computed on demand, never persisted
                if record.dataset_ref is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="job has no dataset yet"
                    )
                if cand.period_days is None or cand.epoch_bjd is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"candidate {candidate!r} has no period/epoch to fold on",
                    )
                series, etag, npy_arr = _folded_series(
                    store, record.dataset_ref, job_id, record, candidate,
                    cand.period_days, cand.epoch_bjd, bins, max_points, stride,
                )

        if request.headers.get("if-none-match") == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        if format == "npy":
            buf = io.BytesIO()
            np.save(buf, np.ascontiguousarray(npy_arr))
            return Response(
                content=buf.getvalue(),
                media_type="application/octet-stream",
                headers={
                    "ETag": etag,
                    "Content-Disposition": (
                        f'inline; filename="{job_id}-{type}-{candidate}.npy"'
                    ),
                    "X-Checksum-Sha256": series["ref_checksum"],
                },
            )
        body = dict(series["json"])
        body["etag"] = etag
        return Response(
            content=json.dumps(body),
            media_type="application/json",
            headers={"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"},
        )

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref_out(ref: ArtifactRef) -> ArtifactRefOut:
    return ArtifactRefOut(
        store=ref.store,
        path=ref.path,
        dtype=ref.dtype,
        shape=list(ref.shape),
        checksum=ref.checksum,
        n_bytes=ref.n_bytes,
    )


def _jailed(store: ArtifactStore, ref: ArtifactRef) -> Path:
    """Resolve a server-side ref, enforcing the store boundary.

    Refs are generated server-side, never from client input, so a path
    escaping the store means corruption, not a user error -- 500 with a
    reason.  A missing file is 404 (artifact lost with an ephemeral
    disk, PRD §8.3).
    """
    path = ArtifactStore.resolve(ref, store.root)
    if not path.is_relative_to(store.root.resolve()):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="artifact reference escapes the store (store is corrupt)",
        )
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="artifact file not found"
        )
    return path


def _dataset_series(store, ref, job_id, record, max_points, stride, t_min, t_max):
    _jailed(store, ref)
    try:
        ds = store.load_dataset(ref)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    t = np.asarray(ds.time, dtype=np.float64)
    f = np.asarray(ds.flux, dtype=np.float64)
    e = np.asarray(ds.flux_err, dtype=np.float64) if ds.flux_err is not None else None
    n_total = int(t.shape[0])
    if t_min is not None or t_max is not None:
        lo = t_min if t_min is not None else float(t[0])
        hi = t_max if t_max is not None else float(t[-1])
        mask = (t >= lo) & (t <= hi)
        t, f = t[mask], f[mask]
        e = e[mask] if e is not None else None
    s = stride_for(int(t.shape[0]), max_points, stride)
    ts, fs = decimate_1d(t, f, s)
    es = decimate_1d(e, e, s)[0] if e is not None else None
    etag = artifact_etag(ref.checksum, "dataset", max_points, s, t_min, t_max, "json")
    payload = DatasetSeries(
        job_id=job_id,
        dataset_id=record.dataset_id,
        time_unit=str(ds.time_unit.value) if hasattr(ds.time_unit, "value") else str(ds.time_unit),
        n_total=n_total,
        n_returned=int(ts.shape[0]),
        stride=s,
        t_min=float(ts[0]) if ts.shape[0] else None,
        t_max=float(ts[-1]) if ts.shape[0] else None,
        time=[float(v) for v in ts],
        flux=[float(v) for v in fs],
        flux_err=[float(v) for v in es] if es is not None else None,
        etag=etag,
    )
    cols = [ts, fs] if es is None else [ts, fs, es]
    return (
        {"json": payload.model_dump(mode="json"), "ref_checksum": ref.checksum},
        etag,
        np.column_stack(cols),
    )


def _periodogram_series(store, ref, job_id, candidate, max_points, stride):
    _jailed(store, ref)
    try:
        grid = np.asarray(store.load_array(ref), dtype=np.float64).reshape(-1, 2)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    n_total = int(grid.shape[0])
    merged, s = decimate_periodogram(grid, max_points)
    peak_row = merged[int(np.argmax(merged[:, 1]))]
    etag = artifact_etag(ref.checksum, "periodogram", candidate, max_points, s, "json")
    payload = PeriodogramSeries(
        job_id=job_id,
        candidate_id=candidate,
        n_total=n_total,
        n_returned=int(merged.shape[0]),
        stride=s,
        periods=[float(v) for v in merged[:, 0]],
        powers=[float(v) for v in merged[:, 1]],
        peak=PeriodogramPeak(period_days=float(peak_row[0]), power=float(peak_row[1])),
    )
    return (
        {"json": payload.model_dump(mode="json"), "ref_checksum": ref.checksum},
        etag,
        np.ascontiguousarray(merged),
    )


def _ttv_series(store, ref, job_id, candidate, summary):
    _jailed(store, ref)
    try:
        resid = np.asarray(store.load_array(ref), dtype=np.float64).ravel()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    etag = artifact_etag(ref.checksum, "ttv", candidate, "full", "json")
    payload = TtvSeries(
        job_id=job_id,
        candidate_id=candidate,
        n_epochs=int(resid.shape[0]),
        rms_minutes=summary.rms_minutes,
        residuals_min=[float(v) for v in resid],
    )
    return (
        {"json": payload.model_dump(mode="json"), "ref_checksum": ref.checksum},
        etag,
        np.ascontiguousarray(resid),
    )


def _folded_series(store, ref, job_id, record, candidate, period, epoch, bins, max_points, stride):
    _jailed(store, ref)
    try:
        ds = store.load_dataset(ref)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    t = np.asarray(ds.time, dtype=np.float64)
    f = np.asarray(ds.flux, dtype=np.float64)
    n_total = int(t.shape[0])
    if bins == 0:
        s = stride_for(n_total, max_points, stride)
        phase = (np.mod(np.mod(t - epoch, period) + period, period)) / period - 0.5
        order = np.argsort(phase, kind="stable")
        ps, fs = decimate_1d(phase[order], f[order], s)
        etag = artifact_etag(ref.checksum, "folded", candidate, period, epoch, "scatter", s, "json")
        return (
            {
                "json": {
                    "job_id": job_id,
                    "candidate_id": candidate,
                    "type": "folded",
                    "period_days": period,
                    "epoch_bjd": epoch,
                    "bins": 0,
                    "n_total": n_total,
                    "stride": s,
                    "phase": [float(v) for v in ps],
                    "flux": [float(v) for v in fs],
                    "counts": [1] * int(ps.shape[0]),
                },
                "ref_checksum": ref.checksum,
            },
            etag,
            np.column_stack([ps, fs]),
        )
    centres, means, counts = fold_and_bin(t, f, period, epoch, bins)
    etag = artifact_etag(ref.checksum, "folded", candidate, period, epoch, bins, "json")
    payload = FoldedSeries(
        job_id=job_id,
        candidate_id=candidate,
        period_days=period,
        epoch_bjd=epoch,
        bins=bins,
        n_total=n_total,
        phase=[float(v) for v in centres],
        flux=[float(v) for v in means],
        counts=[int(v) for v in counts],
    )
    return (
        {"json": payload.model_dump(mode="json"), "ref_checksum": ref.checksum},
        etag,
        np.column_stack([centres, means]),
    )


def require_user_dep(request: Request) -> CurrentUser:
    """Dependency wiring ``require_user`` to the app's ``AuthState``."""
    return require_user(_auth_state(request), _bearer(request))  # type: ignore[arg-type]


def _bearer(request: Request):
    from fastapi.security import HTTPAuthorizationCredentials

    header = request.headers.get("authorization", "")
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=parts[1])


def _require_owned_job(request: Request, job_id: str, user: CurrentUser) -> JobRecord:
    """Fetch a job, enforcing ownership.

    A job that does not exist and a job owned by someone else both return
    404 with the same message, so the endpoint cannot be used to enumerate
    other owners' job ids.
    """
    supervisor = _supervisor(request)
    record = supervisor.store.get_job(job_id)
    if record is None or record.owner_id != user.owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return record


def _is_terminal(request: Request, job_id: str) -> bool:
    record = _supervisor(request).store.get_job(job_id)
    return record is not None and record.is_terminal()


def _provenance_dict(supervisor, job_id: str) -> dict[str, Any] | None:
    provenance = supervisor.store.get_provenance(job_id)
    if provenance is None:
        return None
    return provenance.to_dict()


async def _client_disconnected(request: Request) -> bool:
    try:
        return await request.is_disconnected()
    except Exception:  # pragma: no cover - transport quirks
        return False


router = build_router()
