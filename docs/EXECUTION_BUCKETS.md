# ASTRAEUS — Execution Buckets

**The execution map for the remaining migration.**

Created at the close of Phase 0 (2026-09-17). **Phase 0 checkpoint: branch
`v.0.0.3`, commit `ac82a56`** (full SHA
`ac82a564acff6347282a14517b200f23d47f4b57`, 2026-09-17 14:24:35 +0600,
`feat(core): complete Phase 0 foundation and fail-closed hardening`). That
commit is the tip of `v.0.0.3` and is the state every bucket below branches
from. Governing specification: `PRD_v4.1_web_platform.md`.

This document is the **execution map**: it decomposes the remaining
ASTRAEUS migration (PRD v4.1 §16, Phases 0.5→5) into independent,
fresh-session-runnable buckets so work can be parallelised or sequenced
without architectural confusion.

**It is a plan, not an implementation.** No bucket below has been
implemented. Each bucket's implementation prompt must be generated
separately (see §11) and run in its own session.

---

## 1. Dependency graph

```
Phase 0 [COMPLETE @ v.0.0.3 / ac82a56]  foundation, fail-closed science, packaging
   │
   ├── P05-A  TLS multiprocessing benchmark        [COMPLETE -- measured]
   │     └── measured 1.06x-2.08x (not 6-8x); unlock deferred to P4-G
   │
   ▼
Phase 1  CONTRACTS (sequential — they import each other)   [COMPLETE]
   P1-A  Canonical Dataset contract        ──┐ [COMPLETE]
   P1-B  AnalysisResult v1 schema           ──┤  (P1-A → P1-B → P1-C) [COMPLETE]
   P1-C  Provenance contract                ──┘ [COMPLETE]
   │
   ├── P1-D  Ingestion consolidation (4 sites → seam)   ║ parallel with contracts
   │        [COMPLETE] — time_unit forwarded; adopters at loader + dashboard
   │
   ├── P1-E  Job persistence (SQLite WAL)     ── depends on nothing
   │        [COMPLETE] — SQLite store replaces JOB_REGISTRY; owner_id indexed
   ├── P1-F  Worker / IPC (Popen + JSONL)     ── depends on P05-A's decision
   │        [COMPLETE] — worker + asyncio supervisor; cancel/timeout/restart
   ├── P1-G  Real-data async integration      ── depends on P1-D + P1-F
   │        [COMPLETE] — ingestion_bridge.py; real data crosses the boundary
   ├── P1-H  FastAPI + JWT API layer          ── depends on P1-B + P1-C + P1-E
   │        [COMPLETE] — astraeus/api/; optional `api` extra; 34 tests
   ├── P1-I  Search-loop unification          ── depends on P1-F
   │        [COMPLETE] — async worker delegates to the single sync loop
   │
   ▼
Phase 2  VERTICAL SLICE
   P2-A  Backend slice (one real target e2e)   ── depends on P1-G + P1-H
         [COMPLETE] — Kepler-90 cached curve API→worker→COMPLETED + honest TLS
   P2-B  Frontend slice (minimal honest UI)    ── depends on P2-A
         [COMPLETE] — Next.js Investigate page over the API slice + CORS
   │
   ▼
Phase 3  PRODUCT FRONTEND                          (after P3-A, routes are parallel)
   [COMPLETE — all routes, copilot, QA, freeze; see handoffs P3-A..P3-I]
   P3-A  Frontend foundation (Next.js, client gen, theme) [COMPLETE]
   P3-A  Frontend foundation (Next.js, client gen, theme)
   ├── P3-B  Investigate route
   ├── P3-C  Analyses route
   ├── P3-D  Simulate route
   ├── P3-E  Settings route + BYOK
   ├── P3-F  Visualization integration (uPlot/Plotly/R3F)
   ├── P3-G  Copilot (SSE, evidence-grounded)
   └── P3-H  E2E QA + side-by-side vs Streamlit
   P3-I  Streamlit freeze behind --legacy        ── after P3-H
   │
   ▼
Phase 4  SCIENTIFIC ACCURACY  (versioned, flag-guarded, validated vs baseline)
   ├── P4-A  MCMC convergence gates
   ├── P4-B  Detection-floor FAP calibration
   ├── P4-C  Weighted χ² + odd/even + ephemeris matching
   ├── P4-D  Limb-darkening single source of truth   ◄── [DEC-LIC gate]
   ├── P4-E  Subtraction geometry + detrending window ◄── [DEC-LIC gate]
   ├── P4-F  Inference wiring (Candidate → MCMC)
   └── P4-G  TLS multiprocessing unlock landing   ── depends on P05-A
   │
   ▼
Phase 5  VALIDATION & RELEASE
   P5-A  Validation corpus + injection-recovery CI gate
   P5-B  Deployment (Docker Compose + Caddy + Fly/Hetzner)
   P5-C  Research credibility (ASCL + Zenodo + JOSS)
```

