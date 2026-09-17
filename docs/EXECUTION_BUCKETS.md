# ASTRAEUS — Execution Buckets

**The execution map for the remaining migration.**

Created at the close of Phase 0 (2026-09-17), branch `v.0.0.2`, commit
`3eafbd4` + Phase 0 work. Governing specification: `PRD_v4.1_web_platform.md`.

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
Phase 0 [COMPLETE]  foundation, fail-closed science, packaging
   │
   ├── P05-A  TLS multiprocessing benchmark        [VALIDATION]
   │     └── decides: land daemon=False + use_threads unlock, or not
   │
   ▼
Phase 1  CONTRACTS (sequential — they import each other)
   P1-A  Canonical Dataset contract        ──┐
   P1-B  AnalysisResult v1 schema           ──┤  (P1-A → P1-B → P1-C)
   P1-C  Provenance contract                ──┘
   │
   ├── P1-D  Ingestion consolidation (4 sites → seam)   ║ parallel with contracts
   │
   ├── P1-E  Job persistence (SQLite WAL)     ── depends on nothing
   ├── P1-F  Worker / IPC (Popen + JSONL)     ── depends on P05-A's decision
   ├── P1-G  Real-data async integration      ── depends on P1-D + P1-F
   ├── P1-H  FastAPI + JWT API layer          ── depends on P1-B + P1-E
   ├── P1-I  Search-loop unification          ── depends on P1-F
   │
   ▼
Phase 2  VERTICAL SLICE
   P2-A  Backend slice (one real target e2e)   ── depends on P1-G + P1-H
   P2-B  Frontend slice (minimal honest UI)    ── depends on P2-A
   │
   ▼
Phase 3  PRODUCT FRONTEND                          (after P3-A, routes are parallel)
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
   ├── P4-D  Limb-darkening single source of truth
   ├── P4-E  Subtraction geometry + detrending window
   ├── P4-F  Inference wiring (Candidate → MCMC)
   └── P4-G  TLS multiprocessing unlock landing   ── depends on P05-A
   │
   ▼
Phase 5  VALIDATION & RELEASE
   P5-A  Validation corpus + injection-recovery CI gate
   P5-B  Deployment (Docker Compose + Caddy + Fly/Hetzner)
   P5-C  Research credibility (ASCL + Zenodo + JOSS)
   P5-D  Licensing resolution (batman GPL — USER DECISION)
