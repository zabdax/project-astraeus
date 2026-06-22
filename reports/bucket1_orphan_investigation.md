# Bucket 1 — Orphan Investigation & RemoteDiscoveryEngine Disambiguation

**Branch:** `refactor/orphan-cleanup-and-rde-rename`
**Phase:** 1 (Discovery — read-only, no code changes)
**Baseline test result (Phase 0):** 53 passed, 10 failed (all 10 pre-existing; see `reports/bucket1_pretest_baseline.txt`)
**Date:** 2026-06-22

> A note on the working tree: at the start of this bucket the prior (terminated)
> agent had left three uncommitted artifacts behind on this branch — a stray
> `nul` file (a botched Windows redirect), a test-churn modification to
> `logs/experiments.json`, and an incomplete `reports/bucket1_pretest_baseline.txt`.
> **No prior Phase 2/3 work existed** (no `deprecated/` folder, no
> `docs/ARCHITECTURE.md`, no RDE rename in code). Those leftovers were removed
> and the tree reset to clean before Phase 0 ran, per the user's "fresh start"
> instruction. Bucket 0 and Bucket 6 commits already on the branch are unrelated
> earlier buckets and were left untouched.

---

## 1. ENTRY-POINT TRACING (re-confirmed by reading import statements)

### Live launch path

```
streamlit run app.py
```

`app.py` import block (lines 11–15):

```python
from astraeus.dashboard.ui.layout import workbench_layout       # layout.py
from astraeus.dashboard.ui.styles import inject_page_styles     # styles.py
from astraeus.dashboard.ui.components import render_floating_chat  # components.py
from astraeus.analysis.reporting import generate_academic_report
from route import render_route
```

So `app.py` imports **exactly three** `astraeus/dashboard/ui/` modules: `layout`,
`styles`, `components`. This matches the prompt's premise.

### Real import tree (verified 2+ levels deep)

```
app.py
├── astraeus.dashboard.ui.layout.workbench_layout
│     (layout.py imports ONLY streamlit — pulls in no other astraeus module)
├── astraeus.dashboard.ui.styles.inject_page_styles
│     (styles.py imports ONLY streamlit)
├── astraeus.dashboard.ui.components.render_floating_chat
│     (components.py imports ONLY streamlit)
├── astraeus.analysis.reporting.generate_academic_report
└── route.render_route
      └── ui.pages.{simulator, lab, detective, history, settings}  (route.py:5)
            ├── simulator.py  -> astraeus.dashboard.figures.*
            │                   astraeus.core.transit_model.generate_multi_planet_transit
            │                   astraeus.dashboard.simulation.semi_major_axis_for_solar_mass
            │                   astraeus.data.preprocessing.inject_gaussian_noise
            │                   astraeus.core.orbital_models.calculate_orbital_position
            │                   (lazy) astraeus.core.nbody_solver.*
            ├── lab.py        -> astraeus.core.sensitivity_engine.get_model_curve
            ├── detective.py  -> astraeus.analysis.detection.detect_transit_candidate
            │                   astraeus.core.orchestrator.run_multi_planet_search
            │                   astraeus.core.ingestion.RemoteDiscoveryEngine, DataAdapter   <-- RDE #1 (LIVE)
            │                   (lazy) astraeus.core.nbody_solver.*
            ├── history.py    -> astraeus.analysis.logging.load_experiment_history
            └── settings.py   -> astraeus.dashboard.ui.settings.render_settings_panel   <-- LIVE dashboard/ui module
```

The "Discover" tab is rendered **inline in `app.py`** (lines 192–292); it does
**not** go through `route.py`. `route.py` only handles Simulation / Lab /
Detective / History / Settings.

### Shared-library status of `astraeus/dashboard/` (non-ui)

These are still imported by live paths and are therefore **LIVE shared libraries**:

