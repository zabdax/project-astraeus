# ASTRAEUS — Agent Implementation Briefs (v2)

**Purpose:** A sequence of self-contained prompts for coding agents to execute one at a time, in order. Each bucket is independent enough to hand to a fresh agent session, but assumes all prior buckets are complete and merged.

**How to use this document:** Copy one bucket's entire prompt (everything between `### AGENT PROMPT START` and `### AGENT PROMPT END`) into your coding agent. Do not skip ahead — later buckets assume earlier ones are done and verified. Do not run two buckets in parallel on the same branch.

> **Status as of this revision (v2):** The codebase has moved on since v1 of this document.
> - The frontend consolidation that Bucket 1 originally called for is **partially done** — `ui/pages/` + `route.py` is the live UI, and `astraeus/dashboard/` has been *demoted to a shared library* (still imported by `app.py` and by `ui/pages/simulator.py` + `ui/pages/settings.py`). What remains is orphan cleanup, not parallel-system consolidation.
> - Bucket 2's V-shape vetting is **partly done** — a new `astraeus/analysis/vetting.py` `VettingEngine` (U-shape vs V-shape χ² comparison) is wired into `detection.py`. What remains is the physically-grounded secondary-eclipse threshold and the remaining inline magic numbers.
> - **No CI exists.** `requirements.txt` is incomplete. Root directory has substantial scratch/debug clutter. New Buckets 6 and 7 address these.

**Global ground rules for every bucket** (also repeated inside each prompt so no single prompt depends on this header surviving):

1. Work on a dedicated git branch per bucket. Never commit directly to main/master.
2. Investigate before changing. Every bucket below starts with a read-only discovery phase. Do not modify, delete, or refactor anything until the discovery phase is complete and its findings are written down in a report file.
3. Never delete code — deprecate it. If something looks dead, move it to a `deprecated/` folder or comment it out with a dated note, rather than deleting outright. Actual deletion only happens in a later, explicit cleanup step, never in the same pass as discovery.
4. Run the existing test suite before touching anything, and again after every meaningful change. If a test that passed before your change now fails, that is a stop condition — fix it or revert before continuing, do not proceed with a known-broken state.
5. No silent fallbacks. If something can't be verified (e.g., no network access, missing dependency), say so explicitly in the report rather than assuming success.
6. Small commits. Each logical change gets its own commit with a clear message, so any single step can be reverted without losing the whole bucket's work.
7. At the end of every bucket, produce a written summary report (markdown file in `reports/`) covering: what was found, what was changed, what was tested and how, what remains uncertain or deferred, and exact commands to verify the result.

---

## Bucket order and what each one solves

| # | Bucket | Solves |
|---|---|---|
| 0 | Streamlit state & caching diagnostic | The "physics works standalone, breaks in app.py" problem — almost certainly a state/caching bug, diagnosed before any other bucket touches the UI |
| 1 | Orphan cleanup, `RemoteDiscoveryEngine` disambiguation & architecture doc | Deprecate confirmed-dead code (`astraeus/ui/`, unused dashboard panels), rename the two same-named `RemoteDiscoveryEngine` classes, and document the real architecture so later buckets stop guessing |
| 2 | Vetting threshold hardening (remaining work) | Finish what's left after the new `vetting.py`: physically-ground the secondary-eclipse threshold, extract the remaining inline magic numbers (`0.03`, `20.0`, `0.0008`, `3.0`, `1.5`) into named constants |
| 3 | Injection-recovery completeness sweep | Scale the existing `run_injection_recovery()` primitive into a real period/depth/SNR completeness map with caching and a report artifact |
| 4 | N-body × TTV cross-validation | Wire `nbody_solver.py` into `ttv_analysis.py` so detected TTV signals get checked against real N-body stability rather than just reported as residuals |
| 5 | Test suite CI-readiness | Convert the diagnostic scripts in `tests/` into proper pytest cases, fix `requirements.txt`, **create a CI workflow** (none exists today) |
| 6 | End-to-end smoke test | One fast, single-command pipeline-health check on a known synthetic target — the safety net the other buckets need |
| 7 | Root-directory hygiene | Move scratch/debug/duplicate files out of the repo root so the MVP looks like a product, not a workbench |

**Suggested ordering:** 0 and 1 first (in that order) — 0 because it's actively being debugged, 1 because every later bucket needs to know which code path is real. 6 (smoke test) immediately after 0 so 5 can wire it into CI. 7 (hygiene) is low-risk and can slot in anywhere after 1. 2 before 3 and 4 (both rely on `detection.py` behaving predictably). 5 last (it tests the final state).

---

## Bucket 0 — Streamlit state & caching diagnostic

**Why this is first:** the symptom described — physics engines work correctly when tested standalone, but break when exercised through `app.py` — is a textbook signature of one of three Streamlit-specific problems: stale `@st.cache_data`/`@st.cache_resource` returning old results after inputs change, session state not being reset between target/mission switches, or re-execution-model bugs (Streamlit reruns the whole script top-to-bottom on every interaction, which breaks code that assumes persistent in-memory state the way a normal script would). This bucket's entire job is to find out which of these it actually is, with evidence, before anyone "fixes" it by guessing.

> **Note for v2:** A prior `pytest_log.txt` shows collection hanging at `collecting ...`. Before starting, confirm the suite actually completes collection — if not, that's a separate blocker to flag in the report, possibly a conftest or import side-effect (e.g. `app.py` being imported at collection time, or one of the stress scripts in `tests/` running live network calls at import).

### AGENT PROMPT START

