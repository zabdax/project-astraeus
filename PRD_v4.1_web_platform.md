# ASTRAEUS — PRD v4.1: Repository-Reconciled Migration Specification

**Status:** Specification for review (planning only — **no implementation started, nothing modified**)
**Date:** 2026-09-16
**Supersedes:** `PRD_v4_web_platform.md` (which superseded `PRD_v3_web_platform.md`)
**Method:** Every claim below was verified against source at HEAD `3eafbd4` by six parallel read-only
subsystem audits plus an authoritative full-suite baseline run. Where v4 asserted, v4.1 shows the line.

---

## 0. How to read this document

Throughout, statements are tagged so that current reality is never confused with intent:

- **[CURRENT]** — verified to exist in the repository today, with `file:line` evidence.
- **[WORK]** — migration work required to reach v1.
- **[SCIENCE]** — a change to numerical/scientific behaviour, not just plumbing.
- **[FUTURE]** — deliberately out of v1 scope.

**Quality bar applied at every decision:**

> Does this make ASTRAEUS more scientifically trustworthy, technically maintainable, and genuinely
> useful to someone performing exoplanet transit analysis?

---

## 1. Executive summary

### 1.1 Verdict on PRD v4: **SUBSTANTIALLY REVISE** (neither adopt nor lightly amend)

v4's architecture is directionally correct — FastAPI + Next.js + SSE + SQLite, preserve the engine,
fix the scientific accuracy gaps, treat credibility as a deliverable. Those survive. But v4's
**foundation claims are materially overstated in ways that change Phase 0 and Phase 1 scope**:

| v4 claim | Repository truth | Consequence |
|---|---|---|
| "the job model already exists" | **True as code, false as a real-data capability.** [CURRENT] `submit_multi_planet_search` (`orchestrator.py:546`) is exercised in the live app **only on synthetic data** (`app.py:314-332` builds a `SyntheticTransitScenario`, no MAST fetch). Real data (`ui/pages/detective.py:340`) calls the **synchronous** `run_multi_planet_search` — no registry, no cancel, no progress, no subprocess. No test or live UI ever pushes real MAST data through the async path. | The durable job system **for real data is greenfield**, not a wrapper. This is the single largest schedule driver v4 underweights. |
| "a clean service layer exists" (`dashboard/services/`) | **False for live purposes — it is orphaned.** Neither `app.py` nor any `ui/pages/*` imports it; its only callers are `deprecated/` panels and tests. Worse, it calls the **older, less hardened** ingestion stack (`data/loader.py` → bare `lk.search_lightcurve().download_all()`, no timeout/retry/S3 fallback). | "Re-route live pages through the service layer" is **original wiring**, and wiring it to that stack would be a **regression**. |
| "the perf unlock is two coupled changes: `daemon=False` + remove `use_threads=1`" | The coupling is real, but **`multiprocessing.Process` has no `start_new_session` parameter** (verified against the installed 3.12 signature). Adopting process-group kill **mandates a `Process`→`Popen` rewrite**, which retires the `multiprocessing.Queue` that currently streams `running/iteration/candidate/done/error`. | It is an **IPC redesign**, not a flag flip. v4's "~300–500 LOC" queue estimate is roughly right but for a different reason than stated. |
| "TLS silently doesn't run when missing" | **Understated — it fails OPEN.** [CURRENT] `detection.py:107-109`: on `ImportError`, `tls_valid = True # Fail open if missing`, with `tls_fap` left at `1.0` and both error sentinels left `None`. | A fresh container **passes every candidate past the "load-bearing" TLS gate unvalidated**. Compounds with the `snr>10` override (§4.2). This is a scientific-correctness **emergency**, and Phase 0 item #1. |
| "279 passing tests" | **Stale.** Authoritative baseline at HEAD `3eafbd4` (2026-09-16): **286 passed, 1 skipped, 37 deselected, exit 0, 1573 s.** | v4 quoted the audit's *intermediate* run. The gate is green; the plan inherits a solid net. |
| "~80 s per TLS call" | **Understates the production default ~1.9×.** 80.9 s is a *synthetic*-curve control arm; the real Kepler-90 stitch with **TLS defaults** single-threaded is **149.7 s** (`scratch/j2c_tls_profiling_result.json`). | Budgets derived from 80 s are wrong. The 8-iteration projection is 19.96 min serial vs 2.50 min at the theoretical /8 bound. |
| "6–8× speedup" | **UNKNOWN — no measured support.** The only multi-threaded data point in the repo is a **5.27 s crash**. `/8` is a computed Amdahl bound; `/4` is an explicitly-labelled assumption in the JSON. v4 already flags this — v4.1 makes it a gate. | The unlock is **deferred to Phase 0.5 behind a real Linux benchmark**, not committed in Phase 0. |
| "Arrow IPC / Parquet" | **Premature.** Largest artifact in the repo today is ~3.2 MB (a scratch text dump); typical JSON reports are 1–35 KB; arrays are persisted **nowhere**. Meanwhile there are **seven distinct in-memory light-curve representations** and no canonical type. | v1 uses **JSON + a canonical typed Dataset boundary**. Arrow is introduced only when a *measured* payload justifies it. |
| "keep existing `LLMClient`, route through an OpenAI-compatible interface" | **Half right.** `LLMClient` exists and is real, but it is **four bespoke per-provider SDK branches** (`llm_gateway.py:78-87`), sync-only, no streaming — *not* OpenAI-compatible-shaped. Its SDKs (`openai`/`anthropic`/`google-generativeai`) are **not in requirements.txt**, and its live UI surface is a hardcoded mock (`components.py:94-99`) with zero live callers. | "Keep" = keep the *interface intent*; the gateway is **reworked** to an OpenAI-compatible seam. The copilot is **new product functionality** (v4 was right about that). |

### 1.2 What v4 got right (retained unchanged)

- This is a **migration, not a rewrite**. The scientific engine is genuinely separable: `import astraeus.core`
  and `import astraeus.analysis` **already succeed with Streamlit uninstalled** (empirically verified).
- The **stack** (Next.js 16 / FastAPI / native SSE from the API origin / SQLite→Postgres / own JWT +
  `ASTRAEUS_SINGLE_USER` / Docker Compose + Caddy) — research-verified, locked.
- **The accuracy-gap list (§4.2)** — every clause independently verified TRUE against source, two with
  corrections (§4.2 notes).
- **The credibility paradox** — ASCL + Zenodo + JOSS as first-class deliverables.
- **Streamlit stays live as the side-by-side QA reference** until the frontend reaches parity.
- **The license reasoning** (Apache-2.0 while sole copyright holder) — sound, and now *more* urgent: v4
  flagged `batman` as MIT; it is in fact **GPL-3.0** (per its own README/classifiers), which makes the
  substitution analysis in §13.3 a licensing decision, not just a technical one.

### 1.3 The one-paragraph summary

ASTRAEUS has a real, tested, framework-agnostic scientific engine (286 passing tests) wrapped in a
Streamlit shell whose state lives in `st.session_state` and whose newest UI surface ("Discover") is
synthetic-only. Its headline vetting gate fails open in any container lacking an undeclared optional
dependency, its async job system has never carried real data, its result contract is an untyped
~32-key dict with three period aliases and three verdict vocabularies, nothing about a run is
reproducible from its own record, and the package cannot be installed or invoked as `python -m astraeus`
because it has no `__init__.py`. v4.1 therefore re-sequences the plan: **fix the scientific
fail-closed behaviour and the packaging foundation first (Phase 0), benchmark rather than assume the
performance unlock (Phase 0.5), then build the contracts and a real-data job system (Phase 1), prove
the architecture on one real target (Phase 2), build the product frontend (Phase 3), fix the numerical
accuracy against the Streamlit baseline (Phase 4), and validate + publish (Phase 5).**

---

## 2. Current repository truth

All items verified 2026-09-16 at HEAD `3eafbd4`, branch `v.0.0.2`.

### 2.1 Shape and size

| Property | Value |
|---|---|
| Package root | `astraeus/` (top-level; `src/astraeus/` in `.agents/skills/astraeus-architecture/SKILL.md` is **stale**) |
| Live Python LOC | ~11,552 (`astraeus/`), + `app.py` (368) + `ui/pages/` |
| Layout | `core/` (16 modules), `analysis/` (14), `dashboard/` (ui + services + 4 headless modules), `data/` (3), `simulation/` (2), `visualization/` (1), `workflows/` (1), `main.py` |
| UI spans **three** surfaces | root `app.py` + root `route.py`; `ui/pages/` (5 page files); `astraeus/dashboard/ui/` (chrome: layout/styles/components/settings). `astraeus/dashboard/{figures,scenario,simulation,validation}.py` + `services/` are headless. |
| Deprecated tree | `deprecated/` excluded from pytest via `pytest.ini --ignore=deprecated` |

### 2.2 Test baseline (authoritative, run 2026-09-16)

```
py -m pytest -q -m "not network and not slow"
→ 286 passed, 1 skipped, 37 deselected, 9 warnings, exit 0, 1573.07 s (26m13s)
```

| Metric | Value |
|---|---|
| Total collected | 324 |
| Fast gate (not network and not slow) | 287 (286 pass + 1 skip) |
| `@network` | 32 |
| `@slow` | 32 (27 overlap with network) |
| Failure clusters | **None.** Zero failures. |
| Historical | baseline pre-audit 168 pass/1 fail → audit final 286/0. Gate has been stable since 2026-08-21. |