```

**Vertical arrows = hard dependency.** A bucket may not start until its
predecessor's handoff manifest exists. **Parallel markers (║)** = the
buckets touch disjoint file sets and may run concurrently.

---

## 2. Bucket inventory

Each bucket is one coherent engineering objective. Tag meanings (directive
§47): `[INFRA]` infrastructure, `[CONTRACT]` a shared schema/interface that
others depend on, `[UX]` user-facing, `[SCIENCE]` changes numerical
behaviour, `[VALIDATION]` measurement/verification, `[RELEASE]` packaging,
distribution, or credibility.

| ID | Bucket | Phase | Tag | Effort | Depends on |
|---|---|---|---|---|---|
| P05-A | TLS multiprocessing benchmark | 0.5 | `[VALIDATION]` | 3–5 d | Phase 0 |
| P1-A | Canonical `Dataset` contract | 1 | `[CONTRACT]` | 3–4 d | Phase 0 |
| P1-B | `AnalysisResult` v1 schema + alias map | 1 | `[CONTRACT]` | 4–5 d | P1-A |
| P1-C | Provenance contract | 1 | `[CONTRACT]` | 2–3 d | P1-B |
| P1-D | Ingestion consolidation onto the seam | 1 | `[INFRA]` | 3–4 d | Phase 0 |
| P1-E | Job persistence (SQLite WAL) | 1 | `[INFRA]` | 3 d | — |
| P1-F | Worker / IPC architecture | 1 | `[INFRA]` | 5–7 d | P05-A |
| P1-G | Real-data async integration | 1 | `[INFRA]` | 3–4 d | P1-D, P1-F |
| P1-H | FastAPI + JWT API layer | 1 | `[INFRA]` | 4–5 d | P1-B, P1-E |
| P1-I | Search-loop unification | 1 | `[INFRA]` | 2–3 d | P1-F |
| P2-A | Vertical slice backend | 2 | `[VALIDATION]` | 3–4 d | P1-G, P1-H |
| P2-B | Vertical slice frontend | 2 | `[UX]` | 3 d | P2-A |
| P3-A | Frontend foundation | 3 | `[UX]` | 4–5 d | P2-B |
| P3-B | Investigate route | 3 | `[UX]` | 5–7 d | P3-A |
| P3-C | Analyses route | 3 | `[UX]` | 3–4 d | P3-A, P1-H |
| P3-D | Simulate route | 3 | `[UX]` | 4–5 d | P3-A |
| P3-E | Settings route + BYOK | 3 | `[UX]` | 2–3 d | P3-A |
| P3-F | Visualization integration | 3 | `[UX]` | 4–5 d | P3-A |
| P3-G | Copilot (SSE) | 3 | `[UX]` | 4–5 d | P3-A, P1-H |
| P3-H | E2E QA + Streamlit side-by-side | 3 | `[VALIDATION]` | 3–4 d | P3-B…G |
| P3-I | Streamlit freeze (`--legacy`) | 3 | `[INFRA]` | 1–2 d | P3-H |
| P4-A | MCMC convergence gates | 4 | `[SCIENCE]` | 4–5 d | P3-H |
| P4-B | Detection-floor FAP calibration | 4 | `[SCIENCE]` | 3–4 d | P3-H |
| P4-C | Weighted χ² + odd/even + ephemeris | 4 | `[SCIENCE]` | 3–4 d | P3-H |
| P4-D | Limb-darkening single source of truth | 4 | `[SCIENCE]` | 4–5 d | P3-H |
| P4-E | Subtraction geometry + detrending window | 4 | `[SCIENCE]` | 2–3 d | P4-D |
| P4-F | Inference wiring (Candidate → MCMC) | 4 | `[SCIENCE]` | 5–7 d | P4-A |
| P4-G | TLS multiprocessing unlock landing | 4 | `[SCIENCE]` | 1–2 d | P05-A, P1-F |
| P5-A | Validation corpus + IR CI gate | 5 | `[VALIDATION]` | 4–5 d | P4-* |
| P5-B | Deployment (Compose + Caddy + Fly) | 5 | `[RELEASE]` | 3–4 d | P5-A |
| P5-C | Research credibility (ASCL/Zenodo/JOSS) | 5 | `[RELEASE]` | 3–4 d | P5-B |
| P5-D | Licensing resolution (batman) | 5 | `[RELEASE]` | user decision | — |

**Total ≈ 20 buckets, ≈ 100 working days** — consistent with PRD §16's
"plausible but tight" 14–17 week envelope with parallelism.

---

## 3. Bucket dependencies (why each edge exists)

* **P1-A → P1-B** — `AnalysisResult` carries `dataset_id` as a foreign key
  to the `Dataset` contract, so the dataset's identity (content hash *over
  the arrays*, not metadata — PRD §5) must be defined first.
* **P1-B → P1-C** — provenance records which config + capability snapshot
  produced which `AnalysisResult`; it references the result schema.
* **P05-A → P1-F** — the worker/IPC redesign (`Process`→`Popen`,
  `Queue`→JSONL) is *scoped from measured numbers*. Landing the unlock
  without a benchmark is forbidden (PRD §17 risk register).
* **P1-D + P1-F → P1-G** — real data has never crossed the async subprocess
  boundary (PRD §18); the worker needs both the consolidated ingestion and
  the new IPC to do it.
* **P1-B + P1-E → P1-H** — the API serialises `AnalysisResult` and persists
  jobs; both contracts must exist or the endpoints are invented ad hoc.
* **P1-F → P1-I** — the sync/async search loops have drifted (PRD §2.5);
  unifying them only makes sense once the worker topology is final,
  otherwise the unified target keeps moving.
* **P3-A → (P3-B…G)** — routes share the shell, the generated API client,
  and the theme; foundation first prevents five incompatible shells.
* **P3-H → P4-*** — accuracy changes are validated *against the Streamlit
  baseline*, which must still be live and green until Phase 3 exits (PRD
  §16 constraint). Science buckets may not start before the reference is
  frozen and comparable.
* **P4-D → P4-E** — subtraction geometry and the detrending window both
  consume limb-darkening coefficients; a single LD source of truth must
  exist first (PRD §16.1 items 4–6).
* **P4-A → P4-F** — inference wiring needs the seeded, gated sampler.

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

(P5-D, the licensing decision, can be resolved by the user at any point
and should be **before** P4-D/P4-E if batman is to become required.)

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
   surface) and can overlap once `P1-B`/`P1-E` handoffs exist.
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
notably the `batman` licensing decision (P5-D) and the perf unlock
(P05-A).

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

The repository is **ready for P05-A** (the TLS multiprocessing benchmark)
as the next isolated task. That benchmark is *not* part of Phase 0 and has
not been started.