```
You are debugging a Streamlit application called ASTRAEUS where the underlying
physics/analysis engines (astraeus/core/, astraeus/analysis/) are confirmed
working correctly in isolation (standalone scripts, pytest), but produce bugs,
stale results, or crashes specifically when invoked through the Streamlit
frontend (app.py, ui/, and the astraeus/dashboard/ui/ panels it imports).

LIVE UI PATH (confirmed by entry-point tracing in this codebase revision):
  app.py
    -> route.render_route(...)            (route.py)
    -> ui/pages/{simulator,lab,detective,history,settings}.py
    -> shared layout/styles/chat from astraeus/dashboard/ui/
    -> "Discover" tab is rendered inline in app.py (not via route.py)
Detection / ingestion are invoked from ui/pages/detective.py, which imports
RemoteDiscoveryEngine and DataAdapter from astraeus/core/ingestion.py.

============================================================
PHASE 0 — SAFETY SETUP (do this before anything else)
============================================================
1. Confirm you are on a clean git working tree (`git status` shows no
   uncommitted changes). If not, stop and ask the user how to proceed —
   do not stash or discard their work yourself.
2. Create a new branch: `git checkout -b fix/streamlit-state-diagnostic`
3. Run the full existing test suite and save the output to
   `reports/bucket0_pretest_baseline.txt`:
       python -m pytest tests/ -v > reports/bucket0_pretest_baseline.txt 2>&1
   Note the pass/fail count. If collection HANGS or fails to finish, state
   that explicitly and record where it hangs — do not kill it silently.
   This is your baseline — you must not regress below it at any point.
4. Do NOT modify any application code in this phase. This phase is read-only.

============================================================
PHASE 1 — DISCOVERY (read-only, no code changes yet)
============================================================
Your goal is to identify the SPECIFIC mechanism causing the break, not to
guess-and-patch. Investigate all of the following and write findings to
`reports/bucket0_diagnostic_findings.md` as you go:

1. CACHING AUDIT
   - Find every use of `@st.cache_data` and `@st.cache_resource` in the
     codebase. Confirmed locations to seed the search: app.py, route.py,
     ui/pages/, astraeus/dashboard/ui/, astraeus/dashboard/services/,
     astraeus/core/ingestion.py (RemoteDiscoveryEngine.fetch_data is
     `@st.cache_data`-wrapped), astraeus/data/discovery.py.
   - For each cached function, check: does its cache key (the function
     arguments) actually capture everything that affects its output? A
     common bug is a cached function that reads global config, session
     state, or mutable default arguments that aren't part of the cache key
     — Streamlit will then silently return stale results when those
     hidden inputs change but the visible arguments don't.
   - Check specifically whether `RemoteDiscoveryEngine.fetch_data` could
     return stale data when the user switches target name or mission type
     in the UI but some other session state lags behind.
   - Document every cached function found, its cache key, and whether the
     cache key fully captures its true inputs. Flag any mismatches.

2. SESSION STATE AUDIT
   - Find every use of `st.session_state` across the UI layer (app.py,
     route.py, ui/pages/, astraeus/dashboard/ui/).
   - For each, determine: is it initialized with a guard (e.g.
     `if "key" not in st.session_state:`) or does it assume prior
     existence? Uninitialized/assumed session state is a common source of
     "works on second click but not first" or "breaks after navigating
     away and back" bugs.
   - Check whether switching between pages (Simulation/Lab/Detective/
     Discover/History/Settings via the sidebar in
     astraeus/dashboard/ui/layout.py) properly resets or correctly
     preserves state that depends on the previously active page. Look
     specifically for state from one target/mission bleeding into a
     newly selected target/mission.
   - Document every session_state key found, where it's set, where it's
     read, and whether initialization is guarded.

3. RERUN MODEL AUDIT
   - Streamlit reruns the entire script top-to-bottom on every widget
     interaction. Identify any code that assumes execution happens once
     and persists (e.g., module-level mutable state, a class instantiated
     at import time that accumulates state across reruns, a generator or
     iterator that isn't reset).
   - Pay particular attention to anywhere `detect_transit_candidate`,
     `run_mcmc`, or `run_stability_analysis` results are stored — confirm
     results are correctly keyed to their specific input parameters (e.g.
     target name + mission), not just stored under a generic key that the
     next interaction silently overwrites or incorrectly reuses.

4. REPRODUCE THE SYMPTOM
   - Attempt to reproduce a concrete failure: run `streamlit run app.py`,
     exercise a realistic flow (load target A, run detection on the
     Detective tab, switch to target B, run detection again, switch back
     to target A). Note any point where displayed results don't match
     what a fresh standalone run of the same physics functions would
     produce.
   - If you cannot run Streamlit interactively in this environment, state
     that explicitly in the findings file rather than guessing at runtime
     behavior. In that case, do the audit via static code reading only,
     and flag every suspected issue as "suspected, not runtime-confirmed."
   - Do not fabricate a reproduction you didn't actually run.

5. WRITE THE DIAGNOSIS
   At the end of `reports/bucket0_diagnostic_findings.md`, write a clear
   ranked list of root causes found, each with: the file/line, why it's a
   problem, and what evidence supports it being the actual cause (not just
   a theoretical possibility). If multiple real issues are found, rank by
   how likely each is to explain the user's actual symptom (results
   correct standalone, wrong/crashing through the UI).

============================================================
PHASE 2 — FIX (only after Phase 1 findings are written down)
============================================================
1. For each confirmed root cause (not speculative ones) in ranked order:
   a. Make the smallest possible fix that addresses the specific mechanism
      found — e.g., add missing cache key parameters, guard session state
      initialization, scope cached/stored results by their actual input
      parameters.
   b. Prefer Streamlit's built-in tools over custom state management:
      `st.cache_data(hash_funcs=...)` if a parameter needs custom hashing,
      explicit `st.session_state.clear()` or scoped keys (e.g.
      `f"result_{target_name}_{mission}"`) rather than ad-hoc global dicts.
   c. Commit this single fix separately with a message referencing the
      finding it addresses.
   d. Re-run the standalone physics tests (must still pass — this bucket
      should never touch astraeus/core/ or astraeus/analysis/ physics
      logic itself, only the UI/state layer wrapping it). If any physics
      test now fails, you have made an out-of-scope change — revert it.
   e. If you were able to run Streamlit interactively in Phase 1, re-run
      the same reproduction flow and confirm the symptom is gone. If you
      could not run it interactively, say so clearly in the report and
      mark the fix as "applied per static analysis, runtime-unverified."

2. Do NOT attempt to fix suspected-but-unconfirmed issues by guessing. If
   Phase 1 turned up something ambiguous, list it in the report under
   "needs further investigation" rather than touching code for it.

============================================================
PHASE 3 — VERIFY & REPORT
============================================================
1. Run the full test suite again:
       python -m pytest tests/ -v > reports/bucket0_posttest.txt 2>&1
   Compare against the Phase 0 baseline. Pass count must be >= baseline.
   Any new failure is a stop condition — fix or revert before finishing.

2. Write `reports/bucket0_summary.md` containing:
   - Root cause(s) confirmed, with file/line references
   - Exact changes made (list of commits)
   - What was tested and how (standalone pytest, interactive Streamlit
     reproduction if possible, or static-analysis-only with that caveat
     stated)
   - Whether collection completed cleanly, and if not, the hang location
   - Anything flagged as "needs further investigation" but not fixed
   - Exact commands the user should run to verify this themselves:
       git checkout fix/streamlit-state-diagnostic
       python -m pytest tests/ -v
       streamlit run app.py
       (and the specific manual reproduction steps to check)

3. Do not merge to main yourself. Leave the branch ready for the user to
   review and merge.

============================================================
HARD CONSTRAINTS (apply throughout all phases)
============================================================
- Do not modify any file under astraeus/core/ or astraeus/analysis/ in
  this bucket. This bucket is scoped to the UI/state/caching layer only
  (app.py, route.py, ui/, astraeus/dashboard/ui/, astraeus/dashboard/services/).
  If you believe a physics-layer change is actually required to fix the
  symptom, STOP and document why in the report instead of making the
  change — that would indicate the diagnosis is wrong and needs
  reconsideration, not that you should proceed anyway.
- Do not delete any file in this bucket, including ones that look unused
  — orphan cleanup is Bucket 1's job, with its own investigation.
- Do not rename the RemoteDiscoveryEngine classes — that is Bucket 1.
```

### AGENT PROMPT END

---

## Bucket 1 — Orphan cleanup, `RemoteDiscoveryEngine` disambiguation & architecture doc

**Why this is second:** every later bucket that touches the data layer or UI needs to know which code path is real. v1 of this brief framed this bucket as "consolidate two parallel frontends." That consolidation is **already done** — `ui/pages/` + `route.py` is the live UI, and `astraeus/dashboard/` has been demoted to a shared library (layout/styles/chat panels still imported by `app.py`; figures/simulation still imported by `ui/pages/simulator.py`; settings still imported by `ui/pages/settings.py`).

What remains is the genuinely valuable work:

1. **Three confirmed orphans** that are pure dead weight: `astraeus/ui/dashboard.py` (only referenced by one obsolete test), and any `astraeus/dashboard/ui/` panels that nothing imports.
2. **The `RemoteDiscoveryEngine` name collision** — still real, still a bug magnet: `astraeus/core/ingestion.py` defines a Streamlit-cached `RemoteDiscoveryEngine` used by the UI and stress tests; `astraeus/data/discovery.py` defines a *different* `RemoteDiscoveryEngine` (astroquery-based) used by `tests/test_discovery.py`. Two classes, identical name, different modules.
3. **No written architecture doc** — every bucket so far has had to re-derive the live path by reading source. This bucket ends that by writing one.

### AGENT PROMPT START

