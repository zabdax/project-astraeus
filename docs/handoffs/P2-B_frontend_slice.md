BUCKET: P2-B
STATUS: COMPLETE

PROVIDES:
- `web/` — the first browser UI over the Phase 1 API (Next.js 16 App
  Router + TypeScript strict, one route `/`): connect (API-key → bearer,
  memory-only) → data (real MAST target fetch or CSV upload parsed to
  inline arrays in-browser) → run (max_signals/snr_floor) → measured SSE
  progress with polling backstop → evidence table with epistemic badges
  (PRD §10: MEASURED/derived, never a planet probability) → provenance
  drawer (dataset_id, capability snapshot, TLS roll-up, warnings) →
  result-JSON download. Cancel kills the process tree.
- `web/lib/api.ts` — hand-written typed client mirroring
  `astraeus/api/schemas.py` + `AnalysisResult.to_dict` field-for-field.
  Slice scaffolding: P3-A replaces it with an OpenAPI-generated client.
- `web/lib/api.test.ts` — 7 vitest tests (TLS labels, SSE parsing,
  CSV parsing, no-probability rule).
- API CORS for the browser slice (`astraeus/api/main.py::_add_cors`):
  loopback dev origins by default, `ASTRAEUS_CORS_ORIGINS` override,
  no credentials (bearer header, not cookies). Additive only.
- `tests/api/test_jobs.py::test_preflight_allows_loopback_slice_origin`
  locks the preflight.

CONSUMED BY:
- P3-A (Next.js foundation, generated client, real theme)
- P3-B (Investigate route — this page is its seed)

VERIFIED (measured, this bucket):
- `npm run typecheck` (tsc strict): clean
- `npm test` (vitest): 7 passed
- `npm run build`: green, `/` prerendered static
- `tests/api` (incl. new CORS test): 19 passed fast subset
- Live HTTP smoke over real uvicorn (`/auth/token` → submit noise →
  poll → result): COMPLETED with provenance attached

FILES OF INTEREST:
- web/app/page.tsx, web/app/layout.tsx, web/app/globals.css
- web/lib/api.ts, web/lib/api.test.ts
- web/package.json (+ lockfile), web/tsconfig.json, web/next.config.ts
- web/README.md
- astraeus/api/main.py (`_add_cors` only)
- tests/api/test_jobs.py (one added test)

KNOWN CONSTRAINTS:
- Theme is deliberately thin; P3-A owns the real theme. Do not grow
  `lib/api.ts` into a second contract — extend the API schema instead.
- Tokens in memory only; BYOK persistence is P3-E.
- CSV upload parses time,flux[,flux_err] with `#`/header tolerance and
  the API's ≥10-point minimum enforced client-side before submit.
- SSE via EventSource with polling backstop: a dropped stream can never
  stick the UI on a terminal state.
- `web/.next/`, `node_modules/` ignored; `package-lock.json` committed.

NEXT REQUIRED ACTION:
- P3-A may scaffold the foundation around this page and generate the
  API client from the OpenAPI schema.
