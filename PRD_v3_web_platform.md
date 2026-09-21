# ASTRAEUS — PRD v3: From Streamlit App to Independent Web Platform

**Status:** Draft for review (planning only — no implementation started)
**Date:** 2026-09-16
**Branch:** `v.0.0.2`
**Supersedes relationship:** Makes `prd_v2.md` executable. `prd_v2.md` already names the target
stack (Next.js + FastAPI + PostgreSQL + Qdrant) but the project briefing records it three times as
*"aspirational portfolio vision — none of this is built"* (lines 73, 1860, 1979 of
`PROJECT_BRIEFING_v0.0.2.md`). This document is grounded in what actually exists today.

---

## 1. Executive summary

**The headline finding: this is a migration, not a rewrite.** The scientific engine is already a
separable, framework-agnostic Python backend. Only the presentation layer and the state-plumbing are
Streamlit.

Measured facts behind that claim:

| Property | Evidence |
|---|---|
| Codebase size | ~13.5k LOC Python (audit measured ~12.5k live, excluding `deprecated/`) |
| Framework coupling in the engine | `astraeus/core`, `analysis`, `simulation`, `data`, `workflows`, `visualization` contain **2 lazy `import streamlit` calls** — `core/ingestion.py:240` and `data/adapter.py:299`. Nothing else. |
| Files that import Streamlit | 21 total, of which **9 are in `deprecated/`** and 6 are `ui/pages/*` |
| Existing REST/WS/SSE code | **None.** Zero matches for `fastapi`, `flask`, `uvicorn`, `APIRouter`, `pydantic`, websocket, SSE. Greenfield API layer. |
| Existing frontend assets | **None.** No `package.json`, no `.tsx`. Greenfield frontend. |
| Existing async job model | **Yes** — `astraeus/core/orchestrator.py:285-603` already has `submit_multi_planet_search() -> job_id`, `get_job_status(job_id)`, `cancel_job(job_id)`, `JobState`. In-memory registry + subprocess worker + progress messages over a `queue`. |
| Existing clean service layer | **Yes, but orphaned** — `astraeus/dashboard/services/` (3 files) + `dashboard/{figures,scenario,simulation,validation}.py` are pure Python with zero Streamlit imports, but the live UI imports **none of them**. Only `deprecated/` uses them. |
| Test safety net | 63 test files, ~240 tests in the fast gate, 279 passing after the v0.0.2 audit. Real regression coverage to migrate against. |

**Recommendation in one line:** build a FastAPI process in front of the existing engine, replace the
Streamlit UI with Next.js, and replace `st.session_state` (which is currently the de-facto database
*and* the cross-page IPC bus) with explicit API contracts and a real persistence layer — while keeping
Streamlit live as a compatibility surface until the frontend reaches parity.

---

## 2. Current-state assessment

### 2.1 The one live launch path

`app.py` → `workbench_layout()` (a hand-rolled 3-panel shell in `astraeus/dashboard/ui/layout.py`,
driven by `st.session_state["current_route"]` + `st.rerun()`, *not* Streamlit native multipage) →
6 routes:

| Route | Implemented in | What it does |
|---|---|---|
| **Discover** | `app.py` (inline, ~160 lines) | Live multi-planet search jobs, KPI cards, candidate ledger, PDF manuscript export |
| **Simulation** | `ui/pages/simulator.py` (431 lines) | Multi-planet system builder (per-planet sliders, add/remove/rename), animated 3D orbit view, light curve + residuals, N-body stability sweep |
| **Detective** | `ui/pages/detective.py` (868 lines, 138 `st.` calls — the largest page) | Archive fetch (NASA Exoplanet Archive / TESS / Kepler), CSV/FITS upload, BLS single + multi-planet search, vetting verdicts, TTV plots, N-body stability matrix |
| **Lab** | `ui/pages/lab.py` (113 lines) | Interactive sensitivity/model fitting against a **mock** reference dataset |
| **History** | `ui/pages/history.py` (79 lines) | Experiment ledger (`logs/experiments.json`) view + parameter restore |
| **Settings** | `ui/pages/settings.py` (15 lines) | LLM provider/model/API-key config (writes only to session state, never back to `config.json`) |