```
You are cleaning up orphaned code in the ASTRAEUS codebase, disambiguating
two classes that share the identical name, and documenting the real
architecture. This is NOT a "consolidate two parallel frontends" task —
that consolidation was already done in a prior revision. The live UI is
ui/pages/ + route.py, launched via app.py, with astraeus/dashboard/
demoted to a shared library (layout, styles, chat, figures, simulation,
settings) that app.py and ui/pages/ still import from.

THREE CONFIRMED-OR-PRESUMED-DEAD TARGETS TO INVESTIGATE (do not assume
any of them is dead until your Phase 1 import trace proves it):

  ORPHAN 1 — astraeus/ui/dashboard.py
    Presumed dead: a grep as of this writing finds its ONLY import is in
    tests/test_chaos_integration_suite.py:158. No live path (app.py,
    route.py, ui/pages/, astraeus/dashboard/) imports astraeus.ui.* at all.

  ORPHAN 2-? — astraeus/dashboard/ui/ panels not imported by app.py
    app.py imports exactly three things from astraeus/dashboard/ui/:
      workbench_layout   (layout.py)
      inject_page_styles (styles.py)
      render_floating_chat (components.py)
    Every OTHER module in astraeus/dashboard/ui/ (sidebar.py,
    simulation_panel.py, mcmc_panel.py, mcmc_form.py, action_deck.py,
    data_ingestion_panel.py, settings.py) must be checked individually:
    is it imported by any live path (ui/pages/, app.py, route.py) or only
    by other dashboard modules or tests? Anything with NO live importer
    is an orphan candidate.

  AMBIGUITY — two classes named RemoteDiscoveryEngine
    - astraeus/core/ingestion.py:RemoteDiscoveryEngine  (Streamlit
      @st.cache_data-wrapped, used by ui/pages/detective.py and by the
      stress/diagnostic scripts tests/{pipeline,global,solid}*.py and
      trace_download_deadlock.py via _fetch_data_impl)
    - astraeus/data/discovery.py:RemoteDiscoveryEngine  (astroquery-based,
      query_metadata / fetch_time_series / discover_and_cache, used by
      tests/test_discovery.py)

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user — do not
   stash or discard their work.
2. Branch: `git checkout -b refactor/orphan-cleanup-and-rde-rename`
3. Run full test suite, save baseline:
       python -m pytest tests/ -v > reports/bucket1_pretest_baseline.txt 2>&1
   Note pass/fail count. Do not regress below this at any point.
4. This phase is read-only. No code changes yet.

============================================================
PHASE 1 — DISCOVERY: PROVE WHAT IS ACTUALLY USED
============================================================
Do NOT delete, move, or modify anything in this phase. Produce a written
report, `reports/bucket1_orphan_investigation.md`, covering:

1. ENTRY POINT TRACING (re-confirm; the codebase may have changed)
   - Confirm the live launch path: `streamlit run app.py`. Trace its
     actual import chain at least 2 levels deep by opening files and
     reading `import` statements (do not guess from filenames).
   - Confirm which astraeus/dashboard/ui/ modules are imported by app.py
     directly, and which by ui/pages/{simulator,settings,lab,...}.py via
     route.py. Build the real import tree.
   - For each candidate orphan (astraeus/ui/dashboard.py and every
     astraeus/dashboard/ui/ panel not named above), run a ripgrep across
     the WHOLE repo for its module path AND for the symbols it exports,
     and record every hit with file:line. A hit inside its own module or
     inside tests/ does NOT count as a live import — only a hit from
     app.py, route.py, ui/, or another still-live astraeus/dashboard/
     module counts.

2. REMOTEDISCOVERYENGINE DISAMBIGUATION
   - For EACH of the two RemoteDiscoveryEngine classes, document:
       file:line, public methods, how it's cached (if at all), and the
       FULL list of importers (with file:line for each).
   - Determine: does astraeus/core/ingestion.py's version (Streamlit-
     cached) work correctly OUTSIDE a Streamlit context (from a script or
     pytest)? If the @st.cache_data wrapper means it silently misbehaves
     headless, that would explain why a separate astroquery-based version
     exists in astraeus/data/discovery.py rather than being redundant.
     State whether both are legitimately needed for different contexts or
     one is truly dead.

3. GIT HISTORY CHECK
   - Run `git log --oneline -- astraeus/ui/` and
     `git log --oneline -- astraeus/dashboard/` and compare recency. A
     path with no recent commits while another is active is a (weak)
     signal of which is maintained.

4. WRITE THE PROPOSAL
   - For each orphan candidate, state CONFIRMED DEAD (no live importer)
     or STILL LIVE (list its live importers), with confidence level.
   - For the RemoteDiscoveryEngine collision, state your recommended
     resolution:
       (a) both legitimately needed -> rename for clarity (e.g.
           StreamlitCachedArchive / AstroqueryArchive, or
           RemoteDiscoveryEngineUI / RemoteDiscoveryEngineHeadless), OR
       (b) one is truly dead -> deprecate it, keep the survivor's name.
     Do not pick (a) vs (b) by guessing — base it on the Phase 1.2
     headless-context finding.
   - If evidence is ambiguous for any item, say so explicitly and STOP
     on that item. Leave it untouched and flagged for the user.

============================================================
PHASE 2 — CLEAN UP (only for items Phase 1 resolved with confidence)
============================================================
1. For each CONFIRMED DEAD orphan:
   - Do NOT delete outright. Move it under a top-level `deprecated/`
     folder preserving internal structure (e.g.
     `deprecated/astraeus_ui_dashboard/dashboard.py`) and add a
     `DEPRECATED.md` next to it explaining why, when, and what (if
     anything) replaced it, linking back to
     reports/bucket1_orphan_investigation.md.
   - Update or remove the obsolete test import that referenced it
     (e.g. tests/test_chaos_integration_suite.py:158). If that test was
     specifically testing the dead module, mark the test
     @pytest.mark.skip with a reason referencing this report rather than
     deleting it — preserve test history.

2. For the RemoteDiscoveryEngine collision, apply the Phase 1 resolution:
   - If renaming: use a repo-wide find-and-replace with care, updating
     every importer (ui/pages/detective.py, tests/test_discovery.py, the
     stress scripts, MODULE_REFERENCE.md). Each rename is one commit.
   - If deprecating one: move it to deprecated/, fix the surviving one's
     importers if any pointed at the dead one.

3. Commit each deprecation / rename as its own commit with a clear
   message referencing the finding.

4. After EACH commit, run:
       python -m pytest tests/ -v
   If anything that passed in the Phase 0 baseline now fails, you removed
   or renamed something that was actually live — revert that specific
   commit immediately and correct the Phase 1 conclusion in the report.

============================================================
PHASE 3 — WRITE THE ARCHITECTURE DOC
============================================================
Create `docs/ARCHITECTURE.md` (the `docs/` dir may not exist yet — create
it). It must contain, in plain prose with an ASCII diagram:

1. The live launch path: `streamlit run app.py` -> sidebar nav
   (astraeus/dashboard/ui/layout.py) -> route.render_route ->
   ui/pages/{simulator,lab,detective,history,settings}.py, with the
   "Discover" tab rendered inline in app.py.
2. Which astraeus/dashboard/ modules are STILL shared libraries (layout,
   styles, components/chat, figures, simulation, settings) and which are
   now deprecated/removed per Phase 2.
3. The data layer: the (renamed) Streamlit-cached archive engine in
   astraeus/core/ingestion.py is the live UI path; the astroquery engine
   in astraeus/data/discovery.py is [whatever Phase 1 concluded].
4. The analysis pipeline call order inside detect_transit_candidate:
   detrend -> BLS -> geometric validation -> VettingEngine (U vs V shape)
   -> physical properties -> TTV. (Reference real file:line.)
5. A one-paragraph "if you're a new agent, read this first" summary.

============================================================
PHASE 4 — VERIFY & REPORT
============================================================
1. Run full test suite, save to reports/bucket1_posttest.txt. Pass count
   must be >= Phase 0 baseline.

2. Manually confirm (via static read, and interactively if possible):
       streamlit run app.py
   still launches and the basic pages route correctly. If interactive
   verification isn't possible in this environment, say so explicitly.

3. Write reports/bucket1_summary.md with:
   - Final resolution for each orphan and for the RemoteDiscoveryEngine
     collision (deprecated / renamed / left ambiguous for user decision)
   - Exact files moved/deprecated and renamed, with before/after paths
   - The new docs/ARCHITECTURE.md and what it documents
   - Test results before/after
   - Exact verification commands

============================================================
HARD CONSTRAINTS
============================================================
- Never delete files in this bucket — deprecate (move + document) only.
  Actual deletion is a separate, explicit, later decision for the user.
- Do not rename or modify astraeus/core/ingestion.py's or
  astraeus/data/discovery.py's actual FETCH LOGIC. This bucket only
  resolves WHICH path is used, renames for clarity if both survive, and
  deprecates the dead one. Logic changes are out of scope.
- Do not touch astraeus/analysis/ or astraeus/core/ physics/solver
  modules at all in this bucket.
- If Phase 1 is inconclusive for a given target, do not guess in Phase 2
  — leave that specific target untouched and clearly flagged.
```

### AGENT PROMPT END

---

## Bucket 2 — Vetting threshold hardening (remaining work)

**Why this matters:** A new `astraeus/analysis/vetting.py` `VettingEngine` already exists and is wired into `detect_transit_candidate` (U-shape vs V-shape χ² model comparison, replacing the old `v_shape > 0.85` magic check). **That part is done.** What remains, and what this bucket now scopes to, is the *other* hardcoded thresholds in `detection.py` and `geometric_validation.py` that still silently misclassify edge cases:

- `transit_depth_fraction < 0.03` → "Verified Planet Candidate" (`detection.py`, fixed % regardless of star)
- `best_snr <= 20.0` gating the V-shape / secondary-eclipse branches (twice in `detection.py`)
- `sec_depth < 0.0008` (800 ppm, fixed) → "Atmospheric Occultation Detected" — **the original misclassification bug this bucket exists to fix**: a genuinely real, hot, large planet around a hot star can produce real thermal occultation depths exceeding 800 ppm, which the current logic misclassifies as an eclipsing-binary signature.
- `secondary_eclipse_snr > 3.0` (`geometric_validation.py`) — fixed SNR cutoff for declaring a secondary eclipse
- `best_period < 1.5` days (`detection.py`) — ultra-short-period cutoff

### AGENT PROMPT START