```
══════════════════════════════════════════════════════════════
DEC-LIC  batman licensing decision          [USER DECISION — external gate]

  NOT a bucket. NOT in the sequence above. Owns no code, has no exit
  gate, and is never executed by a session. It is a decision the user
  must make and record.

  BLOCKS: any bucket that would make `batman` a required runtime
  dependency, or that changes the transit-subtraction implementation —
  most importantly P4-D and P4-E, and any packaging/release bucket
  (P5-B, P5-C) that ships a license declaration covering it.

  Resolving it early is strongly recommended (see §5): it gates Phase 4
  science, so deciding it at Phase 5 is too late.
══════════════════════════════════════════════════════════════
```

**Vertical arrows = hard dependency.** A bucket may not start until its
predecessor's handoff manifest exists. **Parallel markers (║)** = the
buckets touch disjoint file sets and may run concurrently.

**Edge types** (applied to the dependency map in §2 and explained in §3):

* `HARD` — the predecessor bucket must *complete* first (its handoff
  manifest must exist). The successor is blocked on delivered work.
* `CONTRACT` — a shared contract the successor imports must exist first.
  The predecessor need not be fully done, but the contract is frozen.
* `VALIDATION` — the successor requires a *verified measurement or
  baseline* before it may start. Measured numbers, not intent.

---

## 2. Bucket inventory

Each bucket is one coherent engineering objective. Tag meanings (directive
§47): `[INFRA]` infrastructure, `[CONTRACT]` a shared schema/interface that
others depend on, `[UX]` user-facing, `[SCIENCE]` changes numerical
behaviour, `[VALIDATION]` measurement/verification, `[RELEASE]` packaging,
distribution, or credibility.