Cross-cutting: a floating AI chat (`components.py:render_floating_chat`) and a dark "Astro" theme.

### 2.2 The five things that are genuinely good

1. **The science engine is real and tested.** Kepler solver, transit geometry, limb darkening, BLS +
   TLS cross-validation, multi-stage vetting, MCMC retrieval, TTV, symplectic N-body. 279 passing
   tests after a serious audit. This is the asset; the UI is a window onto it.
2. **An async job model already exists.** `submit_multi_planet_search` runs the search in a
   *subprocess*, streams `running`/`iteration`/`candidate`/`done`/`error` messages over a queue, and
   is polled today by `@st.fragment(run_every=2)`. That is a job queue and a progress feed wearing a
   Streamlit hat.
3. **A clean service layer exists.** `dashboard/services/{data_ingestion,mcmc_retrieval,action_deck}.py`
   are dataclass-in/dataclass-out, framework-free, and `mcmc_retrieval.run_retrieval` even takes a
   `progress_callback: Callable[[int,int], None]` — literally the hook a websocket/SSE feed needs.
4. **A production-shaped LLM gateway exists.** `core/llm_gateway.py::LLMClient` supports
   openai/anthropic/google/ollama with lazy SDK imports and env-var key fallbacks, reached via
   `analysis/explanation.py::get_scientific_explanation` → structured JSON
   (`physics_interpretation` / `parameter_breakdown` / `uncertainty_analysis`).
5. **The plotting layer is already Plotly.** `dashboard/figures.py` returns `go.Figure` objects,
   which render in Next.js via `react-plotly.js` almost verbatim; the orbit animation already returns
   a self-contained HTML/JS document that is iframe-embeddable *today*.

### 2.3 The five things that hold it back

1. **`st.session_state` is the database and the IPC bus.** Pages communicate through implicit shared
   keys — `active_dataframe`, `selected_kic`, `current_dataset_hash`, `detective_results`,
   `discovery_payload`, `multi_planets`, `active_job_id`. Detective publishes a dataframe that
   Simulator's N-body sweep consumes; Detective stamps a dataset hash that History validates on
   restore. **This implicit contract is the single hardest thing to migrate**, because it is
   undocumented, untyped, and only discoverable by reading page source.
2. **The service layer is orphaned, and logic is duplicated.** The live UI calls `astraeus.core.*`
   and `astraeus.analysis.*` directly and re-orchestrates inline. So we have two MCMC paths
   (`services/mcmc_retrieval.run_retrieval` vs `workflows/pipeline.run_retrieval`), two N-body entry
   paths, and `dashboard/simulation.py::DashboardSimulation` is dead code because `simulator.py`
   rebuilds the same physics into a `SimpleNamespace` at line 222.
3. **The AI copilot is a mock.** `render_floating_chat` returns a hardcoded string: *"I will be
   connected to the LLM Gateway shortly."* The real gateway exists but is only invoked from
   `deprecated/` code. The headline feature of `prd_v2.md` is the one thing most visibly fake.
4. **Nothing is durable or multi-user.** The job registry is a process-local dict (the UI already
   ships a "Clear Stale Job" button for jobs lost on restart). Persistence is `logs/experiments.json`
   on disk. No auth, no users, no sessions — it is a single-user desktop tool served over HTTP.
5. **Errors are swallowed at the system boundary.** The audit's deferred register records that
   `tls_environment_error` / `tls_scientific_error` are never consumed by the orchestrator — an
   infrastructure failure surfaces as a clean *"0 candidates, DONE"*. Any real product needs honest
   error states, and the API boundary is the right place to define them.

### 2.4 Two Streamlit leaks in the engine (must fix in Phase 0)

- `core/ingestion.py:240` — `RemoteDiscoveryEngine.fetch_data` is monkey-patched at import time to
  wrap its impl in `@st.cache_data(ttl=3600)`. This means **the engine cannot be imported and used
  headlessly without Streamlit installed**, and caching semantics are invisible to a FastAPI process.
