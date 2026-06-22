# Bucket 0 — Diagnostic Findings

**Branch:** `fix/streamlit-state-diagnostic` (off `v.0.0.2`)
**Date:** 2026-06-22
**Phase 1 is READ-ONLY.** No application code was modified during this phase.
**Runtime caveat:** This is a headless environment with no browser/interactive
Streamlit runtime. `streamlit run app.py` could not be exercised interactively
(see §4). All findings below are grounded in **static code reading plus
`streamlit.testing.v1.AppTest` headless execution**. Items I could not confirm
at runtime are explicitly tagged "suspected, not runtime-confirmed."

---

## 0. Baseline established (Phase 0)

`python -m pytest tests/ -v` → **10 failed, 51 passed** (full output in
`reports/bucket0_pretest_baseline.txt`).

The 10 failures fall into three unrelated buckets; only the first is on-topic
for this work item:

| # | Test | Failure mode | On-topic? |
|---|------|--------------|-----------|
| 1–6 | `test_panel_routing`, `test_experiment_history_cycle`, `test_ui_sync_slider_events`, `test_ui_dynamic_expansion`, `test_ui_flow`, `test_workbench_navigation_persistence` | `RuntimeError: DeltaGeneratorSingleton instance already exists!` (in full suite) — **see RC-2** | related (test infra) |
| 7–9 | `test_bulletproof_detector::*` (benchmark / aliasing / state-binding) | numerical nondeterminism + a 4.8 s timing assertion (>1.5 s target) | NO (physics/benchmark) |
| 10 | `test_agent_detective::test_noise_injection` | `AssertionError` on BLS finding a candidate in pure noise | NO (physics) |

Constraint for Phase 2/3: **must not regress below 10 failed / 51 passed.**

---

## 1. CACHING AUDIT

Every `@st.cache_data` / `@st.cache_resource` in the repo was located.

### 1a. `astraeus/core/ingestion.py:217-224` — `RemoteDiscoveryEngine.fetch_data` ⚠️ OUT OF SCOPE
```python
def _cached_fetch_data(target_name: str, mission: str = "Kepler") -> dict:
    import streamlit as st
    @st.cache_data(ttl=3600, show_spinner=False)
    def _inner_fetch(t_name, m_name):
        return RemoteDiscoveryEngine._fetch_data_impl(t_name, m_name)
    return _inner_fetch(target_name, mission)
RemoteDiscoveryEngine.fetch_data = staticmethod(_cached_fetch_data)
```
- **Cache key:** `(t_name, m_name)` only. These ARE the two true inputs to
  `_fetch_data_impl`, so the key correctly captures everything the impl reads.
  No hidden global / session-state reads inside `_fetch_data_impl`.
- **Anti-pattern present (separate concern):** the decorator is re-applied on
  **every call** (`@st.cache_data` wraps a freshly-defined `_inner_fetch` each
  invocation). The cache works because Streamlit keys cached funcs by the
  *source code hash* of the inner function, which is stable across calls — but
  it is fragile and not idiomatic.
- **File location:** `astraeus/core/ingestion.py` is under `astraeus/core/`,
  which Phase 2 is **forbidden** to modify. **Documented here, not touched.**
- Cache-key verdict: **KEY IS CORRECT.** Switching target or mission produces a
  distinct cache key, so stale data is NOT silently returned on a target/
  mission switch (the scenario the prompt worried about). The `ttl=3600` (1 h)
  window is the only staleness surface, and it only affects *re-fetches of the
  identical (target, mission) pair* — acceptable.

### 1b. `ui/pages/lab.py:13` — `get_reference_data()` ✅ CORRECT
```python
@st.cache_data
def get_reference_data():
    np.random.seed(42)
    ...
```
- **Cache key:** no arguments (cache key = empty tuple). The function takes no
  inputs and reads no globals/session_state/mutable defaults. It is a pure
  constant dataset. `np.random.seed(42)` is reseeded but the output is
  deterministic, so caching it is correct. **No staleness risk.**