| ID | Bucket | Phase | Tag | Effort | Dep type | Depends on |
|---|---|---|---|---|---|---|
| P05-A | TLS multiprocessing benchmark | 0.5 | `[VALIDATION]` | 3–5 d | VALIDATION | Phase 0 — **COMPLETE**: measured 1.06x-2.08x at 8 threads (not the projected 6-8x); nested-pool mechanism confirmed; unlock deferred to P4-G. See `benchmarks/results/P05A_HANDOFF.md`. |
| P1-A | Canonical `Dataset` contract | 1 | `[CONTRACT]` | 3–4 d | HARD | Phase 0 — **COMPLETE**. Handoff: `docs/handoffs/P1-A_dataset_contract.md` |
| P1-B | `AnalysisResult` v1 schema + alias map | 1 | `[CONTRACT]` | 4–5 d | CONTRACT | P1-A — **COMPLETE**. Handoff: `docs/handoffs/P1-B_analysis_result.md` |
| P1-C | Provenance contract | 1 | `[CONTRACT]` | 2–3 d | CONTRACT | P1-B — **COMPLETE**. Handoff: `docs/handoffs/P1-C_provenance.md` |
| P1-D | Ingestion consolidation onto the seam | 1 | `[INFRA]` | 3–4 d | HARD | Phase 0 — **COMPLETE**. Handoff: `docs/handoffs/P1-D_ingestion_consolidation.md` |
| P1-E | Job persistence (SQLite WAL) | 1 | `[INFRA]` | 3 d | — | — — **COMPLETE**. Handoff: `docs/handoffs/P1-E_job_persistence.md` |
| P1-F | Worker / IPC architecture | 1 | `[INFRA]` | 5–7 d | VALIDATION | P05-A — **COMPLETE**. Handoff: `docs/handoffs/P1-F_worker_ipc.md` |
| P1-G | Real-data async integration | 1 | `[INFRA]` | 3–4 d | HARD | P1-D, P1-F — **COMPLETE**. Handoff: `docs/handoffs/P1-G_real_data_async.md` |
| P1-H | FastAPI + JWT API layer | 1 | `[INFRA]` | 4–5 d | CONTRACT | P1-B, P1-C, P1-E — **COMPLETE**. Handoff: `docs/handoffs/P1-H_api_layer.md` |
| P1-I | Search-loop unification | 1 | `[INFRA]` | 2–3 d | HARD | P1-F — **COMPLETE**. Handoff: `docs/handoffs/P1-I_search_loop_unification.md` |
| P2-A | Vertical slice backend | 2 | `[VALIDATION]` | 3–4 d | HARD | P1-G, P1-H — **COMPLETE**. Handoff: `docs/handoffs/P2-A_vertical_slice_backend.md` |
| P2-B | Vertical slice frontend | 2 | `[UX]` | 3 d | HARD | P2-A — **COMPLETE**. Handoff: `docs/handoffs/P2-B_frontend_slice.md` |
| P3-A | Frontend foundation | 3 | `[UX]` | 4–5 d | HARD | P2-B — **COMPLETE**. Handoff: `docs/handoffs/P3-A_frontend_foundation.md` |
| P3-B | Investigate route | 3 | `[UX]` | 5–7 d | CONTRACT | P3-A — **COMPLETE**. Handoff: `docs/handoffs/P3-B_investigate_route.md` |
| P3-C | Analyses route | 3 | `[UX]` | 3–4 d | CONTRACT | P3-A, P1-H — **COMPLETE**. Handoff: `docs/handoffs/P3-C_analyses_route.md` |
| P3-D | Simulate route | 3 | `[UX]` | 4–5 d | CONTRACT | P3-A — **COMPLETE**. Handoff: `docs/handoffs/P3-D_simulate_route.md` |
| P3-E | Settings route + BYOK | 3 | `[UX]` | 2–3 d | CONTRACT | P3-A — **COMPLETE**. Handoff: `docs/handoffs/P3-E_settings_route.md` |
| P3-F | Visualization integration | 3 | `[UX]` | 4–5 d | CONTRACT | P3-A — **COMPLETE**. Handoff: `docs/handoffs/P3-F_visualization.md` |
| P3-G | Copilot (SSE) | 3 | `[UX]` | 4–5 d | CONTRACT | P3-A, P1-H — **COMPLETE**. Handoff: `docs/handoffs/P3-G_copilot.md` |
| P3-H | E2E QA + Streamlit side-by-side | 3 | `[VALIDATION]` | 3–4 d | HARD | P3-B…G — **COMPLETE** (Playwright spec collected, browsers CI-only). Handoff: `docs/handoffs/P3-H_e2e_qa.md` |
| P3-I | Streamlit freeze (`--legacy`) | 3 | `[INFRA]` | 1–2 d | HARD | P3-H — **COMPLETE**. Handoff: `docs/handoffs/P3-I_streamlit_freeze.md` |
| P4-A | MCMC convergence gates | 4 | `[SCIENCE]` | 4–5 d | VALIDATION | P3-H — **COMPLETE** (v0.0.3). Handoff: `docs/handoffs/P4-A_mcmc_gates.md` |
| P4-B | Detection-floor FAP calibration | 4 | `[SCIENCE]` | 3–4 d | VALIDATION | P3-H — **COMPLETE** (measurement only; floor unchanged). Handoff: `docs/handoffs/P4-B_fap_calibration.md` |
| P4-C | Weighted χ² + odd/even + ephemeris | 4 | `[SCIENCE]` | 3–4 d | VALIDATION | P3-H — **COMPLETE** (available, not yet wired). Handoff: `docs/handoffs/P4-C_vetting_diagnostics.md` |
| P4-D | Limb-darkening single source of truth | 4 | `[SCIENCE]` | 4–5 d | VALIDATION | P3-H, `[DEC-LIC]` |
| P4-E | Subtraction geometry + detrending window | 4 | `[SCIENCE]` | 2–3 d | CONTRACT | P4-D, `[DEC-LIC]` |
| P4-F | Inference wiring (Candidate → MCMC) | 4 | `[SCIENCE]` | 5–7 d | HARD | P4-A |
| P4-G | TLS multiprocessing unlock landing | 4 | `[SCIENCE]` | 1–2 d | VALIDATION | P05-A, P1-F |
| P5-A | Validation corpus + IR CI gate | 5 | `[VALIDATION]` | 4–5 d | VALIDATION | P4-* |
| P5-B | Deployment (Compose + Caddy + Fly) | 5 | `[RELEASE]` | 3–4 d | HARD | P5-A |
| P5-C | Research credibility (ASCL/Zenodo/JOSS) | 5 | `[RELEASE]` | 3–4 d | HARD | P5-B |