**Phase 0 implication:** the suite is green. **Phase 0 should NOT begin by fixing failures** — there are
none to fix. It begins with the fail-closed/capability work because that is a correctness prerequisite
for containerization, not because a test is red. Two warnings are meaningful:

- `tests/test_mcmc.py::test_mcmc_retrieval` — emcee's own sampler warns: *"`MCMC acceptance fraction is
  0.527, which is poorly tuned (should be between 0.2 and 0.5)`"*. Live in-suite evidence of the missing
  acceptance gate (§4.2 #1).
- `datetime.datetime.utcnow()` DeprecationWarning at `logging.py:116` — the experiment ledger uses a
  deprecated UTC call; cheap to fix in Phase 0.

### 2.3 Dependencies and packaging (the real gap)

`requirements.txt` — **13 lines, NOT fully pinned** (10 exact pins + 3 ranges):

```
lightkurve>=2.4.0        reportlab>=4.1.0,<4.2.0    boto3>=1.28.0
```

**Missing entirely:** `batman`, `wotan`, `transitleastsquares`, `corner`, and all LLM SDKs
(`openai`, `anthropic`, `google-generativeai`). **Present:** `emcee==3.1.6` (hard import), `boto3`
(anonymous S3 fallback — ~80 MB install weight for a rarely-triggered path).

**No packaging metadata exists — definitively.** Zero matches repo-wide for `pyproject.toml`,
`setup.py`, `setup.cfg`, `MANIFEST.in`, `uv.lock`, `Dockerfile`, `docker-compose`. Critically:

- **`astraeus/__init__.py` does not exist at all** — `astraeus/` is a PEP 420 implicit namespace
  package, importable only with the repo root on `sys.path`.
- **No `__version__`** anywhere in production code; "v0.0.2" appears only in a doc filename.
- **No `astraeus/__main__.py`** → `python -m astraeus` **cannot work**.
- `astraeus/main.py` is a **hardcoded single-target script** (`RealDataPipeline(...).execute_full_workflow(target_name="TrES-2b", mission="Kepler", quarter=1)`) with a `sys.path.append` hack — not a CLI. No argparse/click/typer anywhere.
- `astraeus/core/config.py` is **36 lines, LLM-only** (`required_keys = ["llm_provider","llm_model","api_keys"]`). **There is no science/pipeline config system**; `validate_config` only warns and never raises.

**CI:** one workflow (`.github/workflows/tests.yml`), three jobs, **all single Python 3.12, no matrix**.
The **weekly blocking full-suite gate already exists** (`cron: "0 3 * * 0"`, no `continue-on-error`) —
contrary to a natural assumption that only the non-blocking nightly exists. No publish/release/lint/
type-check/coverage. README claims "Python 3.10+" that CI never tests.

**82 generated artifacts are committed to git** (`outputs/` 70, `logs/` 11, `runs/` 1); `.gitignore`
covers `reports/` but **not** `outputs/`, `logs/`, or `runs/`. No PDF has ever been committed.

### 2.4 The two scientific pipelines (they are NOT one pipeline)

[CURRENT] The repository contains **two disjoint scientific paths that share only low-level primitives**
(`detrend_lightcurve`, `to_bjd`). Neither calls the other.

| | **Blind search + vetting** | **Known-period retrieval** |
|---|---|---|
| Entry | `detect_transit_candidate` (`detection.py:11`), driven by `run_multi_planet_search` / `_subprocess_search_worker` | `run_mcmc` via `workflows/pipeline.py` or `dashboard/services/mcmc_retrieval.py` |
| Stages | detrend → BLS → TLS → geometric validation → U/V vetting → cross-vetting ladder → physical properties → TTV → subtract & loop | detrend → phase-fold → optimizer → **emcee** → model flux |
| Has BLS/TLS/vetting | Yes | **No** |
| Has fitting/MCMC | **No** | Yes |
| Period source | **measured** (BLS/TLS) | **user config or hardcoded** (`pipeline.py:163` hardcodes `2.470613` for TrES-2b) |
| Wired to live UI | **Detective only** (sync); Discover (async, **synthetic only**) | **Neither** — only `main.py` CLI and a `deprecated/` panel |

**This is the single most important structural fact in the whole audit**, and it governs §6: the first
unified execution path is the **search + vetting** path. Inference is **explicitly nullable/absent** in
v1 — it has never once run against a real detected candidate.

### 2.5 Duplication inventory

[CURRENT] Every one of these is a real, separate implementation:

1. **Four MAST fetch sites**: `core/ingestion.py::RemoteDiscoveryEngine` (live, hardened) /
   `dashboard/services/data_ingestion.py` → `data/loader.py::NASAArchiveLoader` (older, bare
   `download_all()`, no retries) / `core/lightkurve_client.py` itself (the real downloader, beneath the
   facade) / `workflows/pipeline.py:142` inline `lk.search_lightcurve`.
2. **Two search loops in one file**: `run_multi_planet_search` (sync, `orchestrator.py:92-276`) vs
   `_subprocess_search_worker` (async, `:329-472`) — guardrails 1/2/3 and `subtract_planetary_signal`
   duplicated nearly verbatim, **and already drifted**: only the async one has the
   `_GUARDRAIL1_MARGINAL_TOLERANCE = 3` retry loop. **The sync one is the one real data uses.**
3. **Two MCMC orchestration wrappers**: `mcmc_retrieval.run_retrieval` ≈ `RealDataPipeline.execute_full_workflow`, nearly line-for-line.
4. **Two experiment-ledger schemas at one path**: `save_experiment_log` (live, non-atomic) vs
   `ExperimentLedger.log_candidate` (dead, but **atomic with a richer schema** — worth reviving).
5. **Three parallel UI surfaces** (§2.1) plus three `deprecated/` copies.

---

## 3. Architecture

The target architecture is unchanged in shape from v4; what changes is **what has to be built vs
wrapped**.

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ Next.js 16 (App Router, TS, Tailwind)                                │   [FUTURE build]
   │  uPlot flagship light curve · Plotly partial bundles · R3F orbits    │
   └──────────────────────────────┬──────────────────────────────────────┘
        HTTPS JSON  │  SSE for job + copilot (served from API origin, NEVER via Vercel)
                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ FastAPI (thin) — Pydantic v2 contracts, JWT auth                     │   [WORK]
   │  endpoints 1:1 with the domain model (§5). Engines NEVER run in the  │
   │  request path (async def = I/O only; numpy is GIL-bound anyway).     │
   └──────────────────────────────┬──────────────────────────────────────┘
                    │  imports directly
                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ astraeus/  EXISTING engine — wrapped, not rewritten                  │
   │  core · analysis · simulation · data · workflows · visualization     │
   │  Engine contract invariant (§4): no Next/FastAPI/SSE/JWT/Streamlit.  │
   └──────────────────────────────┬──────────────────────────────────────┘
                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ Job worker: dedicated subprocess via Popen(start_new_session=True)   │   [WORK]
   │  SQLite job table + asyncio supervisor; JSONL event stream on stdout;│
   │  cancel = killpg(SIGTERM → SIGKILL after grace). Replaces the        │
   │  multiprocessing.Process + multiprocessing.Queue mechanism.          │
   └──────────────────────────────┬──────────────────────────────────────┘
                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ SQLite (WAL) v1 → PostgreSQL (asyncpg) prod                          │   [WORK]
   │  targets · datasets · jobs · candidates · artifacts(refs) · users    │
   └─────────────────────────────────────────────────────────────────────┘
```

**What is genuinely reusable today** (verified): `dashboard/figures.py` returns `go.Figure` objects
(`make_*` family) — these render via `react-plotly.js` almost verbatim; the orbit animation already
emits a self-contained HTML/JS string. **What is not**: the service layer (orphaned), the async job
path (synthetic-only), any SSE/streaming (zero `asyncio`/`EventSource` matches repo-wide).

---

## 4. Scientific execution contract (the engine boundary)

### 4.1 The invariant

> **The engine must not depend on Next.js, FastAPI, SSE, JWT, browser state, or Streamlit.**

**Status: ALMOST SATISFIED — one hard breakage remains.** Empirically verified: with `streamlit`
forced absent (`sys.modules['streamlit'] = None`), `import astraeus.core`, `import astraeus.analysis`,
`import astraeus.core.ingestion`, and `import astraeus.data.adapter` **all succeed**. The scientific
modules (`analysis/`, `simulation/`, `visualization/`, `workflows/`, `data/` except `adapter.py`,
`core/` except `ingestion.py`) contain **zero executable Streamlit references**.

Exactly **two** leaks exist, with asymmetric severity:

| # | Site | Class | Reality |
|---|---|---|---|
| 1 | `core/ingestion.py:239-246` — `_cached_fetch_data` does `import streamlit as st` + `@st.cache_data(ttl=3600)` inside the function body, bound as `RemoteDiscoveryEngine.fetch_data` at import time | **HARD, live-reachable** | Importing is fine; **calling** `fetch_data` raises `ImportError`. `ui/pages/detective.py:469` calls it on every "Fetch Target Metadata" click. Must be fixed or the Detective page dies. |
| 2 | `data/adapter.py:299-307` — `_preserve_in_streamlit` writes `st.session_state["active_data"]` inside a bare `try/except: pass` | **OPTIONAL shim** | Harmless; degrades silently. Cleanup, not a blocker. |

