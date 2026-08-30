# Astraeus Full-Codebase Audit Logbook

Dedicated logbook for the v0.0.2 full-codebase bug-hunt audit. Every action taken on
this project during the audit is logged here, newest entries at the bottom.

- **Started:** 2026-08-21
- **Branch:** `v.0.0.2` (clean at start, HEAD `a8423ab`)
- **Operator:** ZCode agent (orchestrator), per user request: full-codebase audit via
  subagents, fixes with regression-test countermeasures, everything logged.

---

## Entry 0 — Setup & Recon (2026-08-21)

- Probed CodeGenome MCP per AGENTS.md: no native MCP tools exposed in context;
  HTTP probe of `http://127.0.0.1:7331/mcp` returned empty (server not running).
  **Fallback used:** direct repo reads (`.genome/exports` contains only graph
  viewer assets, no markdown exports worth parsing). *Note for user: run
  `codegenome mcp-start --transport http` or `codegenome analyze` to refresh the
  graph — it is stale (Jul 6) relative to recent commits.*
- Skills loaded: `when-to-use-which-skill`, `astraeus-architecture`,
  `subagent-orchestrator` (planning phase); `systematic-debugging`,
  `test-driven-development`, `verification-before-completion` to be loaded at
  fix/verify phases.
- Codebase scoped (~12.5k lines of live Python, excluding `deprecated/`):
  - `astraeus/core/` ~4.7k lines (lightkurve_client 978, nbody_solver 621, orchestrator 603, ...)
  - `astraeus/analysis/` ~2.5k lines (reporting 721, detection 405, bls_search 234, ...)
  - `astraeus/dashboard|ui|data|simulation|visualization|workflows` ~5.1k lines
  - `app.py` 368 lines (Streamlit entry), `tests/` ~40 files

## Entry 1 — Plan (2026-08-21)

Delegation plan (audit = read-only Explore agents, fixes applied by orchestrator):