### Verdict
**No cached function has a cache-key / true-input mismatch.** The prompt's
hypothesised "stale cache when target/mission changes" does **not** reproduce
at this layer — `fetch_data`'s key is correct. The actual bugs are in session
state, not caching (see RC-1).

---

## 2. SESSION STATE AUDIT

All `st.session_state` usages in the UI layer were catalogued. Summary of
**unguarded or stale-prone** sites:

| File:line | Key | Guarded on init? | Stale-prone? |
|-----------|-----|------------------|--------------|
| `app.py:150` | `discovery_payload` | ✅ `if not in` | no |
| `layout.py:188` | `current_route` | ✅ `if not in` | no |
| `simulator.py:24,29` | `multi_planets`, `snr` | ✅ `if not in` | no |
| `simulator.py:87` | `edit_name_{i}` | ✅ `if not in` | no |
| `detective.py:156-161` | `search_target`, `data_route`, `uploaded_file_data` | ✅ `if not in` | **see RC-1b** |
| `detective.py:293,309,312` | `detective_results_list`, `detective_results` | set in callbacks only | **see RC-1a** |
| `detective.py:332` | `last_target` | ✅ `if not in` | no |
| `detective.py:380,403,419` | `active_metadata` | set on fetch | **see RC-1a** |
| `detective.py:687` | `stability_detective_results` | set on button click | **see RC-1a** |
| `components.py:14` | `ai_chat_messages` | ✅ `if not in` | no |
| `data_ingestion_panel.py:39` | `LIGHT_CURVE_STATE_KEY` | ✅ `if not in` | no |
| `settings.py:8-18` | llm_* settings | ✅ `if not in` (init flag) | no |
| `mcmc_panel.py:89` | `mcmc_data` | set on submit | keyed to single LC; separate route; acceptable |

### RC-1 (CONFIRMED root cause) — `detective.py` target/mission-switch state reset is incomplete

**Location:** `ui/pages/detective.py:331-345`
```python
elif target:
    if 'last_target' not in st.session_state or st.session_state['last_target'] != target:
        st.session_state['last_target'] = target
        for key in ['detective_plot_data', 'detective_results', 'fetched_target_data',
                    'active_time', 'active_flux']:
            if key in st.session_state:
                del st.session_state[key]
```
**Why it's a bug:**
1. The reset list **omits keys that `run_analysis` and the fetch handler write:**
   - `detective_results_list` (set at `:293` and `:309`)
   - `active_metadata` (set at `:380`, `:403`, `:419`)
   - `stability_detective_results` and `stability_detective_config_hash` (`:687-688`)
2. When a user runs detection on **target A**, then changes the search box to
   **target B**, the stale `active_metadata` (period / stellar radius / transit
   depth, read at `:422-424` and rendered into the "Target Discovery
   Confirmation" card `:430-436`) and `detective_results_list` (rendered at
   `:609-648`) from **A** persist and are displayed for **B** until B's fetch +
   analysis complete. This is exactly the "works standalone, wrong/stale through
   the UI" symptom, with physics that is provably correct (`detect_transit_candidate`
   and `run_multi_planet_search` are fully stateless — see §3).
3. The reset fires **only on `target` text change**. Changing the **Data Route**
   dropdown (`data_route`, `:228`) from e.g. "Kepler" to "TESS" for the **same**
   target does NOT reset anything. If the user then re-clicks Fetch, the cache
   key changes (so fresh data is fetched — good), but if they instead click
   "Analyze Telemetry & Verify Harmonics" on the *already-stored* `fetched_target_data`,
   they analyze A-on-Kepler data while the dropdown reads "TESS" — a
   display-vs-data inconsistency.

**Evidence:** the keys are set in the same file at the lines cited above; the
reset loop enumerates a literal list that does not include them. This is a
defect of omission, confirmed by static reading of the same module.

**Rank:** **#1** — highest likelihood of explaining the reported symptom
(stale/wrong Detective results when switching targets through the UI).