| Module | Live importer (runtime, not TYPE_CHECKING) |
|---|---|
| `dashboard/figures.py` | `ui/pages/simulator.py:10` |
| `dashboard/simulation.py` | `dashboard/figures.py:10` (runtime); `ui/pages/simulator.py:16` |
| `dashboard/scenario.py` | `dashboard/__init__.py:3`; `dashboard/simulation.py:13`; `dashboard/validation.py:5` |
| `dashboard/validation.py` | `dashboard/simulation.py:14` (runtime) |
| `dashboard/ui/{layout,styles,components}.py` | `app.py:11-13` |
| `dashboard/ui/settings.py` | `ui/pages/settings.py:4` |
| `dashboard/services/data_ingestion.py` | `dashboard/services/data_ingestion.py` is imported by `astraeus/data/discovery.py:160` (inside `discover_and_cache`, but that module is itself an orphan candidate — see §2) **and** by the orphan `dashboard/ui/data_ingestion_panel.py:8`. No live importer found. |
| `dashboard/services/mcmc_retrieval.py` | only referenced under `if TYPE_CHECKING:` in `figures.py:13` (not a runtime import) and by orphan panels. |
| `dashboard/services/action_deck.py` | only by orphan `dashboard/ui/action_deck.py:10` / `mcmc_panel.py:12`. |

> **Important caveat (out of scope for this bucket's hard constraints):** the
> `dashboard/services/*` modules are imported only by orphan UI panels and by
> RDE #2 (itself an orphan candidate). However, the bucket's hard constraints
> scope Phase 2 cleanup to **(a)** `astraeus/ui/dashboard.py`, **(b)** the named
> `astraeus/dashboard/ui/` panels, and **(c)** the RemoteDiscoveryEngine
> collision. `dashboard/services/*` are dependencies *of* the orphan panels but
> are not themselves in the named target list. Deprecating the orphan UI panels
> leaves `services/*` with no live importers; I flag this in §6 as a follow-up
> for a later explicit cleanup step, and **do not** touch `services/*` here.

---

## 2. REMOTEDISCOVERYENGINE DISAMBIGUATION

### RDE #1 — `astraeus/core/ingestion.py:24`  (the Streamlit-aware facade)

| Aspect | Detail |
|---|---|
| `file:line` | `astraeus/core/ingestion.py:24` |
| Public surface | `_resolve_mission_target`, `_bridge_to_time_series`, `_fetch_data_impl` (all `@staticmethod`, **no Streamlit**), and `fetch_data` (attached dynamically at module load, line 224, wrapping `_fetch_data_impl` in `@st.cache_data`) |
| Caching | `fetch_data` → `@st.cache_data(ttl=3600)` (line 219). `_fetch_data_impl` itself is **uncached and Streamlit-free**. |
| Importers (file:line) | `ui/pages/detective.py:10` (**LIVE UI**), `tests/global_matrix_stress_test.py:14`, `tests/pipeline_stress_test.py:121`, `tests/solid_matrix_diagnostic.py:23`, `tests/trace_download_deadlock.py:20`, `test_ingest.py:7` |
| How the live UI calls it | `detective.py:391` → `RemoteDiscoveryEngine.fetch_data(target, mission=mission)` (the cached entry point) |
| How headless scripts call it | stress/diagnostic scripts call `RemoteDiscoveryEngine._fetch_data_impl(...)` **directly** — deliberately bypassing Streamlit (see `pipeline_stress_test.py:9`: *"Executes the full ... pipeline without initialising the Streamlit UI, using the raw `_fetch_data_impl` entry point."*) |

### RDE #2 — `astraeus/data/discovery.py:8`  (the astroquery/lightkurve direct implementation)

| Aspect | Detail |
|---|---|
| `file:line` | `astraeus/data/discovery.py:8` |
| Public surface | `query_metadata`, `fetch_time_series`, `discover_and_cache` (all `@staticmethod`, **no Streamlit** except `discover_and_cache` optionally writes `st.session_state` inside a bare `try/except` that silently ignores non-Streamlit contexts) |
| Caching | none |
| Importers (file:line) | `astraeus/data/__init__.py:5` (package re-export only — no other file imports `from astraeus.data import RemoteDiscoveryEngine`; `dashboard/services/data_ingestion.py:9` imports `DataAdapter` from the same package, not RDE), `tests/test_discovery.py:7,10,32,69,70` |
| Live UI importers | **NONE.** `detective.py` uses RDE #1. No `ui/pages/*` references `query_metadata` / `fetch_time_series` / `discover_and_cache`. |
| Last git commit | `b823181` **2026-06-02** *"Add RemoteDiscoveryEngine and UI integration"* — the "UI integration" it refers to was the now-dead dashboard panels. |

### Headless-context analysis (the deciding question)

The prompt asked: does RDE #1 work correctly **outside** a Streamlit context, or
does its `@st.cache_data` wrapper force a separate astroquery implementation for
scripts/tests?

**Finding:** RDE #1 is deliberately designed to be callable both ways:

- `_fetch_data_impl` is a plain `@staticmethod` with **no Streamlit import and
  no Streamlit call**. It is the pure network/parse logic. This is what every
  headless stress/diagnostic script calls directly.
- The `@st.cache_data` wrapper lives **only** in the separate
  `_cached_fetch_data` function (line 217), which itself does `import streamlit
  as st` **lazily inside the function body**. `st.cache_data` applied to a
  function returns the cached version *when called inside an active Streamlit
  script context*; called from a plain Python process it raises
  `StreamlitAPIException`, but the headless scripts never call `fetch_data` —
  they call `_fetch_data_impl`, which is Streamlit-free.

So **RDE #1 already serves both the Streamlit UI (via `fetch_data`) and the
headless pipeline (via `_fetch_data_impl`)**. There is no Streamlit-headless
limitation in RDE #1 that would justify a second implementation. The two classes
are functionally overlapping alternates, **not** context-specialized complements.

### Conclusion for the collision

- RDE #1 (`core/ingestion.py`) — **LIVE**, actively maintained (last commit
  2026-06-22, i.e. today). The single source of truth for both UI and headless
  ingestion. **Keep, keep its name.**