**Total: 32 entries — 31 implementation buckets + 1 user decision gate.**
Summing the effort ranges above gives **100–133 working days (≈116 at the
midpoint)**, excluding the decision gate — consistent with PRD §16's
"plausible but tight" 14–17 week envelope with parallelism.

`[DEC-LIC]` in the *Depends on* column is **not a bucket dependency** — it
marks a decision gate the user must resolve before that bucket starts (see
§2.1 below). A bracketed gate never contributes to the `Dep type`.

### 2.1 Decision gate (not an implementation bucket)

| ID | Item | Kind | Resolved by | Blocks | Effort |
|---|---|---|---|---|---|
| DEC-LIC | `batman` licensing decision — whether the GPL-licensed `batman` package may become a required runtime dependency, or must stay optional/behind a flag, or be replaced | **USER DECISION / decision gate — RESOLVED 2026-09-22: keep OPTIONAL (status quo)** | the user — recorded in `AUDIT_LOGBOOK.md` Entry 16 | P4-D, P4-E (subtraction implementation), and any P5-B/P5-C step that ships a license declaration covering `batman` | user decision, no engineering estimate |

**Rules that make this a gate rather than a bucket:**

* it owns no files, ships no code, and produces no handoff manifest, so it
  cannot satisfy the bucket exit gate (§9);
* it is **excluded from the sequential execution chain in §5** and from all
  parallel groups in §6 — no session is ever assigned it;
* it is not a `[RELEASE]` bucket and is no longer counted as Phase 5 work;
* until resolved, the status quo holds: `batman` remains optional and the
  subtraction implementation is unchanged.

---

## 3. Bucket dependencies (why each edge exists)

* **P1-A → P1-B** `[CONTRACT]` — `AnalysisResult` carries `dataset_id` as
  a foreign key to the `Dataset` contract, so the dataset's identity
  (content hash *over the arrays*, not metadata — PRD §5) must be defined
  first.
* **P1-B → P1-C** `[CONTRACT]` — provenance records which config +
  capability snapshot produced which `AnalysisResult`; it references the
  result schema.
* **P05-A → P1-F** `[VALIDATION]` — the worker/IPC redesign
  (`Process`→`Popen`, `Queue`→JSONL) is *scoped from measured numbers*.
  Landing the unlock without a benchmark is forbidden (PRD §17 risk
  register).
* **P1-D + P1-F → P1-G** `[HARD]` — real data has never crossed the async
  subprocess boundary (PRD §18); the worker needs both the consolidated
  ingestion and the new IPC to do it.
* **P1-B + P1-C + P1-E → P1-H** `[CONTRACT]` — the API serialises
  `AnalysisResult`, **attaches the provenance record that P1-C defines**
  (every API result must carry provenance, PRD §5), and persists jobs.
  All three contracts must exist or the endpoints are invented ad hoc —
  omitting P1-C would force the API layer to invent a throwaway
  provenance shape that later has to be migrated.
* **P1-F → P1-I** `[HARD]` — the sync/async search loops have drifted
  (PRD §2.5); unifying them only makes sense once the worker topology is
  final, otherwise the unified target keeps moving.
* **P3-A → (P3-B…G)** `[CONTRACT]` — routes share the shell, the generated
  API client, and the theme; foundation first prevents five incompatible
  shells.
* **P3-H → P4-*** `[VALIDATION]` — accuracy changes are validated *against
  the Streamlit baseline*, which must still be live and green until Phase 3
  exits (PRD §16 constraint). Science buckets may not start before the
  reference is frozen and comparable.
* **P4-D → P4-E** `[CONTRACT]` — subtraction geometry and the detrending
  window both consume limb-darkening coefficients; a single LD source of
  truth must exist first (PRD §16.1 items 4–6).
* **P4-A → P4-F** `[HARD]` — inference wiring needs the seeded, gated
  sampler.
* **`[DEC-LIC]` on P4-D / P4-E** — *not* a dependency edge. It is the user
  decision gate of §2.1: until it is resolved, no bucket may make `batman`
  a required runtime dependency or alter the subtraction implementation.
  This is why P4-D and P4-E carry a bracketed gate rather than an extra
  bucket in their `Depends on`.