### RC-1b (minor, same file) — `uploaded_file_data` reassignment order
`detective.py:243` sets `uploaded_file_data = None` whenever the uploader is
empty, and `:239` sets it on parse. Because `render_discovery_bar` is called
every rerun (`:260`) before the `elif target:` branch (`:331`), the
`uploaded_file_data` path and the `target` path are mutually exclusive
(`:324` vs `:331`). This is internally consistent. Not a bug — listed only to
record it was checked.

---

## 3. RERUN MODEL AUDIT

Streamlit reruns the whole script top-to-bottom on each widget interaction.
Anything that assumes single execution and persists in module-level mutable
state would corrupt across reruns.

Checked all of `astraeus/dashboard/services/`, `astraeus/analysis/`,
`astraeus/core/`, and the UI layer:

- **`detect_transit_candidate`** (`analysis/detection.py`): all state is local
  (`time`, `flux`, `active_time`, `active_flux`, `candidates` list). No module-
  level mutable state. **Stateless. ✅**
- **`run_multi_planet_search`** (`core/orchestrator.py`): all accumulators
  (`discovered_planetary_properties`, `discovered_periods`,
  `current_working_flux`, counters) are local. **Stateless. ✅**
- **`run_mcmc`** / **`run_retrieval`** (`analysis/error_analysis.py`,
  `dashboard/services/mcmc_retrieval.py`): inputs are arguments + a frozen
  `MCMCConfig` dataclass; outputs are a frozen `MCMCRetrievalResult`. **Stateless. ✅**
- **`run_stability_analysis` / `check_system_stability`** (`core/nbody_solver.py`):
  pure functions of `planet_dicts`. **Stateless. ✅**
- **`reporting.py`** `self._saved_page_states = []` is instance-level, created
    fresh per call to `generate_academic_report`. Not shared across reruns. ✅