- RDE #2 (`data/discovery.py`) — **DEAD** in the live path: zero live UI
  importers, only a package re-export and one mocked test file touch it. Its
  own commit message ("UI integration") points at panels that are themselves
  orphans. Last touched 2026-06-02, then abandoned for RDE #1.

**Recommended resolution (option (b) — deprecate one):** deprecate RDE #2 by
moving `astraeus/data/discovery.py` to `deprecated/`, and remove its re-export
from `astraeus/data/__init__.py`. Keep RDE #1's name (`RemoteDiscoveryEngine`)
unchanged — it is the survivor and there is then no collision to rename.

  Rationale: Phase 1.2 found RDE #1 covers both contexts, so per the prompt's
  instruction *"Do not pick (a) vs (b) by guessing — base it on the Phase 1.2
  headless-context finding,"* the headless finding points unambiguously to (b).

  ⚠️ **Test-impact caveat for RDE #2:** `tests/test_discovery.py` has **3
  pytest-collected, currently-passing tests** (all mocked). A physical move of
  `data/discovery.py` breaks their `from astraeus.data.discovery import ...` and
  their `@patch("astraeus.data.discovery.NasaExoplanetArchive.query_criteria")`
  patch targets, dropping up to 3 passing tests. Per the bucket's "no silent
  fallbacks / no regressions" rules this must be handled explicitly: the test
  file will be moved alongside the module into `deprecated/` (preserving the
  tests rather than deleting them) AND excluded from collection, OR its imports
  re-pointed at the new location. The exact handling is decided and executed in
  Phase 2, with the post-test run as the regression gate.

---

## 3. GIT HISTORY CHECK (recency signals)