```
You are hardening the remaining transit vetting thresholds in ASTRAEUS's
astraeus/analysis/detection.py and astraeus/analysis/geometric_validation.py.

ALREADY DONE (do not redo): a new astraeus/analysis/vetting.py VettingEngine
does U-shape vs V-shape chi-squared model comparison and is called from
detect_transit_candidate. The old single v_shape > 0.85 magic check is gone.

REMAINING FIXED THRESHOLDS TO HARDEN (confirmed present in this revision):
  - transit_depth_fraction < 0.03  -> "Verified Planet Candidate"
    (detection.py, inline literal)
  - best_snr <= 20.0  -> gates the V-shape and secondary-eclipse branches
    (detection.py, appears twice)
  - sec_depth < 0.0008  (800 ppm, FIXED) -> "Atmospheric Occultation
    Detected"  (detection.py)  *** this is the headline misclassification
    bug this bucket exists to fix ***
  - secondary_eclipse_snr > 3.0  -> declares a secondary eclipse detected
    (geometric_validation.py)
  - best_period < 1.5  -> ultra-short-period cutoff (detection.py)

The headline fix: make the secondary-eclipse threshold a function of
expected blackbody thermal emission given the star and planet's physical
properties, not the flat 800 ppm constant. A genuinely real, hot, large
planet around a hot star can produce real thermal occultation depths
exceeding 800 ppm; the current logic misclassifies that as an
eclipsing-binary signature.

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user.
2. Branch: `git checkout -b fix/vetting-threshold-hardening`
3. Run full test suite, save baseline:
       python -m pytest tests/ -v > reports/bucket2_pretest_baseline.txt 2>&1
   Specifically note results from tests/test_bulletproof_detector.py and
   any test exercising detection.py / geometric_validation.py / the new
   vetting.py — these are the ones you must not regress.
4. Read-only phase. No changes yet.

============================================================
PHASE 1 — DISCOVERY
============================================================
Produce reports/bucket2_threshold_audit.md covering:

1. Read astraeus/analysis/detection.py in full (it is ~150 lines). List
   every numeric literal threshold used in vetting decisions, with line
   numbers, and what decision it gates. Note specifically that
   detect_transit_candidate now calls VettingEngine.vet_transit_shape and
   branches on vetting_metrics['vetting_status'].

2. Read astraeus/analysis/vetting.py in full. Document its return dict
   keys (vetting_status, vetting_confidence, u_shape_chi2, v_shape_chi2,
   delta_chi2_u, delta_chi2_v) and its own threshold param
   (vet_transit_shape's `threshold` default 0.0) — flag whether that
   default is itself an unexamined magic number.

3. Read astraeus/analysis/geometric_validation.py in full. List every
   numeric literal threshold (secondary_eclipse_snr > 3.0, the 0.10 in
   the depth_threshold, the 0.05 / 0.15 phase windows, the >= 8 and
   >= 3 sample-count floors), with line numbers.

4. Read astraeus/analysis/physical_properties.py's
   PhysicalPropertiesEngine.derive() to confirm what physical quantities
   are already available at the point vetting happens — specifically
   whether equilibrium_temp_k and st_teff are computed/available BEFORE
   or AFTER the vetting decision in detection.py's current pipeline
   order. As of this revision, PhysicalPropertiesEngine.derive() is
   called AFTER the vetting branches in detect_transit_candidate — so to
   use a physically-grounded secondary-eclipse threshold you will need
   either to (a) reorder so physical properties are derived before
   vetting, or (b) compute a lightweight equilibrium-temperature
   estimate earlier, specifically for the secondary-eclipse check. State
   which you'll do and why; do not bury the choice.

5. For each fixed threshold found, classify it as one of:
   (a) PHYSICALLY DERIVABLE — should become a function of star/planet
       properties rather than a constant. The 800 ppm secondary-eclipse
       cutoff is the clearest: expected thermal occultation depth scales
       roughly as (R_p/R_star)^2 * (T_planet/T_star)^4 via blackbody flux
       ratio. Derive the actual formula; do not approximate carelessly.
   (b) REASONABLE FIXED THRESHOLD — a defensible domain convention (e.g.
       depth < 3% to separate planet candidates from clearly stellar-
       scale signals) but should be named, documented, and configurable
       rather than an inline magic number.
   (c) UNCERTAIN — flag for the user; do not change without their input.

6. Check astraeus/core/constants.py for the existing named-constant
   convention (there are already Kepler-solver constants there). Match
   that style exactly for any (b) thresholds.

============================================================
PHASE 2 — IMPLEMENT
============================================================
Only proceed for thresholds classified (a) or (b) in Phase 1.

FOR CATEGORY (a) — physically derivable thresholds (the 800 ppm one):
1. Implement the derivation as a small, separately-testable function
   (e.g. expected_occultation_depth_ppm(planet_radius_earth,
   stellar_radius, planet_equilibrium_temp_k, stellar_teff_k) -> float)
   in physical_properties.py or a new clearly-named module if that fits
   better. Check existing module boundaries before deciding where it goes.
2. Use it to REPLACE the fixed 0.0008 threshold in detection.py's
   secondary-eclipse branch, but keep a sane fallback constant for cases
   where the required physical inputs are missing (e.g. equilibrium temp
   couldn't be computed). Log a warning when the fallback is used so it
   is visible that the physically-derived threshold wasn't possible.
3. Do not silently change behavior. Add fields to the vetting result dict
   so downstream consumers can see which mode ran, e.g.
     "secondary_eclipse_threshold_mode": "physical" | "fallback_fixed",
     "secondary_eclipse_threshold_ppm": <the actual value used>
4. If you had to reorder the pipeline (per Phase 1.4), make that
   reordering its OWN commit with a message like "refactor(detection):
   derive physical properties before vetting so the secondary-eclipse
   threshold can be physically grounded". Do not bundle it inside the
   threshold-logic commit.

FOR CATEGORY (b) — reasonable-but-magic-number thresholds:
1. Extract each into a named constant in astraeus/core/constants.py
   matching the existing style, e.g.
       VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION = 0.03
       VETTING_VSHAPE_LOW_SNR_GATE = 20.0
       VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD = 3.0
       VETTING_ULTRA_SHORT_PERIOD_DAYS = 1.5
   with a comment explaining the convention/reasoning.
2. Replace the inline literals in detection.py / geometric_validation.py
   with references to these named constants.
3. Do NOT change the actual threshold VALUES in this category — only
   their representation. Re-deriving a convention's value is out of scope.

Commit each threshold's fix separately (one commit per threshold or
tightly related group), referencing the audit finding it addresses.

After EVERY commit, run:
    python -m pytest tests/test_bulletproof_detector.py -v
and the broader suite if that passes. Any regression vs the Phase 0
baseline is a stop condition — fix or revert immediately.

============================================================
PHASE 3 — TEST THE NEW PHYSICAL THRESHOLD LOGIC SPECIFICALLY
============================================================
1. Write new test cases (in tests/, following test_bulletproof_detector.py
   style) that specifically probe the case this bucket exists to fix:
   construct a synthetic hot, large planet scenario (high equilibrium
   temperature, larger radius) where the OLD fixed 800 ppm threshold
   would have misclassified (occultation depth > 800 ppm but the signal
   is a genuine planet, not an eclipsing binary), and confirm the NEW
   physically-derived threshold correctly avoids that misclassification.
2. Also test the fallback path: confirm that when physical properties
   are unavailable, the fallback fixed threshold is used AND the result
   dict flags secondary_eclipse_threshold_mode == "fallback_fixed".
3. Run the full suite one more time, save to reports/bucket2_posttest.txt.
   Pass count must be >= baseline, AND the new tests must pass.

============================================================
PHASE 4 — REPORT
============================================================
Write reports/bucket2_summary.md with:
- Each threshold found, its classification (a/b/c), and what was done
- The actual physical derivation used for the secondary-eclipse
  threshold, with the formula shown explicitly
- Whether the pipeline was reordered and why (the explicit commit)
- New test cases added and what specific misclassification they guard
  against
- Any threshold left as category (c) for the user to decide
- Test results before/after
- Verification commands

============================================================
HARD CONSTRAINTS
============================================================
- Do not change the vetting STATUS LABELS ("Verified Planet Candidate",
  "Eclipsing Binary Detected", etc.) or add new ones — this bucket
  changes how thresholds are COMPUTED, not the classification scheme.
- Do not regress the existing VettingEngine behavior in vetting.py.
  If you find a bug in it, document it separately and propose it as a
  follow-up; do not fix it inline in this bucket.
- Do not touch bls_search.py, fitting.py, error_analysis.py, or
  ttv_analysis.py in this bucket — scope is strictly detection.py,
  geometric_validation.py, constants.py, and (if needed for the physical
  derivation) physical_properties.py or one new clearly-named module.
- If implementing the physical derivation requires reordering the
  pipeline, make that reordering explicit and its own commit — never
  bury a pipeline-order change inside an unrelated commit.
```

### AGENT PROMPT END

---

## Bucket 3 — Injection-recovery completeness sweep

**Why this matters:** `astraeus/simulation/synthetic.py` already has `run_injection_recovery(scenario, n_injections)`, but it operates on a single scenario configuration. The high-value version — a publishable completeness map that empirically validates detection thresholds — runs it across a grid of periods, depths/radius-ratios, and SNRs, caches the results (since this is expensive), and produces both a data artifact and a plot. This bucket extends the existing primitive rather than replacing it.

### AGENT PROMPT START