- **`logging.py`** `LOG_FILE` is a module-level *string constant*; the file on
  disk accumulates history by design (that's its purpose). Not a rerun bug. ✅

**Verdict:** No module-level mutable accumulator or singleton in the physics or
service layers. Results stored to session state are correctly *produced* fresh;
the defect is solely that the UI does not *clear* the prior result's keys when
the input identity changes (RC-1).

---

## 4. REPRODUCE THE SYMPTOM

**Could not run `streamlit run app.py` interactively** — this is a headless
sandbox with no browser/display server. Stated explicitly per the "no silent
fallback" rule rather than simulated.

What WAS run, as a runtime proxy, is `streamlit.testing.v1.AppTest` (the same
headless harness the project's own tests use):
- `AppTest.from_file("app.py").run()` loads the app with **no exception**
  (`at.exception` is an empty `ElementList`).
- Initial `session_state` confirmed: `{snr, discovery_payload, current_route,
  ...widget keys...}` — matches `_initialize_session_state()` and `layout.py`.
- Sidebar nav buttons present: Simulation / Lab / Detective / Discover /
  History / Settings — matches `layout.render_left_nav`.

**Reproduction of the stale-result *mechanism* is therefore static +
session-state-trace confirmed; the interactive browser click-through is
runtime-unverified.** See RC-1 for the line-precise static proof.

A separate, **unrelated** runtime finding emerged from this step and is
recorded below as RC-2 (it explains 6 of the 10 baseline test failures but is
a test/Streamlit-version issue, not an app-layer defect).

### RC-2 (CONFIRMED, but test-infrastructure — see scope note) — `AppTest` DeltaGenerator singleton pollution across tests

**Symptom in the full suite:** `RuntimeError: DeltaGeneratorSingleton
instance already exists!` raised inside Streamlit's own
`delta_generator_singletons.py:74`, surfacing as the failure mode of 6 tests
(`test_panel_routing`, `test_experiment_history_cycle`,
`test_ui_sync_slider_events`, `test_ui_dynamic_expansion`, `test_ui_flow`,
`test_workbench_navigation_persistence`).

**Proof it is cross-test pollution, not app code:**
- `test_experiment_history_cycle` **PASSES** when run with just one other
  AppTest test (`pytest test_agent_detective.py::test_panel_routing
  test_experiment_history.py::test_experiment_history_cycle`).
- The **same test FAILS** with the DeltaGenerator `RuntimeError` in the full
  suite. So the failure is order/cumulative-state dependent, triggered by
  earlier `AppTest.from_file("app.py")` runs in the same process.
- When run **in isolation**, these tests fail for an entirely different reason
  (below), never with the DeltaGenerator error.

This is a known Streamlit-testing friction: each `AppTest` session instantiates
a `DeltaGeneratorSingleton` that is not torn down at process exit, so a second
`AppTest` in the same process trips the singleton guard. **The application code
does not create this singleton** — it lives inside `streamlit` itself.

**Scope note:** RC-2 is a *test-harness / Streamlit-version* issue. This bucket
is scoped to `app.py / route.py / ui/ / astraeus/dashboard/ui/`.
`tests/*.py` is **not** in the in-scope set, and the prompt explicitly forbids
modifying physics tests and renaming classes. **RC-2 is documented, not fixed
here.** A correct fix belongs in a dedicated test-infra bucket (e.g. a
`conftest.py` session fixture that resets the singleton, or pinning the
Streamlit `AppTest` lifecycle). It is listed so the user knows *why* those 6
tests are red and that this bucket will not fix them.

### RC-3 (CONFIRMED, test/app-label mismatch — also out of scope to "fix" by changing app behavior)
`test_agent_detective.py:91`, `test_workbench_navigation.py:52`, and
`test_panel_routing` all look for a button labelled **"Run Detection"**. The
app (`detective.py:327,441`) labels it **"Analyze Telemetry & Verify Harmonics"**.
In isolation these tests fail with `AssertionError: Run Detection button not
found`. This is a test-side label drift; the app button works. **Documented,
not fixed** (fixing would mean editing `tests/`, out of scope).

---

## 5. RANKED ROOT CAUSES

Ranked by likelihood of explaining the user's actual symptom
("physics correct standalone, wrong/stale/crashing through the UI"):

| Rank | ID | File:line | Root cause | In scope? | Action |
|------|----|-----------|------------|-----------|--------|
| **1** | **RC-1** | `ui/pages/detective.py:332-336` | Target/mission switch clears an incomplete set of session keys; `detective_results_list`, `active_metadata`, `stability_detective_results[_config_hash]` from the previous target/route persist and render for the new one. The physics is stateless, so the *only* way stale results appear is this UI-layer omission. | ✅ YES (`ui/`) | **FIX in Phase 2** |
| 2 | RC-1(mission) | `ui/pages/detective.py:331` | Reset fires only on `target` text change, not on `data_route` change → same target, different mission shows stale route/data mismatch. | ✅ YES (`ui/`) | **FIX in Phase 2** (same site as #1) |
| 3 | RC-2 | `streamlit` internals / `tests/*` | `AppTest` DeltaGenerator singleton not reset between tests in one process → 6 tests crash with `RuntimeError` in full suite. | ❌ NO (`tests/`, streamlit lib) | Document only |
| 4 | RC-3 | `tests/*` vs `detective.py` | Tests expect "Run Detection" button; app uses "Analyze Telemetry & Verify Harmonics". | ❌ NO (`tests/`) | Document only |
| 5 | — | `astraeus/core/ingestion.py:219` | `@st.cache_data` applied to a re-defined inner func each call (anti-pattern). Cache KEY is correct; behaviour is correct; just fragile. | ❌ NO (`astraeus/core/`) | Document only |

**Items flagged "needs further investigation" but NOT fixed:**
- RC-2/RC-3: should be a separate test-hygiene bucket. Do not fix by editing
  `tests/` from this bucket.

---

## Phase 1 conclusion

Only **RC-1** (target/mission-switch state reset in `ui/pages/detective.py`)
is (a) confirmed, (b) on-topic for the reported symptom, and (c) in scope.
Phase 2 will make the smallest possible fix at that single site: extend the
reset key list to include the omitted keys, and reset on `data_route` change as
well as `target` change. No `astraeus/core/` or `astraeus/analysis/` file will
be touched. No file will be deleted or renamed.