```
astraeus/core/ingestion.py   dcc467c  2026-06-22 11:21  (today — actively maintained)   [RDE #1]
astraeus/data/discovery.py   b823181  2026-06-02 10:13  (3 weeks stale)                  [RDE #2]
astraeus/ui/                 656dd47  2026-06-19 17:27  (last touched in a reporting/UI commit)
astraeus/dashboard/          656dd47  2026-06-19 17:27  (same commit)
```

- RDE #1's home (`core/ingestion.py`) is the **most recently maintained** file
  in the entire comparison — committed today. RDE #2's home has been untouched
  for 3 weeks and its only commit is the one that "added" it.
- `astraeus/ui/` and `astraeus/dashboard/` share the same last commit — a weak
  signal; it is the git-history of *importers*, not the panels themselves, that
  carries the decision (covered in §1).

---

## 4. PROPOSAL / VERDICTS

### ORPHAN 1 — `astraeus/ui/dashboard.py`

**VERDICT: CONFIRMED DEAD (high confidence).**

- Repo-wide ripgrep of the module path `astraeus.ui` and `astraeus.ui.dashboard`
  finds references in **exactly one file**: `tests/test_chaos_integration_suite.py`
  (docstring line 9; import line 158; `import astraeus.ui.dashboard as dash_mod`
  line 177). That file is a **standalone script** — it contains `0`
  pytest-collectable `def test_` functions, so it is not part of the pytest run
  at all; it is invoked directly (`python tests/test_chaos_integration_suite.py`).
- No live path (`app.py`, `route.py`, `ui/`, or any still-live
  `astraeus/dashboard/` module) imports `astraeus.ui.*`. The actual live entry
  is `app.py`, whose inline "Discover" tab supersedes `astraeus/ui/dashboard.py`
  wholesale (both define `BASELINE_PAYLOAD`, `_build_adapted_metrics_payload`,
  `_check_headless_prerequisites`, `_initialize_session_state`, `main` —
  `astraeus/ui/dashboard.py` is an older parallel copy of what `app.py` now
  does inline).
- The file's own docstring (line 7) and `MODULE_REFERENCE.md:636,851` still
  advertise `streamlit run astraeus/ui/dashboard.py` as the entry point —
  **stale documentation**; the live entry is `streamlit run app.py`. (Doc
  fixes happen in Phase 3, ARCHITECTURE.md.)

**Action:** Move to `deprecated/`, update the obsolete test import in
`test_chaos_integration_suite.py`.

### ORPHAN 2 — `astraeus/dashboard/ui/sidebar.py`

**VERDICT: CONFIRMED DEAD (high confidence).**

- Zero importers of `astraeus.dashboard.ui.sidebar` anywhere (module path or
  exported symbols `render_app_sidebar` / `render_scenario_controls`) outside
  the file itself. The live sidebar is `layout.render_left_nav()`
  (`layout.py:168`), imported by `app.py`.

### ORPHAN 3 — `astraeus/dashboard/ui/simulation_panel.py`

**VERDICT: CONFIRMED DEAD (high confidence).**

- Zero live importers. `render_simulation_panel` is referenced nowhere outside
  the file. The live simulation UI is `ui/pages/simulator.py` (via `route.py`).

### ORPHAN 4 — `astraeus/dashboard/ui/data_ingestion_panel.py`

**VERDICT: CONFIRMED DEAD (high confidence).**

- Zero importers of the module path. It is the "root" of a self-referential
  dead cluster (it imports `mcmc_panel`, which imports `action_deck` +
  `mcmc_form` + `services/*`).

### ORPHAN 5 — `astraeus/dashboard/ui/mcmc_panel.py`

**VERDICT: CONFIRMED DEAD (transitive, high confidence).**

- Only importer is the also-dead `data_ingestion_panel.py:13`. Its own symbols
  (`render_mcmc_analysis_panel`, `_execute_mcmc_retrieval`,
  `_render_retrieval_results`) have no importers outside the dead cluster.

### ORPHAN 6 — `astraeus/dashboard/ui/action_deck.py`