---

## 4. Shared contract ownership

The files below are **single-owner**. Two buckets editing the same contract
simultaneously is the definition of false independence (directive §45).

| Contract | Owner | Consumers (read-only) |
|---|---|---|
| `astraeus/contracts/dataset.py` (new) | **P1-A** | P1-B, P1-C, P1-G, P1-H, P2-A |
| `astraeus/contracts/analysis_result.py` (new) | **P1-B** | P1-C, P1-H, P2-A, P3-B, P3-C, P3-G |
| `astraeus/contracts/provenance.py` (new) | **P1-C** | P1-H, P2-A, P3-B |
| `astraeus/core/capabilities.py` | **Phase 0 (frozen)** | P1-B adopts `CapabilitySnapshot` unchanged |
| SQLite schema + migrations | **P1-E** | P1-H, P2-A |
| JSONL worker event vocabulary | **P1-F** | P1-G, P1-H, P3-B |
| OpenAPI schema (generated) | **P1-H** | P3-A (client generation) |
| `astraeus/core/detrending.py` numerics | **P4-E** | P4-D consults, P4-G consumes |
| `astraeus/analysis/detection.py` result emission | **P1-B** | — (P4-* patch *within* it, sequentially) |

**Rule:** if a bucket needs to change a contract it does not own, it
either (a) files the change as a dependency on the owning bucket, or
(b) the owning bucket absorbs it. Never edit another bucket's contract
in place.

---

## 5. Recommended execution order

**Strictly sequential (safest, one session at a time):**

```
P05-A → P1-A → P1-B → P1-C → P1-D → P1-E → P1-F → P1-G → P1-H → P1-I
      → P2-A → P2-B → P3-A → P3-B → P3-C → P3-D → P3-E → P3-F → P3-G
      → P3-H → P3-I → P4-A → P4-B → P4-C → P4-D → P4-E → P4-F → P4-G
      → P5-A → P5-B → P5-C
```

**DEC-LIC is deliberately absent from this chain.** It is the external user
decision gate of §2.1, not an implementation bucket, so no session is
assigned it and it never appears in the sequence. But it is a *hard
prerequisite on the decision axis*: it must be resolved **before** any
bucket that makes `batman` a required runtime dependency or changes the
subtraction implementation — most importantly **P4-D and P4-E**. Resolving
it during Phase 5 is too late, because Phase 4 science has already baked in
the answer; resolve it before Phase 4 starts, ideally at the same time as
P1-A (it needs no engineering prerequisite at all).

**Why this order:** contracts before implementations (directive §46);
measurement before the IPC redesign; the frontend foundation before any
route; and no scientific change before the Streamlit baseline is frozen
and a comparison harness exists (PRD §47 — scientific isolation).

---

## 6. Parallelization opportunities

These groups have **disjoint file sets** and may run as concurrent
sessions:

1. **During contracts:** `P1-D` (ingestion: `core/ingestion.py`,
   `core/lightkurve_client.py`, `data/loader.py`, `dashboard/services/`)
   is disjoint from `P1-A/B/C` (new `astraeus/contracts/`). → **P1-D ∥
   (P1-A → P1-B → P1-C)**.