```
You are extending ASTRAEUS's existing injection-recovery testing into a
systematic completeness sweep. The primitive already exists at
astraeus/simulation/synthetic.py:
  class SyntheticTransitScenario (fields include duration, period,
    eccentricity, radius_ratio, snr, samples, seed, stellar_radius,
    semi_major_axis, inclination)
  class LightCurveSeries
  generate_synthetic_transit_series()
  run_injection_recovery(scenario, n_injections) -> injects a synthetic
    planet and runs BLS to recover it, reporting recovery rate / period
    error / depth error for ONE scenario configuration.

YOUR JOB: build a new, separate sweep layer on top of this existing
primitive — do not rewrite or replace run_injection_recovery() itself
unless Phase 1 discovery finds a concrete blocking bug in it.

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user.
2. Branch: `git checkout -b feature/completeness-sweep`
3. Run full test suite, save baseline:
       python -m pytest tests/ -v > reports/bucket3_pretest_baseline.txt 2>&1
   Pay particular attention to tests/test_synthetic_simulation.py.
4. Read-only phase. No changes yet.

============================================================
PHASE 1 — DISCOVERY
============================================================
Produce reports/bucket3_sweep_design.md covering:

1. Read astraeus/simulation/synthetic.py in full. Document the exact
   signature and behavior of run_injection_recovery,
   SyntheticTransitScenario (all fields listed above), and
   LightCurveSeries. Confirm what "recovery" means precisely in the
   existing implementation (does it consider recovery successful if BLS
   finds the period within some tolerance? what tolerance?).

2. Read tests/test_synthetic_simulation.py to see what's already tested,
   so the new sweep tests don't duplicate existing coverage.

3. CRITICAL: check whether run_injection_recovery currently calls the
   FULL detection pipeline (detect_transit_candidate, including vetting)
   or just the raw BLS search. A completeness map measuring "can BLS
   find the period" is different from "does the full pipeline correctly
   classify it as a Verified Planet Candidate." Determine which exists
   today, and design the sweep to measure BOTH explicitly as separate,
   clearly-labeled metrics if currently only one is measured.

4. Estimate compute cost: time a single run_injection_recovery call
   with a representative n_injections. A naive full grid (e.g. 20
   periods x 20 depths x 5 SNR = 2000 cells) could be very expensive.
   Document the actual per-cell cost found, and use it to inform a
   realistic default grid resolution rather than picking an arbitrary one.

5. Check astraeus/analysis/logging.py's ExperimentLedger and any
   generate_dataset_hash — the sweep results should be cacheable using a
   pattern consistent with the rest of the codebase, not a new ad-hoc
   caching mechanism.

6. Write a design proposal: grid dimensions and ranges, default
   resolution given the cost estimate, output data format, and where
   outputs should live (propose outputs/completeness_sweeps/, consistent
   with the existing outputs/kepler90_blind_search/ pattern).

============================================================
PHASE 2 — IMPLEMENT
============================================================
1. Create astraeus/simulation/completeness.py (new file) with:
   a. A configuration dataclass CompletenessSweepConfig with fields for
      period range/count, radius_ratio (or depth) range/count, SNR
      range/count, n_injections per cell, random seed, and a flag
      use_full_pipeline: bool to select between raw-BLS-only recovery
      and full detect_transit_candidate-based recovery (per Phase 1 #3 —
      implement support for measuring both, since they answer different
      questions).
   b. A function run_completeness_sweep(config) -> CompletenessSweepResult
      that iterates the grid, calls the EXISTING run_injection_recovery
      (or detect_transit_candidate per the use_full_pipeline flag) per
      cell, and aggregates results into a 2D (or 3D if SNR swept too)
      array of recovery rates plus period/depth error stats per cell.
   c. Make this resumable/cacheable: before running a cell, check if a
      cached result for that exact (config_hash, period, depth, snr,
      n_injections, seed) combination exists on disk and skip
      recomputation if so. Write results INCREMENTALLY, not only at the
      end — a crash halfway through must not lose all progress.
   d. Add progress reporting via a callback parameter matching the
      progress_callback pattern already used in error_analysis.py's
      run_mcmc, for consistency.

2. Add a plotting function to astraeus/visualization/plots.py, following
   the existing style of plot_synthetic_validation and plot_corner
   (matplotlib, Agg backend, returns Path, saves to file) — e.g.
   plot_completeness_map(sweep_result, output_path) -> Path rendering a
   2D heatmap of recovery rate vs period and depth/radius-ratio.

3. Add completeness output to astraeus/analysis/reporting.py's
   generate_academic_report OR a clearly separate new function — check
   which fits better given the existing _validate_schema and payload
   structure; do not force the existing schema if it doesn't fit
   completeness data.

4. Commit incrementally: config dataclass -> sweep runner -> caching ->
   plotting -> reporting integration, each as a separate commit.

5. After each commit, run tests/test_synthetic_simulation.py to confirm
   nothing in the existing injection-recovery primitive was broken.

============================================================
PHASE 3 — TEST
============================================================
1. Write tests/test_completeness_sweep.py covering:
   - A small fast sweep (tiny grid, e.g. 2x2 periods/depths, low
     n_injections) runs to completion and returns the expected shape.
   - Caching: running the same small sweep twice, confirm the second run
     uses cached cells (timing difference or explicit cache-hit counter).
   - Resumability: simulate an interrupted sweep (run partial, then
     resume) and confirm completed cells aren't redone and the final
     result is identical to running the full sweep in one pass.
   - The use_full_pipeline flag actually produces different (correctly
     different) recovery semantics in the two modes.
2. Run full suite, save to reports/bucket3_posttest.txt. Pass count must
   be >= baseline, new tests must pass.
3. Actually run ONE real small-scale fast completeness sweep end to end
   and confirm a plot file and report-ready output are produced — don't
   just rely on unit tests with mocked internals; do one genuine small
   integration run and inspect the output artifact yourself.

============================================================
PHASE 4 — REPORT
============================================================
Write reports/bucket3_summary.md with:
- Final grid design and why (referencing the cost estimate)
- Per-cell cost measured, and total sweep cost for the default config
- Caching/resumability behavior confirmed
- Sample output (reference the actual plot/data file produced)
- How this wires into reporting.py and how a future UI panel could call it
- Verification commands

============================================================
HARD CONSTRAINTS
============================================================
- Do not modify run_injection_recovery()'s existing signature or behavior
  unless Phase 1 found a concrete bug blocking the sweep — if so, fix the
  minimal bug and document it explicitly and separately.
- Do not wire this into the Streamlit UI in this bucket — that's future
  work once Buckets 0 and 1 are stable. This bucket produces a callable
  Python API and script-level usage only.
- Keep default sweep resolution conservative (smaller, fast default grid
  with an easy way to configure a larger one) — do not ship a default
  that takes hours to run.
```

### AGENT PROMPT END

---

## Bucket 4 — N-body × TTV cross-validation

**Why this matters:** `astraeus/analysis/ttv_analysis.py`'s `TTVAnalyzer.calculate()` reports timing residuals (`ttv_residual_min`) per transit epoch, but has no way to say whether those residuals are consistent with a real gravitationally-perturbing companion or are just noise/systematics. `astraeus/core/nbody_solver.py` is a real, tested symplectic integrator that can simulate exactly this. This bucket connects them: given a detected TTV signal, search for companion mass/period combinations that could plausibly produce it, and check those candidates for N-body stability, giving a genuine physical plausibility check instead of a bare residual number.

### AGENT PROMPT START