**VERDICT: CONFIRMED DEAD (transitive, high confidence).**

- Only importer is the also-dead `mcmc_panel.py:17`. `render_action_deck` has
  no other importer.

### ORPHAN 7 — `astraeus/dashboard/ui/mcmc_form.py`

**VERDICT: CONFIRMED DEAD (transitive, high confidence).**

- Only importer is the also-dead `mcmc_panel.py:18`. `render_mcmc_config_form`
  has no other importer.

### NOT an orphan — `astraeus/dashboard/ui/settings.py`

The prompt's candidate list included `settings.py`, but
`ui/pages/settings.py:4` does `from astraeus.dashboard.ui.settings import
render_settings_panel` → it is **STILL LIVE** via `route.py`. **Leave
untouched.**

### NOT an orphan — `astraeus/dashboard/ui/{layout,styles,components}.py`

All three are imported directly by `app.py:11-13`. **LIVE.** Leave untouched.

### RemoteDiscoveryEngine collision — see §2

**VERDICT: deprecate RDE #2 (`data/discovery.py`), keep RDE #1's name.** High
confidence, based on the §2 headless-context analysis (RDE #1's `_fetch_data_impl`
is already the headless entry, so no second class is needed for that context).

---

## 5. ITEMS FLAGGED AS AMBIGUOUS / DEFERRED

- **`astraeus/dashboard/services/*` (`data_ingestion.py`, `mcmc_retrieval.py`,
  `action_deck.py`):** After the Phase 2 panel deprecations, these will have no
  live importers (they were imported only by the dead panels and, for
  `data_ingestion`, by RDE #2). They are **dependencies of** the orphan panels
  but are not in the named target list, and the hard constraints forbid
  broadening scope. **Flagged for a later explicit cleanup bucket; NOT touched
  in this bucket.**
- **Stale entry-point docs:** `MODULE_REFERENCE.md:636,851` and
  `astraeus/ui/dashboard.py:7` docstring claim `streamlit run
  astraeus/ui/dashboard.py` is the entry. The live entry is `app.py`. The
  ARCHITECTURE.md (Phase 3) documents the truth; correcting MODULE_REFERENCE.md
  itself is a doc-only follow-up not required by this bucket's deliverables.

## 6. CONFIDENCE SUMMARY

| Target | Verdict | Confidence | Notes |
|---|---|---|---|
| `astraeus/ui/dashboard.py` | CONFIRMED DEAD | High | Only importer is a non-pytest standalone script; superseded by `app.py` |
| `dashboard/ui/sidebar.py` | CONFIRMED DEAD | High | Zero importers |
| `dashboard/ui/simulation_panel.py` | CONFIRMED DEAD | High | Zero importers |
| `dashboard/ui/data_ingestion_panel.py` | CONFIRMED DEAD | High | Root of dead cluster |
| `dashboard/ui/mcmc_panel.py` | CONFIRMED DEAD (transitive) | High | Only importer is dead |
| `dashboard/ui/action_deck.py` | CONFIRMED DEAD (transitive) | High | Only importer is dead |
| `dashboard/ui/mcmc_form.py` | CONFIRMED DEAD (transitive) | High | Only importer is dead |
| `dashboard/ui/settings.py` | STILL LIVE | High | Imported by `ui/pages/settings.py` |
| `dashboard/ui/{layout,styles,components}.py` | STILL LIVE | High | Imported by `app.py` |
| RDE #1 `core/ingestion.py` | LIVE (survivor) | High | Used by live UI + headless scripts |
| RDE #2 `data/discovery.py` | DEAD (deprecate) | High | No live importer; 3 mocked tests to relocate |
| `dashboard/services/*` | DEFERRED | Medium | Becomes dead after Phase 2 but out of scope |

No target in this bucket remains ambiguous. Phase 2 may proceed for all
CONFIRMED DEAD targets above and the RDE deprecation, with the post-commit test
run as the regression gate.
