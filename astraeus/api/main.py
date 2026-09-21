"""Application factory for the ASTRAEUS API layer (P1-H).

``create_app`` is the only public entry point.  It composes:

* the JWT auth state (``auth.AuthState``), resolved from the environment
  once at startup rather than per request;
* one :class:`~astraeus.jobs.supervisor.JobSupervisor` for the process,
  with ``reclaim_stale`` run at startup so a restart re-parents any jobs
  the previous process left ``RUNNING`` (PRD §5.1: stale-job recovery);
* the router from ``routes.py`` and the resource-governance middleware
  (request size caps, PRD §13.1).

The factory is importable without a network or a running server, which is
how ``tests/api/`` exercises the full layer through FastAPI's test client.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from astraeus.api.auth import AuthState
from astraeus.api.routes import build_router

__all__ = ["create_app", "MAX_REQUEST_BYTES"]

#: PRD §13.1: request size limits.  A light curve is at most a few hundred
#: thousand points; anything larger is refused rather than buffered.  The
#: default is generous (32 MB) and overridable for deployments that push
#: large inline arrays.
MAX_REQUEST_BYTES = int(os.environ.get("ASTRAEUS_MAX_REQUEST_BYTES", 32 * 1024 * 1024))


def create_app(
    *,
    auth: AuthState | None = None,
    supervisor: Any = None,
    db_path: Path | str | None = None,
    artifact_root: Path | str | None = None,
    title: str = "ASTRAEUS API",
    docs_url: str = "/docs",
) -> FastAPI:
    """Build the API application.

    Callers may inject ``auth`` and ``supervisor`` (tests do); without them
    the app resolves both from the environment and the default data root.
    """
    from astraeus.core.paths import artifact_path
    from astraeus.jobs.store import JobStore
    from astraeus.jobs.supervisor import JobSupervisor

    if auth is None:
        auth = AuthState()
    if supervisor is None:
        store = JobStore(db_path) if db_path else JobStore()
        supervisor = JobSupervisor(store, artifact_root=artifact_root or artifact_path("artifacts"))

    app = FastAPI(
        title=title,
        description=(
            "Transit search API for ASTRAEUS. Every result carries provenance "
            "(PRD v4.1 §5/§7). Authenticated routes require a bearer token "
            "from POST /auth/token."
        ),
        version=_version(),
        docs_url=docs_url,
        lifespan=_make_lifespan(supervisor),
    )
    app.state.auth = auth
    app.state.supervisor = supervisor
    app.state.store = supervisor.store

    # Resource governance: cap request bodies before they are buffered
    # (PRD §13.1 request-size limits).
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > MAX_REQUEST_BYTES:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "request body too large", "error_kind": "payload_too_large"},
                        )
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "invalid content-length header", "error_kind": "bad_header"},
                    )
        return await call_next(request)

    app.include_router(build_router())

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, Any]:
        # Unauthenticated by design: a load balancer needs a liveness probe
        # that does not require a token.  Leaks nothing but readiness.
        return {
            "status": "ok",
            "version": _version(),
            "auth_enabled": auth.config.enabled,
            "single_user": auth.config.single_user,
        }

    return app


def _make_lifespan(supervisor: Any):
    """ASGI lifespan: reclaim stale jobs at startup, drain at shutdown.

    Replaces the deprecated ``@app.on_event`` handlers.  A job left
    ``RUNNING`` by a previous process is not running anymore; re-parent it
    as FAILED with a reason rather than leaving it stuck forever
    (PRD §5.1 stale-job recovery).
    """

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            supervisor.store.reclaim_stale()
        except Exception:  # pragma: no cover - startup must not block the API
            pass
        try:
            yield
        finally:
            try:
                await supervisor.shutdown()
            except Exception:  # pragma: no cover - best-effort drain
                pass

    return lifespan


def _version() -> str:
    try:
        from astraeus import __version__

        return __version__
    except Exception:  # pragma: no cover - version is best-effort metadata
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """``python -m astraeus.api.main`` -- serve the API locally.

    The server binds loopback by default.  Binding to ``0.0.0.0`` is an
    explicit opt-in because PRD §13.1's authentication requirement is not
    a substitute for not exposing the port in the first place.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="astraeus-api",
        description="Serve the ASTRAEUS FastAPI + JWT API layer.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="reload on source changes (dev only)")
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run("astraeus.api.main:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry
    raise SystemExit(main())
