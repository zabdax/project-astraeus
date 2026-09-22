# ASTRAEUS Web — P2-B vertical slice

Minimal honest UI over the ASTRAEUS transit-search API: connect → data
(target fetch or CSV upload) → run → measured SSE progress → evidence with
epistemic labels → provenance → download. One route (`/`), no invented
planet probability, no AI text, no inference section.

## Run it (two terminals)

```bash
# 1. API (single-user loopback)
set ASTRAEUS_API_KEY=dev-local-key
py -m astraeus-api            # http://127.0.0.1:8000

# 2. Web
cd web
npm install
npm run dev                   # http://localhost:3000
```

Paste the same `dev-local-key` into the page's Connect box. Override the
API origin with `NEXT_PUBLIC_ASTRAEUS_API_URL`.

## Checks

```bash
npm run typecheck   # tsc --noEmit, strict
npm test            # vitest: client contract tests
npm run build       # production build
```

## Regenerating the API client (P3-A)

Wire shapes come from the API's OpenAPI schema — never hand-edit them:

```bash
# 1. Export the schema from the Python API (from the repo root):
py -c "import json; from astraeus.api.main import create_app; \
  from astraeus.api.auth import AuthState, DEFAULT_OWNER; \
  json.dump(create_app(auth=AuthState.for_testing({DEFAULT_OWNER:'k'})).openapi(), \
  open('web/openapi.json','w'), indent=2)"
# 2. Regenerate types:
npm run gen:api
```

`openapi.json` is committed as the pinned snapshot the client was
generated from. Domain shapes (`AnalysisResult`, candidates) mirror
`astraeus/contracts/` and are pinned by `lib/api.test.ts`.

## Scope notes (read before extending)

- The hand-written client (`lib/api.ts`) is slice scaffolding. **P3-A
  replaces it with an OpenAPI-generated client** — do not grow it into a
  second contract; extend the API schema instead.
- The theme here is intentionally thin. **P3-A owns the real theme.**
- CORS defaults to loopback dev origins only
  (`ASTRAEUS_CORS_ORIGINS` overrides). The API still binds loopback by
  default, so widening CORS without widening the bind exposes nothing.
- Auth tokens live in memory only (no localStorage). BYOK persistence is
  P3-E work.