```
You are wiring astraeus/core/nbody_solver.py into
astraeus/analysis/ttv_analysis.py so that detected Transit Timing
Variations get a physical plausibility check against real N-body
dynamics, instead of being reported as bare timing residuals with no
interpretation of whether they're physically explicable.

PRIMITIVES (confirmed present in this revision):
  astraeus/core/nbody_solver.py exports:
    class PlanetParams (line ~60)
    class StabilityResult (line ~77)
    run_stability_analysis(...) (line ~280)
    run_stability_integration(...) (line ~383)
    estimate_mass_from_radius(radius_earth) -> float  (line ~601,
      Weiss-Marcy 2014 scaling)
  astraeus/analysis/ttv_analysis.py exports:
    TTVAnalyzer.calculate(...)

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user.
2. Branch: `git checkout -b feature/nbody-ttv-cross-validation`
3. Run full test suite, save baseline:
       python -m pytest tests/ -v > reports/bucket4_pretest_baseline.txt 2>&1
   Note results from tests/test_nbody_solver.py specifically.
4. Read-only phase. No changes yet.

============================================================
PHASE 1 — DISCOVERY
============================================================
Produce reports/bucket4_nbody_ttv_design.md covering:

1. Read astraeus/analysis/ttv_analysis.py's TTVAnalyzer.calculate() in
   full. Confirm exactly what it returns (per existing docs: a list of
   {epoch, ttv_residual_min}). Check what information about the KNOWN/
   DETECTED planet (period, t0, depth -> radius) is available alongside
   the TTV result at the point this would be called in the pipeline
   (detection.py calls TTVAnalyzer.calculate at the end of
   detect_transit_candidate, with best_period/transit_time/duration/
   transit_depth_fraction all in scope).

2. Read astraeus/core/nbody_solver.py in full. Confirm the exact
   signatures of run_stability_analysis, run_stability_integration,
   PlanetParams, StabilityResult, and especially
   estimate_mass_from_radius — this converts a detected planet's radius
   into an approximate mass for N-body purposes.

3. Think through the actual physics task carefully and write your
   reasoning into the report:
   - Given a TTV residual amplitude and an estimated perturbing period,
     TTV periodicity itself often hints at the perturber's period via
     the resonance/super-period relationship. Check whether existing
     code already extracts a TTV periodicity; if not, add a small
     focused function (e.g. estimate_ttv_periodicity(epochs,
     ttv_residuals_min) -> float | None, reusing the Lomb-Scargle
     approach already used in astraeus/analysis/detrending.py's
     estimate_stellar_rotation for consistency — do NOT invent a new
     periodogram approach).
   - This is fundamentally an inverse/search problem: you don't know
     the perturbing planet's mass or period directly. Design a bounded
     grid search: for a range of hypothetical companion mass (using
     estimate_mass_from_radius bounds for plausible planet sizes,
     sub-Earth to super-Jupiter) and period (informed by the extracted
     TTV periodicity if available, else a broad range relative to the
     known planet's period), run run_stability_analysis for each
     candidate and check:
       (a) is the configuration N-body STABLE over a reasonable
           integration time (not ejecting/colliding)?
       (b) does it produce a TTV amplitude on the KNOWN planet roughly
           consistent with what was observed? (run_stability_analysis
           returns stability diagnostics, not directly a predicted TTV
           amplitude — you will likely need to derive an approximate TTV
           signal from the integration by tracking the known planet's
           transit timing, OR use a simpler analytic TTV-amplitude
           approximation as a fast pre-filter before the expensive full
           N-body run. Investigate which is more tractable and propose
           the cheaper option as a first-pass filter with full N-body
           reserved for the most promising candidates only.)
   - Be explicit that this is a degenerate inverse problem — multiple
     companion configs can produce similar TTV signatures. Output must
     be framed as "configurations consistent with the observed TTV and
     dynamically stable" (a plausibility range), NOT "the companion has
     been determined to have mass X and period Y." Design the output
     data structure and any report language around this explicitly.

4. Check tests/test_nbody_solver.py for the existing testing convention.

5. Write the final design: new module name/location (propose
   astraeus/analysis/ttv_nbody_validation.py), function signatures, grid
   bounds, cheap-filter-then-expensive-confirm strategy, and exactly
   what gets returned.

============================================================
PHASE 2 — IMPLEMENT
============================================================
1. If Phase 1 determined a TTV-periodicity extraction step is needed and
   doesn't exist, implement it first as a small separately-testable
   function. Test in isolation before building anything on top of it.

2. Implement the cheap pre-filter (analytic or simplified TTV-amplitude
   estimate) as its own function, tested against known-answer cases if a
   standard analytic approximation is used (e.g. a textbook two-planet
   near-resonance case from the literature).

3. Implement the full grid search function that:
   - Takes the known planet's parameters + the TTV residual series.
   - Runs the cheap pre-filter across the configured grid.
   - Selects only the top N candidates (configurable, default small
     e.g. 5-10) for full run_stability_analysis confirmation.
   - Returns a result object listing each confirmed-stable candidate
     (companion mass estimate, companion period estimate, stability
     diagnostics from StabilityResult) ranked by TTV-amplitude match,
     explicitly framed as a plausibility set.

4. Add a clear "no plausible companion found" / "TTV consistent with
   noise, no significant periodicity detected" output path — this method
   must be able to return "nothing found" honestly rather than always
   forcing a best-guess candidate.

5. Commit incrementally: periodicity extraction -> cheap filter -> grid
   search -> full integration test, each as its own commit.

6. After each commit, run tests/test_nbody_solver.py to confirm no
   regression in the underlying solver.

============================================================
PHASE 3 — TEST
============================================================
1. Write tests/test_ttv_nbody_validation.py covering:
   - A synthetic case: use nbody_solver's own run_stability_integration
     to generate a KNOWN two-planet configuration, derive what TTV signal
     that would produce on the inner planet, then attempt recovery
     (validates the whole loop end-to-end: known truth -> synthetic TTV
     -> recovery attempt -> does the recovered candidate resemble the
     known truth at least approximately, in mass/period order of
     magnitude).
   - A no-signal case: flat/noise-only TTV residuals correctly return
     "no plausible companion found" rather than a false positive.
   - An unstable-candidate rejection case: confirm dynamically-unstable
     configurations (even if their TTV amplitude matches numerically)
     are excluded from the final result.
2. Run the full suite, save to reports/bucket4_posttest.txt. Pass count
   >= baseline, new tests pass.
3. Document the known-truth recovery test's actual quantitative result
   in the report (how close was the recovered mass/period estimate to
   the synthetic ground truth) — be honest about precision/accuracy,
   since perfect recovery should not be expected or claimed.

============================================================
PHASE 4 — REPORT
============================================================
Write reports/bucket4_summary.md with:
- Final architecture: periodicity extraction, cheap filter, full N-body
  confirmation, in that order, with the actual functions/files
- The known-truth validation test's quantitative result, stated honestly
- Compute cost of a typical run (cheap filter across the grid + N full
  N-body confirmations)
- Explicit language/framing recommendations for how this should be
  presented in UI/reports later (plausibility set, not a determined
  answer) — a hard scientific-honesty requirement, not a style
  preference
- Verification commands

============================================================
HARD CONSTRAINTS
============================================================
- Do not modify nbody_solver.py's existing tested functions
  (run_stability_analysis, run_stability_integration,
  check_system_stability, estimate_mass_from_radius) — only call them.
  If you find a genuine bug, document it separately and propose it as a
  follow-up; do not fix it inline.
- Do not modify TTVAnalyzer.calculate()'s existing return format — add
  new functionality alongside it, don't change what it returns, since
  other code depends on the current shape.
- Never present the output as a determined/confirmed companion
  detection. The result structure and any accompanying text must make
  clear this is a plausibility/consistency check, not a detection claim.
- Do not wire this into the Streamlit UI in this bucket — Python API
  and tests only, consistent with Bucket 3's scope boundary.
```

### AGENT PROMPT END

---

## Bucket 5 — Test suite CI-readiness

**Why this is last:** this bucket should test the final state of everything done in Buckets 0-4, not a moving target. As of this revision: **no CI exists** (`.github/` contains only `copilot-instructions.md`, no `workflows/` directory). The diagnostic/stress scripts already live in `tests/` (not in the repo root as v1 assumed) — `pipeline_stress_test.py`, `global_matrix_stress_test.py`, `solid_matrix_diagnostic.py`, `system_flight_bench.py`, `debug_metadata_network.py`, `trace_download_deadlock.py` — but they are not pytest-idiomatic, are not marker-tagged, and several make live network calls at import/collection time (which likely explains the collection-hang symptom seen in `pytest_log.txt`). Additionally `requirements.txt` is incomplete: it pins 10 runtime deps but the codebase imports `astroquery`, `batman-package`, `statsmodels`, `pytest`, `kaleido` (pinned but as runtime), etc. — a fresh clone will not run.

This bucket: converts the diagnostic scripts to proper pytest cases, **creates** the missing CI workflow, and fixes `requirements.txt`.

### AGENT PROMPT START