So v3/v4's "two Streamlit leaks" is **correct in count** but the change set is **1 mandatory fix + 1
optional cleanup** — not two equal removals.

### 4.2 SILENT SCIENTIFIC DEGRADATION — the highest-severity finding (Phase 0, item #1)

**`batman`, `wotan`, and `transitleastsquares` are undeclared optional dependencies whose absence
changes science without raising any error, warning, result field, or job state.**

| Module | Missing backend | What actually happens | Classification |
|---|---|---|---|
| `detrending.py:3-7` (import) → `:56-83` (fallback) | `wotan` | Falls to `scipy.ndimage.median_filter` running median. **`detrending.py` does not import `logging` or `warnings` at all**; the wotan arm even has a bare `except Exception: pass` so an *installed-but-raising* wotan also silently degrades. `detrend()` returns only the flux array — **no field records which method ran**. | **FAILS OPEN** — silently substitutes a different estimator |
| `detection.py:61-62` → `:107-109` | `transitleastsquares` | `except ImportError: print("WARNING..."); tls_valid = True # Fail open if missing`. `tls_fap` stays `1.0`, `tls_sde` stays `0.0`, **both `tls_environment_error` and `tls_scientific_error` stay `None`**. The result is **internally contradictory**: "100 % false-alarm probability" alongside "validated". | **FAILS OPEN — worst of the three.** The gate is marked *passed* when it did not run. |
| `orchestrator.py:31-32` → `:64-88` | `batman` | Falls to a **trapezoid** model for signal *subtraction*: hardcoded 10 % ingress ramps, **zero limb darkening**, no curvature. `except Exception` merges `ImportError` with runtime failures. Returns flux-only → **no subtraction provenance**. (Note: this is `orchestrator.py`, **not** `transit_model.py` — v4's location was wrong.) | **FAILS OPEN** — silently substitutes a different model |

**Why this is a scientific emergency, not a packaging note.** The compounding chain is real and verified:

1. A grazing eclipsing binary with `10 < snr ≤ 20` hits `vetting.py:123`: `if (delta_chi2_u > delta_chi2_v + threshold) or (snr > 10.0): status = "Likely Planet"` — the **`snr > 10.0` inline literal** (not the `VETTING_VSHAPE_LOW_SNR_GATE = 20.0` constant).
2. "Likely Planet" makes the candidate **ineligible** for the V-shape veto (`detection.py:363-365` requires `"Ambiguous/False Positive"`), so it falls to `detection.py:388` → **`"Verified Planet Candidate"`**.
3. The only backstop is the TLS gate — **which is `tls_valid = True` in exactly the container where TLS is missing**.
4. **No container-deployed build has ever had a functioning TLS gate**, because `transitleastsquares` was never declared.

> **A fresh container actively converts the worst false-positive class into accepted planet candidates,
> with no error, warning, log line, result field, or job-state signal.**

**There is no detection mechanism at all** [CURRENT]: the only `os.environ` reads in the package are
`ASTRAEUS_LIGHTKURVE_CACHE_DIR`, `ASTRAEUS_FORCE_NETWORK`, and the three LLM API keys. `config.py`
checks nothing about science dependencies. All three fallbacks use `print()`, and in the async path
that stdout is captured by **neither** the queue protocol (`{running,iteration,candidate,done,error}`,
`orchestrator.py:334-338`) **nor** `JOB_REGISTRY` — a container job's warnings are invisible to the API caller.

**Required fix [WORK] [SCIENCE]:**
1. Make `batman`, `wotan`, `transitleastsquares` **hard dependencies** in `pyproject.toml`.
2. Replace the `ImportError`-fail-open with an explicit capability check that **fails closed** for
   production jobs: a missing scientific backend is a `FAILED` job with a clear reason, never a
   silently-degraded `COMPLETED`.
3. Introduce a **`tls_outcome ∈ {ran_pass, ran_fail, env_unavailable, not_attempted}`** enum (never a
   boolean `tls_valid`) plus a **capability snapshot** (`backends_available: {batman, wotan, tls}`)
   recorded on every `AnalysisResult`. The completeness subsystem's `algo_version` cache-busting field
   (`completeness.py:296`) is the in-repo precedent for making this visible.
4. Wire `tls_environment_error`/`tls_scientific_error` into the orchestrator's accept decision
   (audit finding A3-F5 — see §4.3) so infra failure is distinguishable from scientific rejection.
5. **Log via `logging`, not `print()`**, and capture worker stdout so a job's warnings reach the caller.

**Caveat to expect [SCIENCE]:** after this change, detection results in a properly-provisioned container
will differ from a desktop that happened to have the packages. That is the *desired* direction, but it
must be announced as a versioned scientific change.

### 4.3 The swallowed-error problem (audit A3-F5 — VERIFIED, still open)

[CURRENT] `orchestrator.py` **never reads** `tls_environment_error` or `tls_scientific_error` (the only
`tls*` token in the file is inside a historical comment). Both guardrails consume exactly three fields
(`orchestrator.py:178`, `:408-409`):

```python
if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate") or not tls_valid:
```

Consequence: **an infrastructure failure terminates as `DONE` with `candidates: []` and `error: None`** —
the job never reaches `FAILED`. `JobState.FAILED` is reachable today only from a worker exception, a
dead process with an empty queue, or a monitor crash. **Every "no planets found" result in the current
system is indistinguishable from a broken pipeline.** Job-level observability — the migration's headline
feature — has nothing to observe until this is fixed.

### 4.4 Engine contract definition [WORK]

```
ACCEPTS:  Dataset (typed: time/flux/flux_err float64 arrays, BJD-labelled, metadata) +
          AnalysisConfig (resolved thresholds, seeds, mission, target) +
          optional progress callback
RETURNS:  AnalysisResult (versioned schema, §6) + artifact references
EMITS:    stage events, warnings (structured), per-stage timing
FAILS:    closed — missing backend / insufficient data / timeout → FAILED + reason
MUST NOT: import streamlit/fastapi/starlette/jose/pydantic-HTTP; read browser state;
          require a display; depend on CWD (all artifact paths are CWD-relative today)
```

The engine must remain independently executable for **CLI, notebooks, Python SDK, backend worker, and
local researchers**. This is already nearly true; the CWD-relative artifact paths (`logging.py:8`,
`outputs/`, `outputs/reports/`) are a real blocker for a CLI and must be rooted via a `project_root` /
`XDG_DATA_HOME` resolution.

---

## 5. Domain model

Derived from the actual workflow, not from the route names. **The central product concept is the
Candidate Investigation — verified as correct**: the real workflow is Target → Data → search →
Candidates → per-candidate evidence/diagnostics → (inference, where available) → interpretation →
export → reproducibility.

| Concept | Kind | Identity / notes |
|---|---|---|
| **Target** | Persistent entity | `name` + `mission` + resolved `kic`/`tic`. Archive metadata (`pl_name`, `st_rad`, `st_teff`, `st_mass`, `sy_jmag`, `raw_row_dump`) is reference data attached to it. |
| **Dataset** | Persistent entity | The canonical typed boundary (§13). Identity = content hash **over the arrays** + `n_cadence` + `baseline_days` + mission + sector/quarter. **Today's `dataset_hash` = `sha256(metadata)` and does NOT identify the dataset** — same metadata + different cadences collide (`logging.py:10-14`). |
| **Job** | Persistent entity | State machine (§5.1). One Job consumes one Dataset and produces one `AnalysisResult`. |
| **Candidate** | Persistent entity — **the aggregate root of a Candidate Investigation** | Born from a Job; carries Evidence + Diagnostics + artifact refs. |
| **Evidence** | *Embedded* structure | Measured quantities + the gate outcome each cleared. Never a free-text verdict. |
| **Diagnostic** | *Embedded* structure | Intermediate quantities (e.g. `u_shape_chi2`, `v_shape_chi2`, `confidence_score`). Explanatory; may reference artifacts. |
| **Artifact** | *Reference* | `{store, path, dtype, shape, checksum, n_bytes}` — **arrays never inline**. |
| **Provenance** | *Embedded*, also separately downloadable | §7. |
| **Experiment** | Persistent entity | Generalizes the completeness sweep + the historical ledger. |
| **User** | Persistent entity | One row in v1 (`ASTRAEUS_SINGLE_USER=1`); `owner_id` on Job/Dataset from day one. |

**Explicitly NOT separate tables in v1:** Evidence, Diagnostic, Provenance (embedded). **Not v1 at
all:** `inference` as a peer entity (nullable section, §6), N-body/stability runs (test-only today).

### 5.1 Job state model (grounded in the real pipeline)

The stage names below are chosen from the actual `detect_transit_candidate` stages
(`docs/ARCHITECTURE.md` §4) rather than the generic list in the brief — note the renaming of
"DETECTING"→"SEARCHING" (the dominant cost) and "CROSS_VALIDATING"→"VETTING":

```
QUEUED → STARTING → FETCHING → PREPROCESSING → SEARCHING → VETTING →
       SUBTRACTING → DERIVING → FINALIZING → COMPLETED
                    ↘ FAILED / CANCELLED  (terminal, from any stage)
```

| Stage | Progress actually measurable? | Basis |
|---|---|---|
| FETCHING | Coarse (bytes/segments; `_MAX_DOWNLOAD_SEGMENTS=12`) | Kepler row-by-row loop is countable |
| PREPROCESSING | Binary only | detrend is a single call |
| **SEARCHING** | **Yes — the one that matters** | The multi-planet loop has countable iterations (`max_signals` + duplicate retries); TLS is the dominant cost (~150 s serial). Report `iteration N of M` + per-iteration phase. |
| VETTING | Binary only | fast, sub-second per candidate |
| SUBTRACTING | Binary per iteration | |
| DERIVING | Binary only | physical properties + TTV |

**Required job-system capabilities [WORK]** — none of these exist today (verified by empty grep for
SQLite/`Popen`/`asyncio`/stdout-capture):

- durable metadata (SQLite job table; today `JOB_REGISTRY` is an in-memory dict and the app ships a
  manual **"Clear Stale Job"** button because jobs are lost on restart),
- cancellation with **process-tree termination**,
- **hard timeout** (none exists today — a hung TLS call runs forever),
- **stdout/stderr capture linked to `job_id`** (today: inherited, unlinked),
- stale-job recovery on startup (reclaim `RUNNING` rows),
- warnings, stage changes, progress, artifact creation, terminal state, restart behaviour.

**Critical engineering constraint [WORK]:** `multiprocessing.Process.__init__` has **no**
`start_new_session` parameter (verified). The current mechanism — `multiprocessing.Process(daemon=True)`
+ `multiprocessing.Queue` for events — **cannot** be flag-flipped into the target architecture. Phase 1
replaces it with `subprocess.Popen(start_new_session=True)` running a dedicated worker script that emits
**newline-delimited JSON events on stdout**. This is the same "dedicated worker subprocess + process-group
kill" design v4 wanted; the evidence just makes clear it is a replacement, not an enhancement. The event
schema supersedes today's `{running,iteration,candidate,done,error}` and adds `warning`, `stage`,
`progress`, `artifact`, `error{kind}`.

**Migration trigger to Redis/arq [FUTURE]:** move when (a) horizontal workers are needed (>1 CPU box
serving concurrent jobs), (b) job volume makes SQLite write contention measurable, or (c) Redis is
already required by another subsystem. The arq task body stays "spawn the subprocess and tail stdout" —
a dispatcher change, not an engine change.

---

## 6. Result contract — versioned `AnalysisResult`

### 6.1 What's wrong today (measured)

`detect_transit_candidate` assembles a **~32-top-level-key untyped dict by sequential `.update()`**
(`detection.py:211-246` + later mutations). Concrete defects, all verified:

| Defect | Evidence |
|---|---|
| **3 period aliases** | `period`, `period_days`, `orbital_period` (+ `tls_period`, a *different* quantity in the same namespace; + `periodogram['periods']`) |
| **2 candidate flags** | `candidate_found`, `is_candidate` |
| **Duplicate epoch** | `t0`, `t0_bjd` (with `time_unit:'BJD'` documenting only one) |
| **3 "SNR" semantics** | `snr` (BLS, unbounded), `tls_sde` (different statistic), `secondary_eclipse_snr` |
| **Two "confidence" scales** | `confidence_score` (BLS peak/median, ~7+, unbounded) vs `vetting_confidence` (0–1) |
| **`v_shape_metric` has two producers** | `geometric_validation.py:22` hardwires `0.0`; `detection.py:257` overwrites with `1 - vetting_confidence`. The validator's value never reaches a consumer. |
| **`vetting_status` has three vocabularies, one key** | detection default `'candidate'`/`'rejected'` (`:220`) → shape engine (`'Likely Planet'`, `'Ambiguous/False Positive'`, `'Insufficient Data'`, `'Inconclusive'`, `'Indeterminate'`) → cross-vetting ladder (5 verdicts). Consumers couple by **string prefix**: `vetting_status.startswith("Verified Planet Candidate")` (`orchestrator.py:179`, `:409`). A fourth vocabulary is computed client-side in `detective.py:700-704`. |
| **Path-dependent schema** | `VettingEngine` returns **4 keys** on Insufficient/Inconclusive but **6 keys** on Indeterminate/success — `delta_chi2_u`/`_v` simply vanish. |
| **Serialized contract ≠ in-memory contract** | `orchestrator.py:255-271` strips `periodogram`, `ttv_data`, and all `np.ndarray` before `json.dumps`. |
| **Arrays embedded in dicts** | `periodogram.periods/.powers` — the **full BLS trial grid, ~90k entries**, embedded in *every candidate*. |
| **No uncertainties anywhere** | period, depth, duration, t0, `planet_radius_earth`, `equilibrium_temp_k`. `run_mcmc` exists but its output is never merged. |
| **No units** | depth=fraction, `secondary_eclipse_threshold_ppm`=ppm, `planet_radius_earth`=R⊕ — none labelled except an orphan `time_unit:'BJD'`. |
| **Precision destroyed / bad sentinel** | `PhysicalPropertiesEngine` `round()`s outputs and uses `0.0` as "not computable" (indistinguishable from a real zero; `physical_properties.py:34`). |
| **No seed, no timestamp, no version, no config snapshot** | — |

### 6.2 The v1 schema (design rules)

- `schema_version: "1"` from day one — **align with the existing in-repo convention** (`completeness.py:136`, `:441`; `reporting.py:730` already use `schema_version`).
- **Canonical scientific names + explicit units in field names** (`period_days`, `depth_fraction`, `duration_hours`, `epoch_bjd`, `radius_earth`).
- **Enums** for every verdict and outcome — killing the three-vocabulary free-text.
- **Nullable sections** for genuinely optional stages (inference, TTV, stability).
- **Artifact references, not inline arrays** — the 90k-entry periodogram becomes `{ref, dtype, shape, n_bytes}`.
- **`tls_outcome` enum, never a boolean** (`ran_pass | ran_fail | env_unavailable | not_attempted`).
- **`capability_snapshot`** recording which scientific backends were available — the §4.2 fix made structural.

Sketch (illustrative, not final):

```python
class AnalysisResult(BaseModel):
    schema_version: Literal["1"]
    job_id: str
    target_id: str
    dataset_id: str                      # FK to Dataset; identity = array hash
    stage_outcomes: dict[Stage, Outcome] # per-stage timing + status
    candidates: list[CandidateEvidence]
    pipeline_summary: PipelineSummary    # n_iterations, n_rejected, all_peaks_rejected...
    tls: TLSOutcome                      # enum + sde + fap + period agreement
    capability_snapshot: Backends        # batman/wotan/tls available?
    provenance: Provenance               # §7
    inference: Optional[Inference] = None  # NULLABLE — see §6.3
    warnings: list[StructuredWarning]
```

### 6.3 Inference is explicitly nullable/absent in v1

Per the evidence: MCMC is a **single** emcee site (`error_analysis.py:56`), reached only via `main.py`
or a `deprecated/` panel; **the live app never runs MCMC at all**; all three entry points take the
period from a config or a hardcoded constant rather than from a detected candidate; and inference has
**never run against a real detected candidate**. Four concrete gaps block Candidate→MCMC wiring:
no `semi_major_axis` in the candidate (computed locally at `physical_properties.py:20` but not
returned), no `eccentricity`/`inclination`/`u1`/`u2`, no retained per-candidate folded light curve, and
a period/t0 provenance mismatch.

**v1 therefore does NOT include an `inference` section in the unified execution path.** The field is
present and `null`. Wiring it is Phase 4 work (§4.3 of the roadmap), and it is a **greenfield stage**,
not a migration of existing wiring. The UI must not represent inference as a capability before it
exists.

### 6.4 Migration / deprecation strategy [WORK]

- Emit **both** legacy keys and canonical keys for one release (a `legacy_aliases` map documented in the
  schema), so existing consumers (tests, `runs/`, `tools/`) keep working.
- Add a contract test that asserts the alias map stays complete.
- Remove legacy keys after one release; keep the alias map as a documented migration table.

---

## 7. Provenance contract

**Honest inventory of what exists today:**

| Item | Status | Evidence |
|---|---|---|
| git SHA / package version | **MISSING** | no `__version__`, no `astraeus/__init__.py` |
| Dependency versions | **MISSING in production** | only in throwaway `scratch/` diagnostic JSONs |
| Dataset identity/hash | **BROKEN** | `sha256(metadata)` — does not cover arrays |
| Cadence count / baseline | **PARTIAL** | only in blind-search telemetry, never in `experiments.json` |
| mission / target / sector | **PARTIAL** | no sector/quarter recorded anywhere |
| **Effective runtime config** | **MISSING** | **`snr_floor` — the decisive threshold — is not even in `JOB_REGISTRY`** (`orchestrator.py:582-591`). No threshold, window, or TLS setting is persisted. A completed job cannot be reproduced from its own record. |
| Random seeds | **MOSTLY MISSING** | `run_mcmc` defaults `seed=None`; completeness cells record per-injection seeds (the one exception) |
| BLAS threads / cpu_count / CPU model / OS | **MISSING** | no `threadpoolctl`, no `OMP_NUM_THREADS` |
| Timestamps | PARTIAL | experiment-log UTC (via deprecated `utcnow()`), completeness ISO stamps |
| Pipeline/schema version | **PARTIAL & inconsistent** | `schema_version` exists *only* in completeness artifacts |

**The reusable pattern — and it is excellent.** `astraeus/simulation/completeness.py` already
implements, all verified on-disk: frozen validated config dataclass (`:30`), **SHA256-over-canonical-JSON
with the hash as the filename** (`:94-97`, `:285-304`), a resumable **manifest** (`:258-282`), literal
**`schema_version: 1`** (`:136`, `:441`) + **`algo_version: 2`** cache-busting (`:296`), and **atomic
`tmp`+`os.replace` writes** (`:232-238`). **Model `provenance.json` on this subsystem, not on
`experiments.json`.** Caveat: `run_completeness_sweep` itself has **no production caller** (tests only),
and the committed `manifest.json` is pre-fix (66 duplicates for an 18-cell sweep) — the *pattern* is
sound, that *artifact* is stale.

**v1 provenance must record:** git SHA; package version; lockfile hash; **exact scientific package
versions (batman/wotan/TLS/emcee)**; dataset **array** hash + `n_cadence` + `baseline_days`; mission,
target, sector/quarter; **effective resolved configuration** (thresholds, `snr_floor`, windows, TLS
settings — not the config file); seeds; BLAS thread counts + `cpu_count()` + CPU model + OS/platform;
timestamps; pipeline + schema version. Surfaced three ways: stored metadata, downloadable
machine-readable `provenance.json`, and a user-facing details drawer (§11).

**Reproducibility definition (the honest version, retained from v4):** *same seed + same pinned env
(incl. BLAS) ⇒ statistically identical posterior* — **not** bit-identical. Do not promise or test
bit-comparability across platforms.

---

## 8. Data / artifact architecture

### 8.1 Seven representations, no canonical type

[CURRENT] There is **no canonical light-curve type**; every boundary converts: (1) dict
`{time,flux,flux_err[,time_unit]}`; (2) bare `(t,f,e)` tuple; (3) `LightCurveData` frozen dataclass;
(4) `lightkurve.LightCurve`; (5) astropy `Quantity` arrays; (6) transient `DataFrame`; (7)
`st.session_state` dicts. **This — not the JSON-vs-Arrow question — is the real data-architecture
problem.**

### 8.2 Wire format: JSON first, Arrow when *measured* payloads justify it

v4's Arrow/Parquet enthusiasm is **premature**. Measured reality: the largest artifact in the repo is
~3.2 MB (a scratch text dump); science outputs are <1 MB; typical JSON reports are 1–35 KB; **light-curve
arrays are persisted nowhere in any form**. The "1.95 MiB vs 4.8–6.2 MiB" comparison is a forward
projection, not a measurement from this codebase.

**v1: JSON + a canonical typed `Dataset` boundary** (one authoritative type that both ingestion stacks
produce and both pipelines consume — this also consolidates the four fetch sites). **Arrow is introduced
when a real measured response exceeds a defined budget** (suggest ≥5 MiB), and only then. Parquet at rest
follows the same trigger. **uPlot remains the right choice for the flagship light curve regardless** —
it is a frontend performance decision, independent of the wire format.

### 8.3 Where things belong

| Belongs in | What |
|---|---|
| **Database** | entity metadata, job state, candidate records, `artifact_ref` + dtype/shape/n_cadence, provenance summary. **Never arrays.** |
| **Artifact store** | periodogram arrays, folded light curves, TTV arrays, figures (PNG), PDFs, posterior chains (when inference exists). Content-addressed, atomic writes — copy `completeness.py`'s pattern. |
| **HTTP response** | `AnalysisResult` JSON + small inline diagnostics. Arrays by reference with a signed fetch URL. |
| **Generated on demand** | PDF reports (already in-memory `BytesIO`), Plotly figure JSON, exports. |

Two cleanups [WORK]: `outputs/`, `logs/`, `runs/` must be gitignored and the 82 committed artifacts
`git rm --cached`; and on-disk telemetry in `outputs/kepler90_blind_search/` carries **`t0_bkjd` (pre-I2-fix
BKJD)** — anyone mining it gets epochs ~2454833 days off the current BJD convention. Also: completeness
cell JSON files contain bare `NaN` literals, which strict JSON parsers reject.

---

## 9. UX architecture

### 9.1 What each current route *actually* does (verified)

| Route | Reality |
|---|---|
| **Discover** | **Partly decorative.** Execution is genuine (`submit_multi_planet_search`, PDF export), but the initial state is a **hardcoded fake payload** (`BASELINE_PAYLOAD`, `app.py:31-40`) and the phase-folded figures are **analytically synthesized** from candidate parameters (`_build_phase_folded_figure`, `app.py:43-127`) — not derived from photometry. Its async job is **synthetic-only**. |
| **Detective** | **Fully wired — the real product.** Real ingestion → detection → vetting → N-body stability. 868 lines, 138 `st.` calls. Uses the *synchronous* search. |
| **Simulation** | **Real**, with caveats: builds a `SimpleNamespace` for figures; the N-body sweep falls back to hardcoded single-planet defaults without workspace state. |
| **Lab** | **A toy**: forward-model overlay against a **mock** reference dataset (`np.random.seed(42)`). No detection, no inversion. |
| **History** | Read-only ledger viewer. "Restore" writes `restored_param_*` keys **nothing consumes**. |
| **Settings** | Thin wrapper; writes LLM config to session state **no live code reads** — a dead write. |

### 9.2 Final information architecture

The brief's hypothesis (`Investigate / Analyses / Explore / Settings`) is **confirmed by the evidence**,
with one correction (Explore is a landing view, not a top-level route):

| v1 route | Replaces | Why |
|---|---|---|
| **Investigate** | Detective (promoted to primary) | The only fully-real route and the entire scientific workflow. Target → Data → Candidates → Investigation. |
| **Analyses** | History (expanded) | Job list + durable results + restore + exports. Makes the job system observable. |
| **Simulate** | Simulation + Lab (merged) | Lab's mock-dataset forward model is a *feature of* a sandbox, not a route. Merging removes a facade. |
| **Settings** | Settings (rebuilt) | Must persist for real (today it never saves) and gain the BYOK key surface. |
| *(home view)* | Discover (demoted) | Discover's synthesized figures and hardcoded payload are **eliminated as a data path**. The landing shows the user's *own* recent work from Analyses — honest by construction. |

### 9.3 Primary user journey

```
Target → validate → Data (real fetch or upload) → Preprocessing → Detection →
Candidates → Investigation (Evidence + Diagnostics) → Inference WHERE AVAILABLE →
Interpretation (AI, clearly labelled) → Export → Reproducibility
```

For each step the UI must show: what the user sees, what the backend is doing, what can fail, what
persists, what is inspectable, what is **scientifically derived** vs **merely explanatory UI**. The main
interaction is the **scientific investigation**, not the plots — figures are evidence in service of the
candidate, never the destination.

---

## 10. Candidate Investigation model (scientific honesty)

A candidate exposes **evidence**, never an unsupported "planet probability" (no such quantity is computed
anywhere in the engine, and none will be invented for the UI). Every metric is labelled by epistemic class:

| Metric | Class | What the engine actually computes | UI phrasing |
|---|---|---|---|
| SNR | **MEASURED** | BLS signal-to-noise (`bls_search.py:238`), unbounded | "BLS signal-to-noise" |
| TLS SDE | **MEASURED** (when `tls_outcome=ran_*`) | TLS spectral density of contrast | "TLS SDE" + the outcome |
| TLS FAP | **DERIVED** by TLS from its own noise calibration | not our statistic — and note our `DETECTION_CONFIDENCE_FLOOR = 7.0` is documented in-code as **"EMPIRICALLY DERIVED, not a formal false-alarm probability"** (`constants.py:143-174`, fit to synthetic sweeps, *"no real Kepler/TESS curves were characterized"*) | show floor as "empirical confidence floor", **never as a FAP** |
| BLS/TLS period agreement | **DERIVED** | `\|tls_period − best_period\|/best_period < 0.05` (inline literal, `detection.py:105`) | "period agreement" |
| depth, duration, epoch | **MEASURED** | BLS; depth is a flux fraction | with units |
| U/V shape Δχ² | **MEASURED, but caveat** | **unweighted** (`vetting.py:114-120`, no `sigma` even as a parameter) → with equal free params this is really an AIC-like comparison, not a significance | "shape comparison" — **not** "significance" until weighted (Phase 4) |
| Secondary eclipse | **MEASURED** | geometric, `secondary_eclipse_snr > 3.0`, ±0.05 phase window; classification vs a physically-derived R-J depth | as a gate outcome |
| Planet radius, eq. temp, TSM | **DERIVED** | from `st_rad`/`st_teff`/`st_mass`/`sy_jmag`; **`bond_albedo = 0.3` is hardcoded** (`physical_properties.py:15`); R≥10 R⊕ → `0.0` sentinel | labelled derived + assumptions exposed |
| TTV | **MEASURED when present** | computed on every detection (`detection.py:415`) — **then discarded** (stripped at `orchestrator.py:261-262`, never displayed, never persisted) | wire or drop from the hot path |
| Stability | **INFERRED** | N-body — **test-only today** (`validate_ttv_with_nbody` and `run_stability_analysis` have zero production callers) | absent in v1 |
| AI explanation | **AI-INTERPRETED** | prose over the same evidence | visually and structurally separated |

The UI must distinguish **MEASURED / DERIVED / INFERRED / AI-INTERPRETED**. Today's `snr > 10.0` override
and the "Verified Planet Candidate (Atmospheric Occultation Detected)" prefix-matched verdict are exactly
the kind of reassuring-but-under-supported labels this discipline replaces.

**Gates that exist today (15, verified)** vs **gates v4 recommends that do NOT exist**: odd/even
transit-depth comparison, ephemeris matching, centroid/pixel motion — all absent (grep-verified). Two
existing diagnostics are **stubs**: `v_shape_metric` (hardwired `0.0`, then overwritten) and
`flat_bottom_fraction` (defaults to `1.0` — a maximally planet-like value from a guard failure, read by
no production gate). Also note the TLS threshold `tls_sde >= 5.0` and the `0.05` tolerance are **inline
literals with no justification comment** — the odd ones out in a file otherwise meticulous about
threshold provenance.

---

## 11. Provenance UX (layered explanation)

A user starts at a headline number and can progressively dig:

```
"Period = 4.2321 d"
  → Details     (units, uncertainty where available, which stage measured it)
  → Diagnostics (BLS power, TLS SDE/FAP, period agreement, Δχ², gate outcomes)
  → Computation (effective config actually used: snr_floor, windows, TLS settings, seeds)
  → Provenance  (git SHA, versions, dataset array hash, BLAS/threads, CPU, full download)
```

**Do not expose implementation noise by default.** The top layer is the number; the deepest layer is the
full `provenance.json`. Scientific detail must be *accessible* without *overwhelming* — progressive
disclosure, not a wall of fields. Implementation detail (e.g. "this was the 2nd subtraction iteration")
is available but not foregrounded.

---

## 12. AI architecture

### 12.1 Current state (verified)

- The **live copilot is a hardcoded mock** (`components.py:94-99`: *"I will be connected to the LLM
  Gateway shortly"*). It never imports `LLMClient` and receives **no analysis context** — no period,
  depth, SNR, or verdict.
- `LLMClient` is real code but has **zero live callers**; its only UI caller is `deprecated/`. Its SDKs
  (`openai`/`anthropic`/`google-generativeai`) are **not in requirements.txt**, so only Ollama
  (localhost) could work today.
- It is **not OpenAI-compatible** — four bespoke per-provider SDK branches (`llm_gateway.py:78-87`),
  sync-only, no streaming (`"stream": False`).
- `explanation.py` is LLM-driven (not templated), takes real fitted params/uncertainties/residuals, and
  **silently returns error strings on failure** — a caller parsing the JSON cannot distinguish an
  explanation from a failure. It does **not** explain vetting outputs.
- **The Settings API-key field is a dead write** (read only by `deprecated/`).
- **LLM text never reaches the PDF** — `action_deck.py:101` passes `discussion=`; `reporting.py` never reads it.

### 12.2 The boundary (retained from v4) — and it is already structurally enforced

```
Scientific engine → AnalysisResult → Evidence serialization → LLM → Explanation
```

**Verified: the AI cannot influence scientific results, and this is by design, not luck.** Zero LLM
references in `vetting.py`, `detection.py`, `orchestrator.py`, `bls_search.py`, `fitting.py`,
`workflows/pipeline.py` (grep-verified). LLM output is prose-only and is not even persisted. The
separation is structural. v4.1 keeps it that way and makes it *auditable*: every AI response is stored
with the prompt context hash + model identity + the `AnalysisResult` id it interpreted, so a reviewer
can always retrace what the model was shown.

### 12.3 Minimum viable implementation [WORK] [FUTURE — Phase 3]

1. Rework `LLMClient` behind an **OpenAI-compatible interface** (so Ollama/any compatible endpoint is
   near-free, which is a genuine institutional differentiator for air-gapped/data-residency use).
2. **Evidence serialization first** — a deterministic, schema'd projection of `AnalysisResult` → prompt
   context. No embeddings, no vector store (none exists; Qdrant stays deferred).
3. Streaming over SSE from the API origin.
4. **BYOK by default** — key in browser session, never persisted server-side; server-side storage opt-in,
   envelope-encrypted, `GET /settings/keys` returns masked last-4 only. Never ship provider keys in any
   demo image.
5. Outputs are labelled **AI-INTERPRETED**, reference the underlying evidence, and can never set a gate
   field or invent a measurement.

**Priority order is non-negotiable: the scientific result contract (§6) exists before the copilot
consumes it.**

---

## 13. Security and resource governance

### 13.1 Required for public v1

| Control | Rationale from the evidence |
|---|---|
| Authentication (own JWT + `ASTRAEUS_SINGLE_USER=1`) | Today: single-user desktop tool over HTTP, no auth, no sessions. Model `users` + `owner_id` on Job/Dataset **from day one** even with one row. |
| **Job CPU/RAM limits + hard timeout** | **None exist today.** A hung TLS call runs forever (`orchestrator.py` has no wall budget). This is a DoS by accident, not just a UX issue. |
| **Input validation on target IDs** | Ingestion accepts free-form target strings routed to MAST/S3. |
| **Job quotas + rate limiting** | A real multi-user deployment must not let one user saturate the CPU. |
| Request size limits + artifact size caps | PDF/figure generation is unbounded today. |
| LLM key handling (BYOK) | `config.json` currently stores empty key strings; never ship provider keys. |
| **Capability check at job start** | The §4.2 fix — a job must refuse to run rather than silently degrade. |

### 13.2 Can wait until v1.1+

Multi-tenancy beyond single-user; disk quotas (artifacts are small — measured <1 MB science outputs);
fine-grained authorization; per-user MCMC budgets (inference is not in v1); Centroid/pixel analysis
(requires data we don't fetch); abuse analytics.

**Do not build infrastructure ahead of the feature that needs it** — the same discipline that defers
Qdrant/LangGraph applies here.

### 13.3 Licensing note that changes with the evidence

`batman` is **GPL-3.0**, not MIT as v4 stated. Since ASTRAEUS intends Apache-2.0, and since the
trapezoid fallback is a *scientific* regression anyway, there is a now a dual motivation to make
`transit_model.py` (a clean analytic `quad_vec` integrator with proper astropy-unit validation, **zero
batman dependency today**) the subtraction model — or to keep batman as an optional/extras dependency
with explicit GPL disclosure. This is a **decision for the user**, flagged in §17, not silently resolved.

---

## 14. Validation strategy

Built on assets that exist, and made publishable:

- **Injection-recovery as the CI gate** — `run_injection_recovery` (`synthetic.py:131`, returns
  `{signal_recovered, period_error_delta, snr_attenuation, recovered_period/snr/depth, injected_snr}`,
  criterion `|ΔP|/P ≤ 0.01`) wrapped by `run_completeness_sweep` (grid + per-cell caching + resumability).
  Seeded, sub-minute, gates recovery rate and `median |ΔP/P|`.
- **Noise-only SDE→FAP calibration** — converts `DETECTION_CONFIDENCE_FLOOR = 7.0` from an empirical
  constant into a defensible statistical threshold. Publishable in its own right.
- **Reference targets** — the QA harness already exercises **13 real targets** (8 cached, incl. TRAPPIST-1,
  Kepler-11, WASP-12 b, Kepler-20, AU Mic, HD 80606 b, Kepler-4d, Kepler-90) against a **local FITS
  cache** — deterministic, no network needed. This is the validation corpus.
- **Hypothesis/property tests** on deterministic geometry/unit code; **seeded golden-master + statistical
  tolerances** on stochastic MCMC (never property-tests on sampler output).
- **asv benchmarks** — matters once the execution profile changes (Phase 0.5).
- **Canonical targets spanning branches** — Kepler-10 b / Kepler-78 b (USP), Kepler-9 b/c/d (TTV),
  TRAPPIST-1 (resonant chain), Kepler-186 f / 452 b (completeness limit), K2-32 / Kepler-160.

**Metrics worth publishing:** detection-efficiency curve vs injected (period, depth); false-positive rate
vs Sullivan predictions; `median` + 95th-pct `|ΔP/P|`; depth accuracy + D–LDC covariance; CDPP as the
community noise yardstick; the noise-only SDE→FAP calibration.

---

## 15. Open-source / research credibility

- **Packaging foundation is a real Phase 0 blocker** for *every* credibility goal: no `pyproject.toml`,
  no `__init__.py`, no `__version__`, no `__main__.py`, no lockfile, no console script. `python -m
  astraeus` literally cannot work. Fix this first — it is cheap and it unlocks CLI/SDK/reproducibility.
- **Reuse the completeness subsystem's machinery** (config dataclass → SHA256 → manifest →
  `schema_version`/`algo_version` → atomic write) for `AnalysisResult` + artifact store + provenance.
  Do not reinvent it.
- **Credibility path:** ASCL entry → Zenodo DOI per release → JOSS submission. AAS Data Editors review
  ~90–100 % of submissions for software citation; the `\software{}` LaTeX tag is expected. **Without
  these, astronomers will not cite results produced in a browser** — this is the credibility paradox,
  and it is budgeted as a deliverable, not polish.
- **Release machinery:** `release-please` + Renovate + pre-commit + a **matrix** CI (today: single
  Python 3.12 while the README claims 3.10+). Add DCO (`Signed-off-by`), not a CLA.
- **Repo hygiene [WORK]:** gitignore + purge the 82 committed artifacts; fix `.github/` being in
  `.gitignore` while `tests.yml` is tracked; root the CWD-relative paths; replace deprecated
  `datetime.utcnow()`.

---

## 16. Roadmap (re-derived from repository complexity)

v4's phases survive in shape; what changes is **content and sequencing**. Constraint unchanged:
**Streamlit stays live and green until Phase 3 exit** — it is the side-by-side QA reference, and nothing
in `astraeus/core` or `astraeus/analysis` is rewritten, only wrapped.

| Phase | Duration | Deliverables | Exit gate |
|---|---|---|---|
| **0 — Foundation & fail-closed** | ~2 wks | §4.2: make batman/wotan/TLS hard deps + **fail closed** + `tls_outcome` enum + capability snapshot; surface swallowed TLS errors as `FAILED` jobs (A3-F5); **packaging foundation** (`pyproject.toml`, `astraeus/__init__.py` + `__version__`, `__main__.py`, CLI with argparse, `uv.lock`, rooted artifact paths); remove the 1 hard Streamlit leak (+ 1 cleanup); gitignore + artifact purge; switch `print()`→`logging` in the three fallback sites; replace `utcnow()`; add CI matrix. **No engine rewrite, no numerical change** beyond the fail-closed behaviour. | Full suite green; `python -m astraeus` works from any CWD; engine imports + runs with Streamlit uninstalled; a missing backend raises a clear error, not a silent degradation. |
| **0.5 — Benchmark before you believe** | ~3–5 days | Stand up the Linux benchmark harness; re-profile TLS with `use_threads ∈ {1, cpu_count}` on **real** curves (the 8 cached targets); measure the *actual* serial baseline (≈149.7 s on Kepler-90 defaults — **not** 80 s) and the *actual* parallel speedup; produce a written result; **only then** decide whether to land `daemon=False` + `use_threads` unlock. Update (don't delete) `test_tls_call_path_contract.py`. | A measured number in the plan. The unlock is **gated on the measurement**, and the IPC redesign (`Process`→`Popen`, Queue→JSONL) is scoped from real numbers. |
| **1 — Contracts + real-data job system** | ~3–4 wks | `AnalysisResult` v1 schema + alias map (§6); canonical typed `Dataset` boundary (consolidates 7 representations); **job system: SQLite table + asyncio supervisor + `Popen(start_new_session=True)` + JSONL stdout events + killpg cancel + hard timeout + stale recovery**; FastAPI app (endpoints 1:1 with the domain model); **wire real ingestion into the async path** (today synthetic-only); `provenance.json` modelled on the completeness pattern; own JWT + `SINGLE_USER`. | Every endpoint contract-tested; **a real-data job survives a server restart; cancel kills the process tree; a TLS infra failure produces `FAILED` + reason.** |
| **2 — Vertical slice** | ~2 wks | §18. | One real target end-to-end through the new stack, with real data and honest progress. |
| **3 — Product frontend** | ~4–6 wks | Next.js 16 shell; routes per §9.2 (**Investigate / Analyses / Simulate / Settings**); uPlot flagship + Plotly partial bundles + R3F orbits; `openapi-ts` → Zod → RHF loop; copilot behind the §12 boundary (BYOK, OpenAI-compatible, SSE). | All routes at parity; dark theme matched; e2e tests; side-by-side QA vs Streamlit. |
| **4 — Scientific accuracy** | ~3 wks | §16.1 items, validated against the Streamlit baseline. | Noise-only FAP calibration published; results documented as a versioned scientific change. |
| **5 — Validation, deploy, credibility** | ~3 wks | Injection-recovery CI gate + asv; validation runs on the reference targets; Docker Compose + Caddy; Fly.io/Hetzner demo; **ASCL + Zenodo DOI; JOSS checklist**; freeze Streamlit behind `--legacy`. | Detection-efficiency curve + FP comparison published; `docker compose up` works cold; DOI minted. |

**Real schedule drivers, ranked:** (1) the real-data job system + IPC redesign — v4's largest underestimate;
(2) the contract layer (untyped 32-key dict → versioned schema is real design work); (3) the frontend;
(4) the accuracy work (must follow parity, since it changes numbers); (5) credibility/packaging (cheap,
must not be last). The original 14–17 week envelope is **plausible but tight**; the risk is concentrated
in Phase 1, not spread evenly.

### 16.1 Scientific accuracy items (Phase 4 — all verified TRUE, two corrected)

1. **MCMC convergence gates**: `seed` defaults `None` (legacy global `np.random.randn`, `error_analysis.py:53`);
   walkers in a `1e-4` **absolute** ball around the optimizer best fit (so relative step sizes differ by
   orders of magnitude across `radius_ratio≈0.1` vs `inclination≈85°`); fixed 20 % burn-in; **zero** matches
   repo-wide for autocorr/Gelman/R-hat/ESS/ArviZ; acceptance fraction computed only if `return_acceptance`
   is passed — **no production caller does**, and emcee itself warns the fraction is out of range in the
   test suite. Fix: seeded by default; report τ; steps ≥ 50τ; 2–4 independent ensembles with rank-normalized
   R-hat; gate acceptance ∈ [0.2, 0.5]; burn-until-τ-stable.
2. **Detection floor on signals, not noise** — publish its true FAP (§14).
3. **Weighted χ² + the `snr > 10.0` override** (§4.2 chain). Add odd/even depth + ephemeris matching.
4. **Limb darkening: up to FIVE assumptions across stages** — uniform disk (`sensitivity_engine.py:53`),
   TLS internal default (`detection.py:66`, no `ld_coefficients` passed), quadratic u1/u2 (`fitting.py`),
   fixed `[0.1,0.3]` subtraction (`orchestrator.py:52`), **and zero-LD trapezoid when batman is absent**.
   One LD source of truth; Kipping q1,q2 sampling; report D–u1–u2 covariance.
5. **Fixed-geometry subtraction** (`orchestrator.py:41-46`): `inc=90`, `ecc=0`, `a ≈ P/(π·duration)` with a
   `max(1.0, …)` clamp and the ×1.5-padded duration as input.
6. **Detrending window** — *corrected*: the live window is **0.5–1.5 d** (not 2.0), derived from a Lomb-Scargle
   rotation peak of the **raw, transit-contaminated** flux, and the stellar-radius adaptive branch
   (0.5–2.0 d) is **dead code on the production path** because `detection.py:27` calls `detrend()` without
   `st_rad`. Scaling from stellar density/duration priors is greenfield, not a parameter change. Note the
   constant (`MAX_...=1.5`) and the inline literal (`2.0`) disagree.

---

## 17. Risk register (deltas on v4)

| Risk | Status | Mitigation |
|---|---|---|
| **The job system is greenfield for real data** | **NEW — v4's biggest blind spot** | Scope Phase 1 from the evidence: `Popen` + JSONL + SQLite, and wire real ingestion into the async path as an explicit deliverable with its own test ("real MAST data through `submit_multi_planet_search`"). |
| **`start_new_session` is impossible on `multiprocessing.Process`** | **NEW** | Treat the unlock as an IPC redesign; retire the Queue deliberately; keep the event vocabulary (`running/iteration/candidate/done/error`) as the JSONL schema so consumers are stable. |
| **TLS fails open in containers** | Sharpened from v4 — it is worse than "doesn't run" | §4.2 fail-closed + capability snapshot. **A correctness prerequisite for containerization**, sequenced first. |
| **The perf unlock changes scientific behaviour** | Retained | Multi-threaded TLS is a numerical-behaviour change; benchmark on Linux (Phase 0.5) before committing; treat the speedup as UNKNOWN until measured. |
| **Sync/async search loops have already drifted** | **NEW** | Any guardrail fix must touch both `run_multi_planet_search` and `_subprocess_search_worker`, or divergence accelerates. |
| **Provenance is not an enhancement** | **NEW** | `snr_floor` isn't even in `JOB_REGISTRY` today; `dataset_hash` doesn't identify the dataset. Phase 1 fills a hole that currently makes no run reconstructible. |
| **Arrow/Parquet premature** | **NEW** | JSON + canonical `Dataset` type first; introduce binary formats on a measured payload threshold, not a projection. |
| **`batman` is GPL-3.0** | **NEW — corrects v4** | User decision: optional extras + disclosure, or migrate subtraction to the in-repo analytic `transit_model.py`. |
| v4 retained risks | unchanged | plotly bundle discipline; credibility paradox; session_state hidden couplings; `detective.py` is a rewrite in disguise (port last, decompose by panel); MCMC numbers change when seeded — announce as a versioned scientific change. |

---

## 18. Vertical slice (what proves the architecture)

```
Enter target ID (a cached QA target, e.g. Kepler-90)
  → validate target
  → fetch REAL data (local FITS cache — deterministic, no network needed)
  → run the REAL pipeline in a dedicated worker subprocess
  → SSE stage updates (measured iteration progress, not fake bars)
  → real light curve (uPlot)
  → ONE real candidate
  → evidence panel (epistemic labels per §10)
  → provenance drawer (§11)
  → download result (AnalysisResult JSON + provenance.json)
```

**Must use REAL astronomical data.** No synthetic demo curves, no hardcoded candidate parameters, no
analytical mock figures, no fake progress — unless explicitly marked as test infrastructure.

**Why this is already nearly reachable (good news):** real ingestion works (`RemoteDiscoveryEngine →
download_pipeline` returns real stitched float64 arrays, BJD-labelled) and is proven against 13 real
targets with a local cache; the detection pipeline runs end-to-end on real data via the Detective page.

**What must be built first (the honest unknowns):**
1. **Real data has never crossed the async subprocess boundary** — ingestion must be wired *into* the
   worker (today `submit_multi_planet_search` receives an already-built dict and the only live caller
   builds a synthetic one).
2. **Worker stdout capture** — today warnings are `print()` to inherited stdout, unlinked to `job_id`.
3. **The capability snapshot must exist** or the slice cannot honestly report whether TLS ran.
4. **`time_unit` is dropped at the seam** (`_fetch_data_impl` discards it; `download_combined_fusion`
   never emits it) — the canonical `Dataset` type must carry it.
5. **The dataset hash must cover arrays**, or the slice's provenance drawer cannot prove which data it ran on.

---

## 19. Explicit non-goals (v1)

- **No inference in the first unified execution path** — `inference` is present and `null`. MCMC wiring
  is Phase 4 and is greenfield (§6.3). The UI must not represent it as a capability.
- **No N-body/stability in the production path** — zero production callers today; stays out until it earns one.
- **No TTV persistence** — it is computed on every run and discarded; wire it to a consumer or drop it
  from the hot path. Do not persist "because the schema has a field."
- **No Arrow/Parquet** until a measured payload justifies it.
- **No Qdrant / LangGraph / RAG** — no retrieval, embeddings, or document store exists anywhere.
- **No "Discover"-style synthesized figures or hardcoded baseline payloads** — eliminated as data paths.
- **No planet-probability score** — not computed, not invented.
- **No K2** — the live router returns `(None, "Invalid mission_type")` despite K2 appearing in
  `time_units.py` and `loader.py`. Either implement it or remove it from the docs; do not advertise it.
- **No multi-user tenancy, billing, or social features.**
- **No bit-exact cross-platform reproducibility** — statistically identical, not bitwise (§7).
- `deprecated/` stays out of scope entirely — already abandoned, and the source of the orphaned-service-layer confusion.

---

## 20. Decision register

### Locked (do not reopen)

| Decision | Evidence | Reversible? | Phase |
|---|---|---|---|
| **FastAPI** (native SSE, OpenAPI→types, Pydantic v2) | zero existing API code; engine is clean | yes, boundary is thin | 1 |
| **Native SSE from the API origin, never via Vercel** (300 s / 4.5 MB caps) | verified constraints | yes | 1 |
| **SQLite (WAL) → Postgres**; `render_as_batch=True` from day one | no DB exists today; JSON ledger is the only "database" | yes (that's the point) | 1 |
| **Job = SQLite table + asyncio supervisor + `Popen(start_new_session=True)` + JSONL events** | `multiprocessing.Process` cannot take `start_new_session`; Queue must be retired | yes, dispatcher-only | 1 |
| **Next.js 16 (App Router)**; uPlot flagship + Plotly partial bundles + R3F | research-verified; `go.Figure` already emitted | moderate | 3 |
| **JSON wire format + canonical typed `Dataset` boundary** | measured payloads are 1–35 KB; 7 representations today | yes — deliberately deferred, not declined | 1 |
| **emcee kept, gates added (no PyMC rewrite)** | single sampler; rewrite mid-migration risks accuracy | — | 4 |
| **AnalysisResult `schema_version: "1"` + artifact refs, not arrays** | in-repo precedent (`completeness.py`) | versioned, so yes | 1 |
| **AI: evidence serialization → LLM → explanation; AI never writes a gate field** | already structurally enforced (zero LLM refs in the engine) | no — this is a principle, not a choice | 3 |
| **Streamlit live until Phase 3 exit** | side-by-side QA reference; 286-test guardrail | yes | 0–3 |
| **ASCL + Zenodo + JOSS as deliverables** | credibility paradox | no | 5 |
| **Migration, not rewrite — engine wrapped, never rewritten** | empirically separable (§4.1) | no | all |

### Intentionally deferred (with a re-entry trigger)

| Deferred | Trigger |
|---|---|
| Redis/arq | horizontal workers needed, or SQLite write contention measurable |
| Arrow IPC / Parquet at rest | a **measured** response ≥ ~5 MiB |
| The TLS performance unlock | a **measured** Linux benchmark (Phase 0.5) — speedup is UNKNOWN |
| Inference in the unified path | Phase 4; requires Candidate→MCMC gaps closed (§6.3) |
| Qdrant / LangGraph | copilot retrieval quality demands it (no retrieval exists) |
| Postgres in prod | scale actually requires it |
| dynesty | Bayesian model comparison (planet vs EB vs grazing) is needed for vetting |
| K2 support | a user asks for it, or it is removed from the docs |
| `batman` (GPL) vs in-repo analytic model | **user decision** — §13.3 |

### Awaiting user decision (5, carried from v4, now evidence-updated)

1. **Apache-2.0 now?** Recommended — patent grant matters; free only while sole copyright holder. One commit + NOTICE.
2. **Greenlight the perf unlock — and its IPC redesign — in Phase 0.5?** v4.1 defers it behind a benchmark (was Phase 0).
3. **Accuracy fixes as dedicated Phase 4 vs interleaved into Phase 0?** Dedicated (validate against the Streamlit baseline).
4. **JOSS as a Phase 5 deliverable?** Needs public history + feature completeness; constrains license + testing.
5. **Copilot default provider.** v4.1 adds evidence: the gateway is 4 bespoke branches, not OpenAI-compatible, with no SDKs installed. Recommend standardizing on an OpenAI-compatible interface with Ollama as the zero-cost air-gapped default.

---

## 21. Definitions of done

**Phase 0:** `python -m astraeus --help` works from any CWD; `pip install -e .` succeeds; the suite is
green (286+); the engine imports **and runs** with Streamlit uninstalled; a missing scientific backend
produces a clear error, never a silent `COMPLETED`.

**Phase 0.5:** a written benchmark documents the measured serial baseline and measured parallel speedup
on real curves; the unlock decision is made from numbers.

**Phase 1:** every endpoint contract-tested; **a real-data job survives a server restart; cancel kills
the whole process tree within the grace period; a TLS infrastructure failure yields `FAILED` + reason,
not `DONE / 0 candidates`; `provenance.json` contains enough to re-run the analysis from its own record.**

**Phase 2:** one real target, real data, one real candidate, honest progress, downloadable result — with
the capability snapshot visible enough to state truthfully whether TLS ran.

**Phase 3:** all four routes at parity; e2e tests green; copilot returns real streamed output grounded in
the active result, labelled AI-INTERPRETED.

**Phase 4:** noise-only FAP calibration published; every accuracy change documented as a versioned
scientific change with the old path available behind a flag for one release.

**Phase 5:** detection-efficiency curve + false-positive comparison published; `docker compose up` works
cold on a clean machine; Zenodo DOI minted; ASCL entry live; JOSS checklist started.

---

## Appendix — corrections to the documentary record

Small, actionable errors found while auditing (each would mislead a future reader):

1. **`PRD_v4:112` and `detection.py:88` cite `logs/j2c_tls_profiling_result.json`; the file is at
   `scratch/j2c_tls_profiling_result.json`.** The "re-profile before quoting" instruction is not actionable at the cited path.
2. **v4's "279 passing"** is the audit's intermediate run; the authoritative figure is **286 passed / 1 skipped / 37 deselected**.
3. **v4 locates the batman fallback in `transit_model.py`**; it is in `core/orchestrator.py:32` (subtraction only). `transit_model.py` has no batman.
4. **v4 says `batman` is MIT**; it is **GPL-3.0**.
5. **v4's "~80 s"** is the synthetic-curve control arm; the real Kepler-90 stitch with TLS defaults is **149.7 s**.
6. **`.agents/skills/astraeus-architecture/SKILL.md` documents `src/astraeus/`**; the package root is `astraeus/`.
7. **README claims "Python 3.10+"**; CI tests only 3.12. **`README`/`PRD` omit batman/wotan/TLS/corner** from the dependency table while listing `boto3`.
8. **"no `schema_version` in any output"** (a natural assumption) is **false** — `schema_version: 1` exists in the completeness subsystem and `reporting.py:730`.
9. **`PROJECT_BRIEFING_v0.0.2.md` §29/§31 correctly documents the TLS fail-open** (`tls_valid = True`) — the most accurate pre-existing statement of the problem, and more accurate than v4's.

*Tooling note (per `AGENTS.md`):* CodeGenome MCP was unavailable again (no native tools; HTTP probe of
`http://127.0.0.1:7331/mcp` → `000`). Direct repo reads were used throughout, including by six parallel
audit agents. **Before Phase 0, run `codegenome analyze` or `codegenome mcp-start --transport http`** so
the migration can be tracked against a current graph; the `.genome/` graph is stale and its
`.genome/exports/` contains no markdown worth parsing.