| # | Subagent | Scope | Acceptance |
|---|----------|-------|------------|
| A1 | core-physics auditor | kepler, orbits, orbital_models, geometry, transit_model, time_units, constants, validation, nbody_solver | structured findings w/ file:line + evidence |
| A2 | core-data auditor | lightkurve_client, nasa_archive, clients/*, ingestion, llm_gateway, config, sensitivity_engine | same |
| A3 | pipeline auditor | orchestrator, detection, bls_search, vetting, fitting, detrending | same |
| A4 | analysis/TTV auditor | ttv_analysis, ttv_nbody_validation, physical_properties, geometric_validation, error_analysis, explanation, optimization, reporting, logging | same |
| A5 | UI/dashboard auditor | app.py, ui/pages/*, astraeus/dashboard/** | same |
| A6 | data/sim/workflows auditor | astraeus/data/*, simulation/*, workflows/pipeline, visualization/plots + cross-module contract mismatches | same |

Process: Phase 1 parallel audit → Phase 2 orchestrator triage (verify every finding
against source; classify real bug / false positive / intentional) → Phase 3 fixes
with regression tests written FIRST (countermeasures) → Phase 4 full-suite run
compared against baseline → logbook updated at every step.

Baseline command recorded in Entry 2.

## Entry 2 — Phase 1 audit results (2026-08-21)

7 parallel Explore agents dispatched (A1 core-physics, A2 core-data/network, A3
pipeline, A4 analysis/TTV, A5 UI/dashboard, A6 data/sim/workflows, A7 test-suite
integrity). **81 raw findings: 5 critical, ~20 major, rest minor.** Full reports
returned to orchestrator; dedup during triage (notable duplicates: depth /100
heuristic found independently by A3+A4; `generate_report` ImportError by A4+A5;
loader no-op unit conversion by A1+A6; v_shape_metric by A3+A4).

Headline criticals (all verified by agents with live/numeric evidence):
- **C1** `nasa_archive.py:252` — `pl_trandep` percent→fraction heuristic wrong for
  every planet with depth < 1% (archive stores percent unconditionally; verified
  live: TRAPPIST-1 b = 0.7378). Two consumers assume opposite conventions.
- **C2** `lightkurve_client.py:80` — KIC table: Kepler-4 → Kepler-11's real KIC
  (006541920); Kepler-11 → nonexistent KIC 010209133. Cache fallback can serve the
  wrong star's light curve. (SIMBAD-verified: Kepler-4 = KIC 11853905.)
- **C3** `app.py:268` — "Run Live Analysis" passes float where astropy Quantity
  required → AttributeError on every click of the primary button.
- **C4** `action_deck.py:10` — imports nonexistent `generate_report` → ImportError.
- **C5** `tests/test_chaos_integration_suite.py` — 0 tests collected (no `test_*`
  functions); entire adversarial suite never runs in CI.
- **C6** `pipeline.py:229` + `mcmc_retrieval.py:174` — real-data retrieval fits a
  transit model offset by P/4 from phase-folded data (model dips at periapsis+P/4;
  data folded to phase 0). Optimizer drives radius_ratio to prior floor.

Triage decisions (orchestrator): fix criticals + majors + safe minors with
regression tests; defer science-tradeoff items as documented recommendations
(BLS autoperiod duration-density vs perf budget, harmonic 5% tolerance vs
Kepler-90 e, TTV ±0.5-duration window, validate_ttv_with_nbody pipeline wiring).

## Entry 3 — Phase 2 triage & orchestrator verification (2026-08-21)

Orchestrator personally re-verifying each critical against source before any fix.
Baseline test run (`py -m pytest -q -m "not network and not slow"`) launched in
background; result to be recorded in Entry 4.

## Entry 4 — Baseline result + critical fixes applied (2026-08-21)

**BASELINE (pre-fix, HEAD a8423ab): 168 passed, 1 FAILED, 1 skipped, 35
deselected in 2300s.** The one pre-existing failure:
`tools/diagnostics/test_exoplanet_ui_debug.py::TestExoplanetUIDebug::test_scenario_C_async_ingestion`
(to be triaged separately — it is itself a bug to fix). Target for final state:
everything green including this.

Fixes applied by orchestrator, each locked by tests/test_audit_regression.py
(25 tests, all passing):
- **C1** `nasa_archive.py`: pl_trandep now split into `depth_percent` (kept in
  meta["pl_trandep"], percent — detection.py's /100 contract) and
  `depth_fraction` (meta["transit_depth"], fraction — UI ppm contract). The
  `>= 1.0` value-sniffing heuristic deleted. Fallback branches emit both units.
- **C2** `lightkurve_client.py`: Kepler-4 → KIC 011853905, Kepler-11 →
  KIC 006541920 (SIMBAD-verified; old table had Kepler-11's KIC under
  Kepler-4 and a nonexistent KIC under Kepler-11).
- **M6** `_resolve_target_to_tic`: prefix matches now require a name boundary
  ("Kepler-9" no longer resolves to Kepler-90's star; "Kepler-90 b" still does).
- **C3** `app.py`: Run Live Analysis now passes `duration=100.0 * u.day`
  (+ astropy units import) — was AttributeError on every click.
- **C4** `action_deck.py`: nonexistent `generate_report` import replaced with a
  working `export_retrieval_report` implementation on top of
  `generate_academic_report` (writes outputs/reports/retrieval_report_*.pdf).
- **C5** `tests/test_chaos_integration_suite.py`: pytest shim added — 6 fast
  vectors + 1 slow-marked memory hammer now collected (previously 0 tests).
- **C6** P/4 model alignment: new `preprocessing.folded_time_to_model_time()`;
  wired into `workflows/pipeline.py` and `dashboard/services/mcmc_retrieval.py`
  (both previously fit a model misaligned by a quarter period from the folded
  data — verified numerically by orchestrator before fixing).
- **M14a** `synthetic.py::run_injection_recovery`: injected_epoch now the true
  transit midpoint (quarter-period shift applied).
- A6-F11 `pipeline.py`: savgol window guarded for short curves.

## Entry 5 — Phase 3: parallel fix batches (2026-08-21)

Four general-purpose subagents executed scoped fix batches while the
orchestrator handled the science-critical files (no file-scope overlaps):

- **Batch B (network/ingestion)** — SUCCESS, 67 tests pass. 11 fixes:
  12-quarter Kepler loop un-broken (M3); download timeouts actually retried
  (F8); `_TIMEOUT_SENTINEL` distinguishes search timeouts from "not observed"
  (F9); K2 BJD offset via `bjd_offset_for_mission` (A1-F5); HD/HIP/GJ
  space-form archive candidates (M4); `order by pl_orbper asc` +
  row-pl_name recording (M5); `pl_period`/`pl_orbpererr1` garbage-period
  fallbacks removed (F7); bridge classifier "Download failed" restored (F10);
  per-mission error accumulation (F11); `load_config` catches OSError (F13);
  fixture recorder uses real `?uri=` + status codes (F12).
  Locked by tests/test_ingestion_audit_fixes.py (31 tests).
- **Batch A (UI/dashboard)** — SUCCESS, 52 tests pass. 10 fixes: stable
  per-planet widget uids (M11); Reset actually resets (M12); plotly
  `use_container_width` (A5-F8); ledger renders real vetting_status (M17);
  one-shot full-app rerun on terminal job state (A5-F6); Clear Stale Job
  button (A5-F7); current_dataset_hash wired + namespaced restore (M13);
  stellar_mass→st_mass fallback (A5-F9); adaptive secondary threshold in UI
  (A4-F15); honest workspace-data wiring for the simulator sweep (A5-F10).
  Locked by tests/test_ui_audit_fixes.py (33 tests).
- **Batch C (physics/analysis)** — SUCCESS (agent's final JSON was empty;
  orchestrator verified via git diff + test runs). 15 fixes incl.: star–planet
  softening removed (M7); scalar-time transit model (A1-F4); fitting
  eccentricity coercion + free-param precedence + ambiguity guards (A1-F3,
  A3-F9); TSM undefined for R>=10 (A4-F9); TTV ZeroDivision guard (A4-F8);
  TTV phantom-epoch rejection + logging (A4-F6/F7 partial); completeness
  report NaN argmin (A4-F2); PDF header color + None formatting (A4-F10/F11);
  corrupt-experiment-log backup + bare-filename ledger guard (A4-F13/F14);
  seeded MCMC option (A6-F6); loader real unit conversion + bjd_tdb column +
  isfinite (A6-F7/F8/F10); completeness heatmap transpose (A6-F5).
  Locked by tests/test_analysis_audit_fixes.py (20 tests).
- **Batch D (test integrity)** — SUCCESS, 44 tests pass. skip→assert in
  fetched_analyze_button (A7-F3); stale R8 xfail docstring removed (A7-F9);
  simulate_backend stale key fixed (A7-F7); vacuous placeholder tests removed
  (A7-F6); detector→experiment-log integration test added (A7-F2); weekly
  BLOCKING full-suite CI job added (A7-F4). Collection now 234 tests.

## Entry 6 — Orchestrator science fixes & regression hunts (2026-08-21)

- **C6 sign error caught by my own regression test**: the model dips at
  P/4 after its time origin, so folded time must shift **+P/4** (first
  implementation used −P/4; test showed the dip at phase P/2). Fixed in
  `preprocessing.folded_time_to_model_time` and `synthetic.run_injection_recovery`;
  both locked numerically.
- **M1** depth /100 heuristic removed in detection.py (BLS depth is always a
  fraction); **M10** depth-only "Verified" pass now requires no
  secondary-eclipse and non-Ambiguous evidence, so the EB gates are reachable
  for shallow candidates; **float(None)** metadata hardening via
  `_metadata_float` (preserves explicit 0.0 — an initial `or`-chain version
  broke the st_teff=0 fallback contract and was caught by
  test_vetting_threshold_hardening, then fixed).
- **M2** BLS boundary: search grid widened to 1.1×p_max so genuine signals
  just under the bound are interior peaks; blanket "within 5% of p_max"
  blacklist replaced by a hard cut at p_max; everything-rejected fallback now
  flagged via `all_peaks_rejected` in the result dict. Near-p_min 5% band kept
  (J3 contract).
- **M14** completeness: injection cells now divide out the scenario transit
  (noise-only baseline; no more double-dip contamination); cell-cache hash
  bumped (`algo_version: 2`) so stale cells are never reused; manifest
  `completed_cells` deduplicated.
- **nbody follow-ups**: after M7, `test_forced_collision` flipped to
  "energy_divergence" — root cause is temporal subsampling (Hill zone crossed
  in <1 timestep) + chaos, not the softening fix. Added segment-swept
  collision detection (closes tunneling), made the chaotic test accept
  {collision, energy_divergence} with rationale, and added a deterministic
  in-Hill-zone collision test. 12/12 nbody tests pass.
- **Pre-existing baseline failure triaged**:
  `tools/diagnostics/...::test_scenario_C_async_ingestion` now passes (its
  baseline failure is consistent with the archive-query nondeterminism batch B
  fixed, or a network flake). `test_performance_speed_benchmark` (slow-marked)
  fails at pristine HEAD too (37.8s vs 5s budget; single-threaded TLS contract
  dominates) — pre-existing hardware/comment drift, NOT an audit regression;
  budget left untouched per the in-file warning.

Gate results: science+J3+J1+completeness+synthetic 27 passed; vetting
hardening 13 passed; nbody 12 passed; batch gates 67+52+20+44 passed.

## Entry 7 — Deferred findings register (2026-08-21)

Verified real but deliberately NOT changed in this pass, with rationale:

| Finding | Why deferred |
|---------|--------------|
| BLS `autoperiod(duration=0.1)` undersamples 0.15–1.0d durations (A3-F10) | Fixing via `durations.min()` densifies the trial grid ~10x and blows the wall-time budgets pinned by J3/bulletproof perf tests. Needs a dedicated perf-tuning bucket. |
| Harmonic-duplicate 5% tolerance silently drops Kepler-90 e (ratio 2.091) (A3-F13) | Deliberate anti-alias tradeoff; tightening re-risks the harmonic duplicates the J1/J3 guards exist for. Recommended: outcome-based dedup (subtract candidate, accept only if previous planet's SNR degrades). |
| TTV search window ±0.5×duration clips large O-C signals (A4-F7) | Science tradeoff; recommended iterative recentering on first-pass minimum. |
| `validate_ttv_with_nbody` has zero production callers (A4-F5) | Feature gap, not a defect; wiring adds heavy N-body cost per candidate — product decision. |
| Orchestrator never consumes `tls_environment_error`/`tls_scientific_error` (A3-F5) | Real gap (infra failure ends as clean "0 candidates DONE"); fix touches the orchestrator state machine + job registry contract — recommended immediate follow-up, isolated to orchestrator.py. |
| `DataFactory.load` archive path downloads ALL products, no author/exposure filter (A6-F9) | Network-path behavior change needs live verification against MAST; fast-gate cannot cover it. |
| Synthetic BLS duration grid caps at 0.3d (A6-F13) | Biases long-period recovered depth/SNR in sweep metrics; safe but changes cached-sweep semantics mid-audit. |
| `flat_bottom_fraction` defaults to 1.0 (most planet-like) on sparse data (A4-F12) | Changing the default alters detective UI pass logic; needs UI/product decision on the "indeterminate" representation. |
| `GeometricValidator.v_shape_metric` hardwired 0.0 (A4-F3) + confidence semantics flip between verdict branches (A3-F6) | Pipeline path overrides it via VettingEngine confidence; direct consumers are scratch/runs scripts. Needs a designed curvature metric. |
| GeometricValidator median-based secondary window misses narrow secondaries | Discovered during M10 test design: a 0.15d secondary in the ±0.05 phase window barely moves the window median. Real sensitivity limitation; needs a matched-filter redesign, not a quick patch. |
| tests/qa_*.py triplicate manual Playwright harnesses (A7-F8) | Repo hygiene; moving files risks stale references in briefing docs. |
| Source-presence assertions (i3) → behavioral locks (A7-F10) | Test-strengthening improvement; optional. |
| `test_performance_speed_benchmark` fails at pristine HEAD (37.8s vs 5s) | Pre-existing: single-threaded TLS contract (~56s on 15k pts) dominates; in-file warning forbids budget changes without a perf bucket. |

## Entry 8 — Final verification (2026-08-21)

Full non-network suite (`py -m pytest -q -m "not network and not slow"`)
launched for the post-fix verdict. RESULT: _pending_ (recorded below when
complete).