```
You are converting ASTRAEUS's diagnostic/stress scripts (already located
in tests/, not the repo root) into proper pytest-discoverable tests,
fixing requirements.txt, and CREATING a CI workflow that does not exist
today. This is the final step after Buckets 0-4 are complete and merged.

CONFIRMED STATE OF THE TEST LAYER AS OF THIS REVISION:
  tests/ contains these NON-pytest-idiomatic diagnostic scripts:
    pipeline_stress_test.py
    global_matrix_stress_test.py
    solid_matrix_diagnostic.py
    system_flight_bench.py
    debug_metadata_network.py
    trace_download_deadlock.py
  Several of these make live network calls (to the NASA Exoplanet
  Archive / MAST) and are likely the cause of the pytest collection
  hang observed in pytest_log.txt ("collecting ...").
  tests/ ALSO has proper pytest files already (test_*.py) — do not
  touch those beyond verifying they still pass.

CONFIRMED STATE OF DEPS:
  requirements.txt pins 10 runtime deps but is missing imports the
  codebase actually uses (astroquery, statsmodels, batman, pytest, etc.).
  No pyproject.toml / setup.cfg marker registration exists.

CONFIRMED STATE OF CI:
  None. .github/ has only copilot-instructions.md. You will CREATE the
  workflow in Phase 3.

MANUAL SCRIPTS STILL IN THE REPO ROOT (separate concern, partly handled
by Bucket 7, but you must not convert THESE in this bucket):
  test_engine.py, test_orchestrator.py, test_ingest.py, test_fetch.py,
  test_nasa.py, run_test.py — investigate their purpose, but if they
  overlap with tests/ files, flag them for Bucket 7 rather than
  converting them here. This bucket's conversion scope is the
  tests/ diagnostic scripts listed above.

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user.
2. Branch: `git checkout -b chore/ci-readiness`
3. Run the full pytest suite as-is, save baseline:
       python -m pytest tests/ -v > reports/bucket5_pretest_baseline.txt 2>&1
   If collection HANGS (as observed in prior runs at "collecting ..."),
   identify WHICH file is hanging by collecting one file at a time:
       python -m pytest tests/<file>.py --collect-only -q
   Record the hang culprit explicitly — it is almost certainly one of the
   diagnostic scripts doing network I/O at import time. Do NOT proceed
   past discovery without knowing the culprit.
4. Read-only phase otherwise. No changes yet.

============================================================
PHASE 1 — DISCOVERY
============================================================
Produce reports/bucket5_ci_audit.md covering:

1. For each diagnostic script in tests/, read its content and document:
   - What does it actually test/exercise?
   - Does it use assert statements, or just print output for a human to
     eyeball? (A script that prints "Result: 42" with no assertion is
     not actually testing anything automatable; converting it naively to
     pytest would create a test that always passes regardless of
     correctness.)
   - Does it require network access? (Several do — they hit the NASA
     Exoplanet Archive / MAST.) If so, propose @pytest.mark.network so
     these are excludable from a fast/offline run
     (`pytest -m "not network"`) but still includable in a full nightly
     run, rather than forcing every CI run to require network.
   - Does it perform network I/O at IMPORT time (module top-level), not
     just inside functions? That is what causes collection hangs. This
     MUST be moved inside a test function or guarded so pytest can
     collect the file without triggering network calls.

2. Check whether any CI config already exists (it does not, but confirm:
   .github/workflows/, .gitlab-ci.yml, Jenkinsfile, azure-pipelines.yml,
   circle.yml). If none, note Phase 3 will create one.

3. Check pytest config (pytest.ini, pyproject.toml [tool.pytest],
   setup.cfg) for marker registration — none exists today, so new
   markers (@pytest.mark.network, @pytest.mark.slow) must be registered
   or they'll emit warnings.

4. Produce the COMPLETE list of importable third-party modules the
   codebase actually uses (grep for `import X` / `from X import`), then
   diff against requirements.txt. Document every missing dep and whether
   it's runtime, test-only, or optional. Common likely-missing ones to
   verify: astroquery, batman-package, statsmodels, pytest, pytest-mock.

============================================================
PHASE 2 — CONVERT
============================================================
For each diagnostic script classified as a genuine assertion-worthy test:

1. Move its actual test logic into the tests/ directory as a proper
   pytest file, OR consolidate into an existing tests/test_*.py if one
   already covers the same subsystem (check for overlap first; do not
   fragment coverage across two files for the same subsystem).

2. Convert print-and-eyeball checks into actual assert statements based
   on what the script's output suggests the correct result should be. If
   this isn't clear from the script alone, say so explicitly rather than
   inventing an assertion that might not reflect intended behavior. Flag
   these cases for the user.

3. Apply @pytest.mark.network to any test requiring live network access,
   and register the marker. Ensure these are excludable.

4. CRITICAL for the collection-hang fix: ensure NO module does network
   I/O at import time. Move any such calls inside test functions (which
   only run when the test runs, not at collection). This alone should
   fix the "collecting ..." hang.

5. For scripts classified as one-off diagnostics (not tests), move them
   to a clearly-named non-test location (e.g. tools/diagnostics/) and do
   NOT force them into pytest — leave them as runnable scripts with a
   comment explaining their original purpose, referencing the audit.

6. Delete the original diagnostic script from tests/ ONLY after its
   logic has been successfully relocated and verified working — never
   delete-then-port, always port-then-verify-then-delete, as two
   separate commits (port, then delete).

7. Commit incrementally, one script's conversion per commit, each
   referencing the audit finding.

============================================================
PHASE 3 — DEPS & CI CONFIG
============================================================
1. Fix requirements.txt:
   - Split into runtime requirements (requirements.txt) and test/dev
     requirements (requirements-dev.txt) — or use extras in
     pyproject.toml if you also add one. Match the existing convention;
     if none exists, requirements.txt + requirements-dev.txt is the
     least-surprise choice.
   - Add every missing dep identified in Phase 1.4. Pin to versions
     compatible with the existing pins (numpy==2.2.6, etc.).
   - Verify the install actually works on a clean venv if possible; if
     you can't, state that explicitly.

2. Register pytest markers in a pytest config (pytest.ini or
   pyproject.toml [tool.pytest.ini_options]):
       markers:
         network: tests requiring live network access
         slow: long-running tests (stress/bench)

3. Create .github/workflows/tests.yml (GitHub Actions — no other CI
   platform is in use in this repo) that:
   - Installs deps from requirements.txt (and requirements-dev.txt for
     the test job).
   - Runs `pytest -m "not network and not slow"` as the default fast
     gate job on every push and PR.
   - Adds a separate, non-blocking (continue-on-error or scheduled)
     full-suite job including network tests, clearly labeled.
   - Targets a Python version matching the repo (3.12 per
     pytest_log.txt).
   - Cache pip wheels for speed.

4. Validate the workflow YAML syntactically. If a local validator
   (actionlint, yamllint) is available, run it; otherwise paste the
   schema check manually and state whether you validated locally.

============================================================
PHASE 4 — VERIFY & REPORT
============================================================
1. Run the full pytest suite one final time:
       python -m pytest tests/ -v > reports/bucket5_posttest.txt 2>&1
   And the fast/CI-equivalent subset:
       python -m pytest tests/ -m "not network and not slow" -v \
         > reports/bucket5_posttest_fast.txt 2>&1
   Confirm collection completes (no more "collecting ..." hang) and the
   new total discovered test count >= old pytest count + converted
   scripts.

2. Write reports/bucket5_summary.md with:
   - The collection-hang root cause and the fix
   - Disposition of every diagnostic script (converted / moved to tools
     / left as-is with reasoning)
   - The requirements.txt / requirements-dev.txt split and what was
     added
   - The CI config and exactly what each job runs
   - Before/after test counts
   - Any script where assertion criteria were unclear and need user
     confirmation
   - Verification commands, including how to run fast vs full locally

============================================================
HARD CONSTRAINTS
============================================================
- Never invent a passing assertion for a script whose correct expected
  behavior is genuinely unclear from reading it — flag it for the user.
  A test that always passes regardless of correctness is worse than no
  test, since it creates false confidence.
- Do not delete a diagnostic script until its logic is confirmed working
  in its new pytest location (port, verify, then delete, as separate
  commits).
- Do not change the actual behavior of any module under test — this
  bucket only changes how existing checks are organized and run, plus
  the CI/deps plumbing.
- Do not convert the repo-root manual scripts (test_engine.py etc.) in
  this bucket — those are Bucket 7's scope. Flag them only.
```

### AGENT PROMPT END

---

## Bucket 6 — End-to-end smoke test (recommended, do right after Bucket 0)

**Why this matters:** There is no single command today that answers "is the whole pipeline still healthy after a change?" The suite is organized by module (physics, transit model, MCMC, etc.) but has no fast end-to-end smoke test that exercises target ingestion → detection → vetting → physical properties → a basic report on a known synthetic target in under a minute or two. Given the Streamlit-layer bugs that don't show up in standalone module tests, this is exactly the safety net that would have caught the original problem earlier and will catch the next one.

**Position in the order:** after Bucket 0 (so it uses the now-fixed UI/state layer) and before Bucket 5 (so Bucket 5 can wire it into CI as the fastest-feedback job). Small enough that it does not need the full multi-phase prompt treatment — the global ground rules (branch, baseline test run, written report) apply.

### AGENT PROMPT START

```
You are adding ONE fast end-to-end smoke test to ASTRAEUS that exercises
the full analysis pipeline on a known synthetic target, so any future
regression in the pipeline (not just in an individual module) is caught
in well under a minute.

DESIGN GOAL:
  - Build a synthetic transit time series with KNOWN injected parameters
    (use astraeus/simulation/synthetic.py's
     generate_synthetic_transit_series / SyntheticTransitScenario so the
    ground truth is exact and reproducible).
  - Run it through detect_transit_candidate (the real pipeline entry
    point in astraeus/analysis/detection.py).
  - Assert the recovered period, depth, and vetting status are within
    sane tolerances of the injected truth.
  - Optionally assert a basic reporting call
    (generate_academic_report on a tiny payload) does not crash.
  - Total wall time under ~60 seconds on a normal laptop, so it can be
    the fastest CI gate.

============================================================
STEPS
============================================================
1. Branch: `git checkout -b test/e2e-smoke`
2. Baseline: `python -m pytest tests/ -v > reports/bucket6_pretest_baseline.txt 2>&1`
3. Create tests/test_pipeline_smoke.py with ONE test function
   (test_full_pipeline_recovers_synthetic_planet or similar):
   - Construct a synthetic single-planet transit series with known
     period / depth / duration.
   - Call detect_transit_candidate on it.
   - Assert: period recovered within e.g. 1%; depth within a factor of 2
     (synthetic noise makes tighter claims fragile); vetting_status is
     one of the planet-candidate labels (starts with "Verified Planet
     Candidate"), NOT an eclipsing-binary label.
   - Assert the result dict contains the expected keys
     (period_days, transit_depth, vetting_status, ttv_data, ...).
4. Time the test. If it exceeds ~60s, reduce n_injections / samples in
   the synthetic scenario — fast feedback is the whole point.
5. Mark it @pytest.mark.smoke (registered by Bucket 5's marker config,
   or register it yourself if Bucket 5 isn't done yet).
6. Run the full suite, confirm the new test passes and nothing regressed.
7. Write reports/bucket6_summary.md: the injected truth, the recovered
   values, the tolerances chosen and why, the wall time, and the exact
   command to run just this test
   (`pytest tests/test_pipeline_smoke.py -m smoke -v`).

============================================================
HARD CONSTRAINTS
============================================================
- Do not modify the pipeline code itself. If the smoke test reveals a
  real bug, document it and propose a fix as a follow-up — do not fix it
  inline in this bucket.
- Do not make this test require network. It must run fully offline on
  synthetic data.
- Keep it ONE test function (or a tiny handful at most). This is a smoke
  test, not a coverage expansion.
```

### AGENT PROMPT END

---

## Bucket 7 — Root-directory hygiene (low-risk, MVP-polish)

**Why this matters:** The repo root currently mixes the real application (`app.py`, `astraeus/`, `tests/`, `ui/`, `runs/`) with substantial scratch, debug, and duplicate artifacts that make the project look like a workbench rather than a product:

- `extracted_output.txt` (3.3 MB) and `extracted_utf8.txt` (1.6 MB) — large extraction dumps.
- `scratch_batman.py`, `test_exoplanet_ui_debug.py`, `ultimate_stress_test.py` (72 KB), `run_my_tests.py`, `run_pipeline_test.py`, `extract.py`, `find_cycles.py`, `init_project.py` — ad-hoc scripts.
- `final_payload.json`, `experiments.json` (root-level duplicate of `logs/experiments.json`).
- `test.html`, `test3d.html` — ad-hoc HTML probes.
- `pytest_log.txt`, `pytest_output.txt`, `pytest_pipeline.log`, `err.log`, `err2.log`, `test_orchestrator_log.txt` — log dumps.
- The two `ui/`-named directories (`ui/` live at root, `astraeus/ui/` dead per Bucket 1) — only resolved by Bucket 1, not here.

