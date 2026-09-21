BUCKET: P1-H
STATUS: COMPLETE

PROVIDES:
- `astraeus/api/` — the FastAPI + JWT API layer (PRD §13.1).  Authenticated
  job submission, owner-scoped listing, cancellation, results with
  provenance attached, and an SSE event stream — the HTTP boundary over the
  Phase 1 job system.  No scientific logic lives here; the engine contract
  is invariant under the caller (PRD §4.1).
- `auth.py` — own JWT (PyJWT), single-user default
  (`ASTRAEUS_SINGLE_USER=1`) with multi-user ready
  (`ASTRAEUS_API_KEYS` as `{owner: key}`).  Fail-closed: an unconfigured
  deployment rejects every protected route rather than serving anonymous
  traffic.  Keys compared in constant time; tokens carry expiry; a token
  for a revoked owner stops validating.
- `schemas.py` — the wire contract: input validation on target IDs before
  they reach MAST/S3 (PRD §13.1), mission allowlist, array-length checks,
  request-size limits, and a `model_validator` enforcing "one Job consumes
  one Dataset" (either inline arrays or a fetch target, never both).
- `routes.py` — owner scoping BY STORE QUERY (`list_jobs(owner_id=...)`), a
  job that doesn't exist and a job owned by someone else both return the
  same 404 (no enumeration), the job id is generated at the boundary.
- `main.py` — `create_app()` factory: lifespan (stale-job reclaim on
  startup, supervisor drain on shutdown), a 413 size-limit middleware,
  `astraeus-api` console script binding loopback by default.

CONSUMED BY:
- P2-A (vertical slice backend)
- P3-A (generated OpenAPI client), P3-C (Analyses route), P3-G (Copilot SSE)

NEW CONTRACTS:
- OpenAPI schema (generated) — P3-A generates its client from this.

FILES OF INTEREST:
- astraeus/api/__init__.py
- astraeus/api/auth.py
- astraeus/api/schemas.py
- astraeus/api/routes.py
- astraeus/api/main.py
- tests/api/test_auth.py
- tests/api/test_jobs.py

KNOWN CONSTRAINTS:
- Installable as an optional extra (`pip install astraeus[api]`); the
  engine boundary never imports the web stack, and Streamlit remains the
  reference UI until Phase 3 exit (PRD §16).
- `python-multipart` and `sse_starlette` are deliberately NOT dependencies:
  inline JSON datasets (no form uploads) and a plain `StreamingResponse`
  cover the requirements.
- `POST /auth/token` is the only unauthenticated route; `/health` is a
  liveness probe that leaks nothing but readiness.
- The `docs_url` default is `/docs`; disable it in hardened deployments.

NEXT REQUIRED ACTION:
- P2-A may compose `create_app()` with the job supervisor for the vertical
  slice; P3-A may generate the API client.