- `data/adapter.py:299` — `_preserve_in_streamlit()` writes into `st.session_state["active_data"]`
  inside a bare `except: pass`. Harmless but it makes the data layer lie about its dependencies.

Both are small and mechanical to remove (move caching into the API/service layer).

---

## 3. Target architecture

```
                     ┌─────────────────────────────────────────────┐
                     │  Next.js 14 (App Router, TS, Tailwind)      │
                     │  react-plotly.js · react-three-fiber        │
                     │  Vercel                                     │
                     └───────────────┬─────────────────────────────┘
                          HTTPS JSON │  SSE/WebSocket for job progress
                                     ▼
                     ┌─────────────────────────────────────────────┐
                     │  FastAPI API layer  (NEW, thin)             │
                     │  Pydantic v2 contracts · auth · file upload │
                     │  ─────────────────────────────────────────── │
                     │  endpoints are 1:1 with the 6 features      │
                     └───────────────┬─────────────────────────────┘
                                     │  imports directly (no rewrite)
                                     ▼
                     ┌─────────────────────────────────────────────┐
                     │  astraeus/  (EXISTING engine, unchanged)    │
                     │  core · analysis · simulation · data        │
                     │  workflows · visualization                  │
                     └───────────────┬─────────────────────────────┘
                                     ▼
                     ┌─────────────────────────────────────────────┐
                     │  Job worker (arq / RQ + Redis)              │
                     │  durable replacement for JOB_REGISTRY       │
                     └───────────────┬─────────────────────────────┘
                                     ▼
                     ┌─────────────────────────────────────────────┐
                     │  SQLite (v1) → PostgreSQL (prod)            │
                     │  experiments, jobs, datasets, users         │
                     └─────────────────────────────────────────────┘
```

### 3.1 Stack decisions (and where I deviate from `prd_v2.md`)

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | **Next.js 14 + TypeScript + Tailwind** | Matches `prd_v2.md`; App Router + server components fit a content+tool hybrid (public portfolio pages + private workspace). |
| Scientific viz | **react-plotly.js** | Backend already emits `go.Figure`; near-zero porting cost. |
| 3D orbits | **react-three-fiber (Three.js)** | `prd_v2.md` names Three.js; the current HTML/JS orbit animation is a throwaway otherwise. |
| Backend | **FastAPI + Pydantic v2 + uvicorn** | Matches `prd_v2.md`; auto-generated OpenAPI gives the frontend types for free. |
| Job queue | **arq or RQ on Redis** (Phase 1 keeps in-process, Phase 2 adds Redis) | The existing registry is in-memory and single-process; a real queue buys durability + horizontal workers. Celery is overkill here. |
| Database | **SQLite via SQLAlchemy in v1 → PostgreSQL in prod** | **Deviation from `prd_v2.md`.** Today's persistence is a JSON file; going straight to Postgres adds infra before there's a single multi-user feature. SQLite is a one-file drop-in that migrates cleanly. |
| Vector DB | **Defer Qdrant.** | **Deviation from `prd_v2.md`.** `LLMClient` is prompt-only — there is no retrieval, no embeddings, no document store anywhere in the codebase. Building Qdrant now is infrastructure for a feature that does not exist. Revisit in Phase 4 when the copilot has real context. |
| AI orchestration | **Defer LangGraph/LangChain.** | The existing gateway makes direct SDK calls with structured JSON output. Adding a framework before the copilot has a defined agent loop is risk without benefit. |
| Deploy | Frontend → **Vercel**; backend + worker → **Fly.io or Railway** (needs persistent workers + volume); local dev via **Docker Compose** | Solo-operator friendly. |

---

## 4. Scope — v1 of the web platform