None of this is dangerous, but for an MVP freeze it's noise that hides the real entry points and bloats the repo. This bucket relocates it cleanly without deleting anything.

### AGENT PROMPT START

```
You are cleaning up the ASTRAEUS repo root so the project reads as a
product, not a scratch workbench. NOTHING IS DELETED — everything is
relocated to clearly-named folders and gitignored where appropriate.

============================================================
PHASE 0 — SAFETY SETUP
============================================================
1. Confirm clean git working tree. If not, stop and ask the user.
2. Branch: `git checkout -b chore/root-hygiene`
3. This bucket does not touch application code, so a test baseline is
   still useful but not safety-critical. Save it anyway:
       python -m pytest tests/ -v > reports/bucket7_pretest_baseline.txt 2>&1

============================================================
PHASE 1 — DISCOVERY (read-only)
============================================================
Produce reports/bucket7_hygiene_audit.md that, for every non-essential
file in the repo root, records:
  - file name and size
  - what it appears to be (scratch script, log dump, data extract,
    duplicate, ad-hoc probe)
  - whether anything in the live codebase (app.py, astraeus/, ui/,
    tests/, runs/) imports or reads it — grep to confirm
  - recommended disposition:
      (a) move to scratch/  (ad-hoc scripts kept for reference)
      (b) move to tools/diagnostics/  (reusable diagnostic scripts)
      (c) move to logs/ or outputs/  (log/data dumps, if useful)
      (d) add to .gitignore AND remove from the repo  (regenerable
          artifacts like *.log, pytest_output.txt, __pycache__ — these
          should never have been committed)

CONFIRMED STARTING LIST (verify each, don't assume):
  extract.py, extracted_output.txt, extracted_utf8.txt, final_payload.json,
  find_cycles.py, init_project.py, scratch_batman.py, test_exoplanet_ui_debug.py,
  ultimate_stress_test.py, run_my_tests.py, run_pipeline_test.py, run_test.py,
  test_engine.py, test_orchestrator.py, test_ingest.py, test_fetch.py,
  test_nasa.py, test.html, test3d.html, experiments.json,
  pytest_log.txt, pytest_output.txt, pytest_pipeline.log,
  err.log, err2.log, test_orchestrator_log.txt

IMPORTANT DISTINCTIONS:
  - test_engine.py / test_orchestrator.py / test_ingest.py / test_fetch.py /
    test_nasa.py / run_test.py at the ROOT are manual test scripts whose
    conversion is Bucket 5's job. Here, only MOVE them to a clear location
    (e.g. scripts/manual_tests/) — do not convert them. Note in the audit
    that Bucket 5 should pick them up from their new location.
  - extracted_output.txt / extracted_utf8.txt are multi-MB data dumps —
    almost certainly belong in .gitignore + removed, NOT committed to a
    folder. Confirm they are regenerable before recommending removal.

============================================================
PHASE 2 — RELOCATE
============================================================
1. Create the destination folders as needed: scratch/, tools/diagnostics/,
   scripts/manual_tests/, logs/ (exists), outputs/ (exists).
2. `git mv` each file to its destination per the audit. Use git mv (not
   cp+rm) so history is preserved.
3. For each (d) regenerable-artifact file, add the pattern to .gitignore
   and `git rm --cached <file>` (removes from tracking, leaves the
   working copy). Commit the .gitignore update and the untracking as
   one commit per logical group (logs together, pytest outputs together,
   data extracts together).
4. Add a short README.md to each new folder explaining what it holds
   and pointing back to reports/bucket7_hygiene_audit.md.
5. Commit each logical group (scratch relocation, diagnostics relocation,
   manual_tests relocation, .gitignore + untrack) as its own commit.

============================================================
PHASE 3 — VERIFY & REPORT
============================================================
1. `git status` must show a clean tree (everything moved/untracked is
   committed). Run the test suite:
       python -m pytest tests/ -v > reports/bucket7_posttest.txt 2>&1
   Pass count must be >= baseline (this bucket moves files, it must not
   break imports — if a moved file was actually imported somewhere, the
   test suite will tell you; revert that move and correct the audit).
2. Confirm `streamlit run app.py` still launches (static check is fine
   if interactive isn't possible).
3. Write reports/bucket7_summary.md with the full before/after map of
   where every root file went.

============================================================
HARD CONSTRAINTS
============================================================
- NOTHING is deleted. Files are moved (git mv) or untracked
  (git rm --cached + .gitignore). Deletion is an explicit later user
  decision.
- Do not move app.py, route.py, astraeus/, ui/, tests/, runs/, config.json,
  requirements.txt, README.md, MODULE_REFERENCE.md, PRD.md, prd_v2.md,
  AGENTS.md, LICENSE, .gitignore, .github/. Those are the real product.
- Do not convert any manual test script — that's Bucket 5. Only relocate.
- Do not move astraeus/ui/ — that's Bucket 1's orphan, handled there.
```

### AGENT PROMPT END

---

## Summary

| # | Bucket | Risk if skipped | Estimated relative effort |
|---|---|---|---|
| 0 | Streamlit state & caching diagnostic | The exact bug you're already hitting stays unresolved and gets worked around instead of fixed | Medium |
| 1 | Orphan cleanup, RDE rename & architecture doc | Every later bucket risks editing dead code or missing the real path; the `RemoteDiscoveryEngine` name collision keeps causing import bugs | Medium |
| 2 | Vetting threshold hardening (remaining) | Real planets around hot/large stars keep getting silently misclassified; magic numbers stay buried | Small-Medium |
| 3 | Injection-recovery completeness sweep | No empirical completeness map — your strongest publishable artifact stays unbuilt | Medium-Large |
| 4 | N-body × TTV cross-validation | TTV signals stay uninterpreted numbers instead of physically-checked candidates | Large |
| 5 | Test suite CI-readiness | Diagnostic scripts keep silently rotting, collection hangs, fresh clones can't install, no CI gate exists | Medium |
| 6 | End-to-end smoke test (optional but recommended) | No fast, single-command pipeline health check | Small |
| 7 | Root-directory hygiene | MVP ships with 5 MB of scratch dumps and 25 stray files at the root, hiding the real entry points | Small |

**Suggested MVP-freeze sequence:** 0 → 6 → 1 → 7 → 2 → 5, with 3 and 4 as stretch goals after the MVP cut (they are the publishable-research features, not the product-stability features). Each bucket's prompt is fully self-contained — copy everything between its `AGENT PROMPT START` and `AGENT PROMPT END` markers into a fresh agent session, and do not start the next bucket until the current one's `reports/bucketN_summary.md` exists and its test suite run shows no regression against the baseline it recorded in Phase 0.

---

## Notes on what changed from v1 (for reviewer context)

- **Bucket 1 reframed.** v1 assumed two parallel frontends to consolidate. The integration is already done: `ui/pages/` + `route.py` is live, `astraeus/dashboard/` is a shared library. New scope: deprecate confirmed orphans (`astraeus/ui/dashboard.py`, unused dashboard panels), rename the two same-named `RemoteDiscoveryEngine` classes, and write `docs/ARCHITECTURE.md` so later buckets stop re-deriving the live path.
- **Bucket 2 rescoped.** v1 framed the whole V-shape vetting as TODO. A new `astraeus/analysis/vetting.py` `VettingEngine` already does U-vs-V χ² comparison and is wired in. Remaining real work: physically-ground the 800 ppm secondary-eclipse threshold (the original headline bug — still present at `detection.py` `sec_depth < 0.0008`), and extract the other inline magic numbers (`0.03`, `20.0`, `3.0`, `1.5`) into named constants. New constraint: don't disturb the existing `VettingEngine`.
- **Buckets 3 & 4.** Confirmed primitive signatures and line numbers against the real source (`run_injection_recovery` at `synthetic.py:131`; `run_stability_analysis` at `nbody_solver.py:280`, `run_stability_integration` at `:383`, `estimate_mass_from_radius` at `:601`; `TTVAnalyzer.calculate` called from `detection.py:119`). Prompts otherwise unchanged in substance.
- **Bucket 5 updated.** v1 told the agent to "check if CI exists" — it does not, so Phase 3 now explicitly creates `.github/workflows/tests.yml`. v1 placed diagnostic scripts in the repo root — they're actually in `tests/`, several doing network I/O at import time (likely the `pytest_log.txt` collection-hang cause), now called out as the headline fix. Added the `requirements.txt`-is-incomplete problem (missing `astroquery`, `batman`, `statsmodels`, `pytest`, etc.) as required Phase 3 work.
- **Bucket 6 added** (smoke test) — was a suggestion in v1's footer; promoted to a full bucket per its own recommendation.
- **Bucket 7 added** (root hygiene) — new, based on the real ~25 stray root files including two multi-MB data extracts. Low risk, high MVP-polish value.
