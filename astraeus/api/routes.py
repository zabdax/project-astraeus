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

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from astraeus.api.auth import AuthState, CurrentUser, create_access_token, require_user
from astraeus.api.schemas import (
    ErrorResponse,
    JobListResponse,
    JobResponse,
    JobSubmission,
    ResultResponse,
    TokenRequest,
    TokenResponse,
)
from astraeus.contracts.dataset import ArtifactStore, Dataset, Mission, TargetRef, TimeUnit
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

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