**In scope (feature parity with today's UI, no science changes):**

1. The 6 routes as 6 authenticated pages, plus public landing/portfolio pages.
2. Async search jobs with live progress over SSE, durable across server restarts.
3. Experiment persistence in a real DB with restore, replacing `logs/experiments.json`.
4. Data ingestion: archive fetch (Kepler/K2/TESS) and local CSV/FITS upload.
5. Interactive simulation + 3D orbit viewer + sensitivity lab.
6. PDF manuscript/report export (server-generated, downloadable).
7. **A real AI copilot** wired to the existing `LLMClient`, streaming over SSE.

**Explicitly out of scope for v1:** multi-planet MCMC on GPU, the deferred science-tradeoff items
from the audit (BLS duration-density tuning, harmonic tolerance, TTV window), Qdrant/RAG, LangGraph,
social/sharing, billing.

**Non-negotiable constraint:** the Streamlit app keeps running and stays green against the test suite
until Phase 3 exit. It is the compatibility surface and the side-by-side QA reference. Nothing in
`astraeus/core` or `astraeus/analysis` gets rewritten — only wrapped.

---

## 5. The core engineering artifact: session_state → API contracts

This is the heart of the migration. Every implicit shared key becomes an explicit, typed contract.

| Route | Reads (today) | Writes (today) | Becomes |
|---|---|---|---|
| **Discover** | `discovery_payload`, `active_job_id`, `current_dataset_hash` | `discovery_payload`, `compiled_pdf_bytes` | `POST /jobs/search` → `job_id`; `GET /jobs/{id}` (SSE stream: iteration/candidate/done/error); `GET /jobs/{id}/candidates`; `POST /reports/manuscript` → PDF |
| **Simulation** | `active_dataframe`, `selected_kic`, `multi_planets` | `multi_planets`, workspace state | `POST /systems` (multi-planet config); `GET /systems/{id}/simulate`; `GET /systems/{id}/stability` (N-body sweep); `GET /systems/{id}/figures/{orbit,lightcurve,residuals}` |
| **Detective** | `selected_kic`, data-route choice | `active_dataframe`, `selected_kic`, `current_dataset_hash`, `detective_results` | `POST /ingest/archive {target, mission}`; `POST /ingest/upload` (multipart); `POST /detection/bls`; `GET /targets/{id}/lightcurve`; `GET /targets/{id}/ttv`; vetting verdicts inline in the candidate payload |
| **Lab** | mock reference curve (cache, seed 42) | slider-driven fits | `GET /lab/reference`; `POST /lab/fit` (params → model curve + residuals) |
| **History** | `logs/experiments.json` | restored params as `restored_param_{k}` | `GET /experiments`; `GET /experiments/{id}`; `POST /experiments/{id}/restore` → returns a system config payload |
| **Settings** | `config.json` (read-only) | session state only, never persisted | `GET/PUT /users/me/settings` — **this also fixes the live bug where settings never persist** |
| **Chat** | `dashboard_scenario`, `dataset` (context awareness) | `ai_chat_messages` | `POST /copilot/chat` (SSE streaming) + `POST /copilot/explain` → wraps `action_deck.explain_retrieval` |

**Derived domain model (shared between API and DB):** `User`, `Dataset` (with the
`current_dataset_hash` content hash as an integrity column), `System` (multi-planet config),
`Job`, `Candidate` (with verbatim `vetting_status`), `Experiment`, `Report`.

---

## 6. Phased roadmap

Exit criteria are the gates; dates assume a solo operator.

### Phase 0 — Decouple and de-duplicate (Streamlit still live)  · ~1 week
The goal is a Streamlit-free engine and one canonical service layer, so Phase 1 wraps *one* thing.

- **0.1** Remove the two Streamlit leaks. `core/ingestion.py:240`: drop `@st.cache_data`, move caching
  into a service-layer wrapper with an explicit TTL. `data/adapter.py:299`: delete
  `_preserve_in_streamlit` (its callers already return the data).
- **0.2** Consolidate the service layer. Pick `dashboard/services/mcmc_retrieval.run_retrieval` as
  canonical (it has the `progress_callback` hook), make `workflows/pipeline.run_retrieval` a
  thin delegator, and delete the dead `DashboardSimulation` path.
- **0.3** Re-route the live Streamlit pages through the service layer instead of calling
  `core.*`/`analysis.*` directly. This is the refactor that makes Phase 1 a wrapper rather than a
  reimplementation, and it makes the duplicated logic visible enough to remove.
- **0.4** Define the Pydantic contracts (§5) as a `astraeus/contracts/` package — pure Python,
  importable by both the future API and the tests.
- **0.5** Surface the swallowed TLS errors: make the orchestrator consume
  `tls_environment_error`/`tls_scientific_error` and expose them as job error states.
- **Exit gate:** full suite green (279+ passing, `not network and not slow`), engine imports with
  Streamlit uninstalled (prove it in CI), zero behavior change in the live UI.

### Phase 1 — API layer + durable jobs  · ~2–3 weeks
- **1.1** FastAPI app: `ingest`, `systems`, `detection`, `jobs`, `experiments`, `reports`, `copilot`
  endpoints per §5. Auto-generated OpenAPI → typed client for the frontend.
- **1.2** Replace `JOB_REGISTRY` with a durable queue. Phase 1a: FastAPI BackgroundTasks + SQLite
  status table (parity with today, survives restarts). Phase 1b: arq/RQ + Redis when horizontal
  workers matter. Keep the existing subprocess-worker protocol — it already speaks the right messages.
- **1.3** Progress streaming over SSE (or WebSocket) — the `queue` messages map 1:1 onto SSE events.
- **1.4** Persistence: SQLAlchemy + SQLite, `logs/experiments.json` becomes a one-time import.
- **1.5** Auth: single-user email/password first (FastAPI Users), structured for multi-user later.
- **Exit gate:** every §5 endpoint works and is contract-tested; a job survives a server restart;
  Streamlit UI still fully functional.

### Phase 2 — Frontend, feature parity  · ~4–6 weeks
Page-by-page, in dependency order, each merged behind a feature flag and QA'd side-by-side with the
Streamlit version:

1. **Shell + nav + theme** (replaces `layout.py`/`styles.py` — the hand-rolled route state machine
   becomes real Next.js routing).
2. **Discover** (jobs + SSE progress + candidate ledger) — highest demo value, exercises the queue.
3. **Detective** (ingest + BLS + vetting + TTV) — the 868-line page; split into components.
4. **Simulation** (system builder + react-three-fiber orbit viewer + stability sweep).
5. **Lab**, **History**, **Settings** (small).
6. **PDF export** — server-side `generate_academic_report`, download link.
- **Exit gate:** all 6 routes at parity, dark theme matched, Plotly figures rendering via
  `react-plotly.js`, e2e tests passing.

### Phase 3 — Real AI copilot  · ~2 weeks
- Wire `render_floating_chat`'s replacement to `LLMClient`; stream over SSE.
- Wire `action_deck.explain_retrieval` into a "Explain this retrieval" action on results pages.
- Add context: active dataset + candidates + experiment history as structured prompt context
  (this is the seed of the RAG feature — build the *context assembly* first, add the *vector store*
  only when retrieval quality demands it).
- Settings page gains real persistence (fixes the never-saves bug).
- **Exit gate:** copilot returns real streamed LLM output grounded in the user's active session.

### Phase 4 — Deploy, polish, deprecate Streamlit  · ~2 weeks
- Docker Compose for local dev (api + worker + redis + db).
- Frontend → Vercel; backend + worker → Fly/Railway; CI pipeline.
- Public portfolio pages (per `prd_v2.md` §17) — this is the portfolio showcase layer.
- Deprecation: freeze `app.py` + `ui/pages/` behind a `--legacy` flag, then remove once telemetry
  confirms the web app is the live path. **Keep the `deprecated/` panels out of scope entirely —
  they are already abandoned and are the source of the orphaned-service-layer confusion.**

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The implicit `session_state` contract has hidden couplings | **High** | High | Phase 0.4 writes the contracts down *before* building anything; grep for every `st.session_state` key and enumerate it as a migration artifact. |
| `detective.py` (868 lines, 138 `st.` calls) is a rewrite in disguise | High | Medium | Port it last of the big pages, after Discover proves the patterns; decompose by panel, not wholesale. |
| Job-queue migration changes timing semantics | Medium | High | Keep the existing subprocess + queue message protocol verbatim in Phase 1a; only the *registry backing store* changes. |
| `react-plotly.js` bundle size / SSR hydration issues | Medium | Low | dynamically import plot components; they're already isolated in `dashboard/figures.py`. |
| Plotly figure JSON isn't stable across versions | Low | Medium | Pin `plotly` (already pinned at 5.24.1) on both sides; contract-test a canonical set of figures. |
| Scope creep from `prd_v2.md`'s aspirational features (Qdrant, LangGraph, Gaia) | **High** | Medium | This PRD defers them explicitly with a re-entry trigger. Review at each phase gate, not ad hoc. |
| Scientific behavior drifts during the refactor | Low | **High** | The 279-test suite is the guardrail; Phase 0.3 re-routing must stay behavior-identical, verified by the existing UI tests. |
| Losing the fast-feedback loop Streamlit gives | Medium | Medium | Keep Streamlit live through Phase 2; it is the side-by-side QA reference. |

---

## 8. What "turning the project good" means — beyond the migration

The migration is the vehicle, but four things from the audit and this review should be fixed
*regardless* of whether the web migration proceeds, because they are the difference between a demo
and a product:

1. **Kill the orphaned-service-layer duality** (Phase 0.2–0.3). Two MCMC paths and two N-body paths
   is a correctness hazard, not just clutter.
2. **Make settings actually persist.** Today's Settings page tells the user *"To persist them
   permanently, update `config.json"* — the API layer fixes this for free.
3. **Replace the mock copilot.** It is the most visible feature in the PRD and the one thing that is
   obviously fake to any reviewer.
4. **Honest error states at the boundary** (Phase 0.5). Infra failures presenting as *"0 candidates,
   DONE"* undermines trust in every result the platform produces.

---

## 9. Decisions I need from you before Phase 0

1. **Postgres from day 1, or SQLite-first?** I recommend SQLite-first (deviation from `prd_v2.md`).
   It is one file, zero infra, and migrates cleanly. Say the word if you want Postgres immediately.
2. **Queue:** in-process + SQLite first (recommended, parity with today), or Redis+arq immediately?
3. **Auth:** single-user now, or design multi-user from the start (affects the DB schema)?
4. **Copilot provider:** the gateway supports openai/anthropic/google/ollama and `config.json`
   currently defaults to `google`/`gemini-1.5-pro-latest`. Keep that default, or standardize on one?
5. **Monorepo or two repos?** I recommend a single repo with `frontend/` and `backend/` — matches the
   existing git history and keeps the contracts package shared-testable.

---

## 10. Appendix — file-by-file porting disposition

| File / dir | Disposition | Notes |
|---|---|---|
| `astraeus/core/**`, `astraeus/analysis/**`, `astraeus/simulation/**`, `astraeus/workflows/**` | **Keep as-is** | The engine. Wrapped, never rewritten. |
| `astraeus/data/**`, `astraeus/visualization/**` | **Keep** | Remove the 2 Streamlit leaks (§2.4). |
| `astraeus/dashboard/services/**` | **Keep — promote to canonical** | Becomes the service layer the API wraps. |
| `astraeus/dashboard/{figures,scenario,simulation,validation}.py` | **Keep** | `simulation.py` dead path to delete; figures → `react-plotly.js`. |
| `astraeus/dashboard/ui/**` | **Discard at Phase 4** | Streamlit shell/theme/chat. |
| `app.py`, `route.py`, `ui/pages/**` | **Discard at Phase 4** | Live until then as QA reference. |
| `deprecated/**` | **Delete** | Already abandoned; source of the orphaned-service confusion. |
| `tools/diagnostics/`, `tests/qa_*.py` | **Modernize** | Audit notes triplicate manual Playwright harnesses; replace with the new frontend e2e stack. |
| `logs/experiments.json` | **One-time import → DB** | |
| `config.json` | **→ DB settings table** | |

---

### Note on tooling (per `AGENTS.md`)

CodeGenome MCP was not available for this analysis: no native MCP tools are exposed in this context,
and the HTTP endpoint `http://127.0.0.1:7331/mcp` returned `000` (server not running). The sanctioned
fallback was used — direct repo reads. `.genome/exports/graph.json` contains only viewer assets; the
graph is also stale (last analyzed 2026-08-21) relative to current work. **Before Phase 0, run
`codegenome analyze` or `codegenome mcp-start --transport http` so the migration can be tracked
against a current graph.**