2. **During Phase 1 infrastructure:** after `P1-E` and `P1-F` land,
   `P1-G` and `P1-H` touch disjoint layers (worker internals vs the API
   surface) and can overlap once the `P1-B`/`P1-C`/`P1-E` contract
   handoffs exist (`P1-H`'s `[CONTRACT]` edge needs all three).
3. **Frontend routes:** `P3-B/C/D/E/F/G` each own a distinct route
   directory and are parallel **after `P3-A`**. Coordination contract: the
   generated API client and the route registry in `P3-A`.
4. **Phase 4 science (partially):** `P4-A` (`error_analysis.py`,
   `fitting.py`) ∥ `P4-B` (`detection.py` thresholds + noise model) ∥
   `P4-C` (`vetting.py`) — *provided* each lands behind its own feature
   flag and `P4-D` is NOT run concurrently (it spans the same files).
   `P4-D` is the serialization point; run it alone.

**Scale up/down:** removing a session means running the next bucket in the
sequence; adding one means pulling from a parallel group. The DAG never
needs re-deriving.

---

## 7. Merge-conflict risks

| Risk | Mitigation |
|---|---|
| **`detection.py` is the most-edited file in Phase 4** (P4-B/C/D all touch it) | Run those buckets strictly sequentially; require each to add a feature flag, not a branch in shared logic. |
| **`orchestrator.py` touched by P1-F, P1-I, P4-G** | P1-F owns the worker rewrite; P1-I and P4-G explicitly depend on it. |
| **The two search loops (`run_multi_planet_search` vs `_subprocess_search_worker`) have already drifted** | Any guardrail fix must patch *both* (PRD §17). P1-I exists to retire the drift; before it, both loops are in scope for any guardrail change. |
| **`app.py` + `ui/pages/detective.py` (868 lines, 138 `st.` calls) until P3-I** | Declared out of scope for every Phase 1–2 bucket; only P3-* may touch the new frontend, and `detective.py` ports last (PRD §17: "a rewrite in disguise"). |
| **`requirements.txt` / `pyproject.toml` drift** | `pyproject.toml` is authoritative (Phase 0 rule). Any dependency change must edit pyproject first. |
| **Generated OpenAPI client** | Generated by `P1-H`'s contract, consumed read-only by `P3-A`. Regeneration is a `P1-H` action. |

---

## 8. Scientific-change isolation

**Every `[SCIENCE]` bucket (Phase 4) MUST state, in its prompt and its
handoff manifest:** baseline version (`astraeus.__version__` at time of
change); the expected numerical behaviour change; the validation corpus
(the 13 cached reference targets, PRD §14); the required comparison
(golden-master vs the frozen Streamlit baseline, with statistical
tolerances — never bit-exact, PRD §7); tolerance/acceptance criteria; and
the versioning requirement (bump version + document as a versioned
scientific change, PRD §16.1).

**Every bucket that touches shared scientific or presentation behaviour
MUST state whether Streamlit must remain unchanged** (directive §48). The
default until Phase 3 exit:

> **Streamlit = the live QA/reference implementation. Do not break it.**

If a bucket intentionally changes behaviour Streamlit exposes, it must say
why, whether that belongs to parity or Phase 4 science, and whether a
comparison test is required. Phase 0's fail-closed change is the precedent:
it changed Streamlit-visible results *by design* and is documented as such.

Feature flags: each `[SCIENCE]` bucket ships its change behind a flag with
the old path available for one release (PRD §21, Phase 4 definition of
done).

---

## 9. Required exit gates

Every bucket's prompt must carry these, plus bucket-specific gates
(directive §50). A bucket is complete only when demonstrated, never when it
"appears complete".

```text
## EXIT GATE
[ ] implementation complete
[ ] targeted tests pass
[ ] relevant existing tests pass (fast gate: 353 passed / 0 failed --
    see README "Verification"; a bucket that drops below this must
    explain the delta)
[ ] no prohibited subsystem changed
[ ] documentation updated if required
[ ] git diff reviewed
[ ] git status reviewed
[ ] handoff manifest produced
```

---

## 10. Handoff manifest (required output of every bucket)

Every bucket must end by producing this, so the next session consumes the
handoff without reconstructing history (directive §52):

```text
BUCKET: P1-C
STATUS: COMPLETE

PROVIDES:
- provenance.json schema v1
- provenance serialization on AnalysisResult

CONSUMED BY:
- P1-H
- P2-A
- P3-B

NEW CONTRACTS:
- Provenance

FILES OF INTEREST:
- astraeus/contracts/provenance.py
- tests/contracts/test_provenance.py

KNOWN CONSTRAINTS:
- hashes must cover arrays, not metadata (PRD §5)
- atomic writes follow the completeness-subsystem pattern

NEXT REQUIRED ACTION:
- P1-H may now serialize provenance in the API layer
```

---

## 11. Future prompt-generation rules

Each bucket gets a dedicated, **self-contained** implementation prompt
(directive §55). A fresh session must be able to execute it with no
knowledge of this conversation. Required sections:

```text
ASTRAEUS — BUCKET <ID>

ROLE
You are implementing exactly one bounded ASTRAEUS engineering bucket.

GOVERNING SPECIFICATION
PRD_v4.1_web_platform.md (sections: <named>)

CURRENT STATE
<verified repository state: branch, SHA, what Phase 0 + prior buckets
delivered, and the exact handoff manifests that exist>

DEPENDENCIES
<completed buckets required, and what they provide>

OBJECTIVE
<one coherent objective>

MUST CHANGE
<exact scope — files/subsystems this bucket owns>

MUST NOT CHANGE
<exact exclusions — see EXECUTION_BUCKETS.md §4 contract ownership and
§7 conflict risks; plus: no premature web stack, no scientific algorithm
change unless the bucket is [SCIENCE], no licensing change without
authorization, no optimisation before measurement>

ARCHITECTURAL CONTRACTS
<relevant locked contracts: capability snapshot, tls_outcome,
Artifact-as-reference, JSON wire format, Streamlit-stays-live, etc.>

IMPLEMENTATION REQUIREMENTS
<detailed task>

TEST REQUIREMENTS
<targeted tests + which existing tests must stay green>

EXIT GATES
<concrete verification commands and expected outputs>

DELIVERABLES
<files/artifacts>

HANDOFF
<what downstream buckets may rely on>

STOP CONDITION
Do not execute the next bucket. Report which bucket is recommended next.
```

Rules: MUST NOT CHANGE is mandatory (directive §49). Never reference
"our previous discussion". Never auto-continue into the next bucket
(directive §53). State unresolved user decisions explicitly (§51) —
notably the `batman` licensing decision, which is the **DEC-LIC** user
decision gate of §2.1 (not a bucket; it blocks P4-D/P4-E and must be
resolved before Phase 4), and the perf unlock (P05-A).

---

## 12. Readiness

Phase 0 delivered the prerequisites every bucket above assumes:

* a real installable package (`pyproject.toml`, `__version__`,
  `python -m astraeus` from any CWD);
* the `CapabilitySnapshot` / `TlsOutcome` vocabulary that `AnalysisResult`
  (P1-B) adopts without redesign;
* fail-closed science, so a Phase 1 worker can trust a `FAILED` result;
* CWD-independent artifact paths, so jobs and containers resolve paths
  deterministically;
* a green fast gate as the no-regression contract. Verified at the close
  of Phase 0: `353 passed, 1 skipped, 36 deselected, 0 failed, exit 0`
  (`pytest tests/ -m "not network and not slow"`, 19m49s), against a
  pre-Phase-0 baseline of `286 passed, 1 skipped, 37 deselected`. Phase
  0 added 70 targeted tests in `tests/phase0/` and fixed the one
  regression it introduced (repo-root detection in
  `astraeus/core/paths.py`), so the gate grew without a single
  unexplained failure. Every bucket below inherits that gate as its
  no-regression contract.

**P05-A (the TLS multiprocessing benchmark) is COMPLETE.** The harness,
measured data, written result, and handoff manifest live under
`benchmarks/`; the unlock decision they support is recorded there and
summarised in the P05-A row of §2.

The headline correction to the plan: the projected **6-8x** speedup from
`daemon=False` + `use_threads=cpu_count()` measures at **1.06x-2.08x** on
the production BLS-narrowed window (geometric mean ~1.4x, i.e. 13%-26% of
the ideal Amdahl bound), with some arms non-monotonic in thread count and
one slower than serial. Serial and parallel return bit-identical SDE /
period, so the unlock is a performance change rather than a scientific one.
The nested-pool mechanism (`daemon=True` cannot create the Pool TLS needs,
`daemon=False` can) is confirmed on the real Kepler-90 call stack.

Two caveats that downstream buckets must honour: the measurement was taken
on Windows (spawn), so PRD v4.1's Linux scope means the production number
must be re-measured on the deployment platform before P4-G ships; and the
plan's "~149.7 s on Kepler-90 defaults" was measured under a BLS-narrowed
828-period window, not TLS defaults -- true defaults exceeded a 900 s
budget single-threaded on the 1240 d baseline.

**Phase 1 is COMPLETE** (all nine buckets, verified by the full fast gate).
Every bucket's exit gate is demonstrated rather than asserted, and each has
a handoff manifest under `docs/handoffs/` naming what the next bucket may
rely on. The next isolated task is **P2-A, the vertical-slice backend**: it
composes the P1-H API layer with the P1-G real-data bridge to run one real
target end to end through the worker + supervisor, which is what proves the
Phase 1 architecture. P3-A may generate its API client from P1-H's OpenAPI
schema in parallel once P2-B lands.

The P1-F worker/IPC redesign was scoped from P05-A's measured numbers
rather than the projected speedup; the TLS unlock lands only as P4-G
behind a feature flag, on the now-unified search loop (P1-I).
