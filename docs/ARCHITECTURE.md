# ASTRAEUS — Architecture

> **If you're a new agent, read this first.**
> ASTRAEUS is a Streamlit application for exoplanet transit detection. The live
> UI is launched with `streamlit run app.py` (project root). Do **not** trust
> older docs or file names that point at `astraeus/ui/dashboard.py` — that path
> is deprecated (see `deprecated/`). The application shell lives in `app.py`,
> feature pages live in `ui/pages/`, and `astraeus/dashboard/` is now a **shared
> library** (layout, styles, chat component, figures, simulation, settings) that
> both `app.py` and `ui/pages/` import from. The analysis pipeline
> (`astraeus/analysis/`) is the scientific core and is invoked from the
> Detective page. All ingestion goes through one engine:
> `astraeus/core/ingestion.py::RemoteDiscoveryEngine`.

---

## 1. The live launch path

```
streamlit run app.py
```

```
                       ┌─────────────────────────────────────────────────────────┐
                       │                         app.py                          │
                       │  (project root — the ONLY live Streamlit entry point)  │
                       └─────────────────────────────────────────────────────────┘
                                     │
            ┌────────────────────────┼─────────────────────────────┐
            │                        │                             │
            ▼                        ▼                             ▼
  astraeus/dashboard/ui/     inline "Discover" tab          route.render_route()
   layout.workbench_layout   (app.py:192-292,               (route.py:5)
   styles.inject_page_styles  rendered inline in app.py)           │
   components.render_floating_chat                                  ▼
            │                                              ui.pages.{simulator, lab,
            │                                       detective, history, settings}
            ▼                                                       │
   sidebar nav (layout.render_left_nav)                             │
   yields selected_feature                                          │
            │                                                       │
            └──────────────► if selected == "Discover": inline ◄────┘
                            else: route.render_route(feature, ...)
```

- **Sidebar navigation** is rendered by
  `astraeus/dashboard/ui/layout.py::render_left_nav` (called inside
  `workbench_layout`, `layout.py:168`), imported by `app.py:11`. It yields
  `selected_feature` ∈ {Simulation, Lab, Detective, Discover, History, Settings}.
- The **"Discover" tab is rendered inline in `app.py`** (`app.py:192-292`) — it
  does *not* go through `route.py`.
- All other tabs go through `route.py::render_route` (`route.py:5`), which
  dispatches to `ui/pages/{simulator, lab, detective, history, settings}.py`.

### Per-page live imports

| Page (`ui/pages/`) | Live imports |
|---|---|
| `simulator.py` | `astraeus.dashboard.figures`, `astraeus.core.transit_model`, `astraeus.dashboard.simulation`, `astraeus.data.preprocessing`, `astraeus.core.orbital_models`, (lazy) `astraeus.core.nbody_solver` |
| `lab.py` | `astraeus.core.sensitivity_engine` |
| `detective.py` | `astraeus.analysis.detection.detect_transit_candidate`, `astraeus.core.orchestrator.run_multi_planet_search`, `astraeus.core.ingestion.{RemoteDiscoveryEngine, DataAdapter}`, (lazy) `astraeus.core.nbody_solver` |
| `history.py` | `astraeus.analysis.logging.load_experiment_history` |
| `settings.py` | `astraeus.dashboard.ui.settings.render_settings_panel` |

---

## 2. `astraeus/dashboard/` — shared library vs. deprecated

### Still-shared libraries (LIVE)

| Module | Role | Live importer |
|---|---|---|
| `dashboard/ui/layout.py` | 3-panel workbench + sidebar nav + theme | `app.py:11` |
| `dashboard/ui/styles.py` | page-level CSS refinements | `app.py:12` |
| `dashboard/ui/components.py` | floating AI chat popover | `app.py:13` |
| `dashboard/ui/settings.py` | settings panel | `ui/pages/settings.py:4` |
| `dashboard/figures.py` | plotly orbit / light-curve / residuals figures | `ui/pages/simulator.py:10` |
| `dashboard/simulation.py` | `DashboardSimulation`, `semi_major_axis_for_solar_mass` | `dashboard/figures.py:10`, `ui/pages/simulator.py:16` |
| `dashboard/scenario.py` | `DashboardTransitScenario` dataclass | `dashboard/__init__.py`, `simulation.py`, `validation.py` |
| `dashboard/validation.py` | `validate_scenario`, `generate_stable_seed` | `dashboard/simulation.py:14` |

### Deprecated in Bucket 1 (moved to `deprecated/`, NOT deleted)

| Moved from | Moved to | Why |
|---|---|---|
| `astraeus/ui/dashboard.py` (+ `astraeus/ui/` package) | `deprecated/astraeus_ui_dashboard/` | Older parallel copy of `app.py`; only importer was a standalone non-pytest chaos script. Superseded by `app.py`'s inline Discover tab. |
| `dashboard/ui/{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py` | `deprecated/astraeus_dashboard_ui/` | Self-referential dead cluster with zero live importers. Live sidebar is `layout.render_left_nav`; live sim/ingestion UIs are in `ui/pages/`. |
| `astraeus/data/discovery.py` | `deprecated/astraeus_data_discovery/` | Second `RemoteDiscoveryEngine` — redundant with `core/ingestion.py` (see §3). |

> **Deferred (NOT touched in Bucket 1):** `astraeus/dashboard/services/*`
> (`data_ingestion.py`, `mcmc_retrieval.py`, `action_deck.py`) were imported only
> by the now-deprecated panels and by the deprecated `data/discovery.py`. They
> are dependencies *of* deprecated code rather than named targets of Bucket 1,
> and are flagged in `reports/bucket1_orphan_investigation.md` §5 for a later,
> explicit cleanup step.

---

## 3. The data layer — one ingestion engine, two call styles

There is now **one** `RemoteDiscoveryEngine`, in
`astraeus/core/ingestion.py:24`. It is a facade over
`NASAExoplanetArchive` (metadata) and `LightkurveClient` (MAST time-series),
and it deliberately exposes **two** entry points so it serves both the
Streamlit UI and headless scripts:

```
                            RemoteDiscoveryEngine
                            (astraeus/core/ingestion.py:24)
                                          │
           ┌──────────────────────────────┴──────────────────────────────┐
           │                                                            │
           ▼                                                            ▼
  fetch_data (ingestion.py:224)                        _fetch_data_impl (ingestion.py:158)
  • attached dynamically at module load                • plain @staticmethod
  • wraps _fetch_data_impl in @st.cache_data           • NO Streamlit, NO caching
    (ttl=3600, lazy `import streamlit as st`)          • the pure network/parse logic
  • the STREAMLIT UI entry point                       • the HEADLESS entry point
  • called by ui/pages/detective.py:391                • called by tests/{pipeline,global,
    (RemoteDiscoveryEngine.fetch_data(target,             solid}*.py, trace_download_deadlock.py,
     mission=...))                                       test_ingest.py
```

**Why one engine covers both contexts:** `_fetch_data_impl` is Streamlit-free,
so headless stress/diagnostic scripts call it directly. The `@st.cache_data`
wrapper lives only in the separate `_cached_fetch_data` function
(`ingestion.py:217`), which does `import streamlit as st` *lazily inside its
body* — so it is only engaged when called from an active Streamlit script
context. There is no headless limitation that would justify a second engine.

> **Historical note:** a second, astroquery-based `RemoteDiscoveryEngine`
> previously lived in `astraeus/data/discovery.py`. It had no live importer
> (only a package re-export and one mocked test) and was functionally
> redundant with `core/ingestion.py`. It was deprecated in Bucket 1 and moved
> to `deprecated/astraeus_data_discovery/`. Its package re-export was removed
> from `astraeus/data/__init__.py` to prevent resurrecting the name collision.
> See `reports/bucket1_orphan_investigation.md` §2 for the headless-context
> analysis that drove this.

---

## 4. The analysis pipeline (`detect_transit_candidate`)

The scientific core is `astraeus/analysis/detection.py::detect_transit_candidate`
(`detection.py:11`), invoked from `ui/pages/detective.py` and by the
multi-planet orchestrator. Inside one call, the pipeline runs in this order
(line numbers are `astraeus/analysis/detection.py` unless noted):

```
detect_transit_candidate(time, flux, ...)                 detection.py:11
  │
  ├─1. DETREND
  │    DetrendingEngine.estimate_stellar_rotation(...)    detection.py:15
  │    DetrendingEngine.detrend(...)                      detection.py:16
  │
  └─> for iteration in 1..3 (multi-planet subtraction):   detection.py:23
        │
        ├─2. BLS SEARCH
        │    BLSSearchEngine.search(active_time, ...)     detection.py:27
        │      -> {period, snr, depth, t0, duration,
        │          confidence_score, periodogram}
        │
        ├─3. GEOMETRIC VALIDATION
        │    GeometricValidator.validate(...)             detection.py:68
        │      -> impact parameter, duration consistency,
        │         secondary_eclipse_depth, secondary_eclipse_detected
        │
        ├─4. VETTING (U vs V transit shape)
        │    VettingEngine.vet_transit_shape(...)         detection.py:72
        │      -> vetting_confidence, vetting_status
        │    result['v_shape_metric'] =                   detection.py:76
        │      1.0 - vetting_confidence    (back-compat key)
        │
        ├─5. FALSE-POSITIVE CROSS-VETTING (decision tree) detection.py:79-110
        │    fuses SNR + V-shape + secondary-eclipse + depth
        │      -> one of:
        │           "Verified Planet Candidate"
        │           "Eclipsing Binary Detected"
        │           "V-Shaped False Positive Risk (Potential Grazing Binary)"
        │           "Verified Planet Candidate (Atmospheric Occultation Detected)"
        │           "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
        │
        ├─6. PHYSICAL PROPERTIES
        │    PhysicalPropertiesEngine.derive(             detection.py:115
        │       best_period, transit_depth_fraction,
        │       st_rad, st_teff, st_mass, sy_jmag)
        │      -> radius, mass, semi-major axis, equilibrium temp, ...
        │
        ├─7. TTV ANALYSIS
        │    TTVAnalyzer.calculate(...)                   detection.py:119
        │      -> ttv_data (O-C residuals)
        │
        ├─   save_experiment_log(...)                     detection.py:124
        │
        └─   if strong candidate (snr > 7.0):
              BLSSearchEngine.mask_transit(...)           detection.py:138
                -> subtract this transit, loop for next planet
             else: break
```

**Engines involved** (all in `astraeus/analysis/`): `DetrendingEngine`
(`detrending.py`), `BLSSearchEngine` (`bls_search.py`),
`GeometricValidator` (`geometric_validation.py`), `VettingEngine`
(`vetting.py`), `PhysicalPropertiesEngine` (`physical_properties.py`),
`TTVAnalyzer` (`ttv_analysis.py`), plus `save_experiment_log` (`logging.py`).

> Out of scope for Bucket 1: the physics/solver modules under `astraeus/core/`
> and `astraeus/analysis/` engine internals are documented here for
> orientation only and were not modified.

---

## 5. Quick reference — where things live

| Concern | Location |
|---|---|
| Streamlit entry point | `app.py` (root) |
| Routing (non-Discover tabs) | `route.py` |
| Feature pages | `ui/pages/{simulator,lab,detective,history,settings}.py` |
| Shell / layout / theme / chat | `astraeus/dashboard/ui/{layout,styles,components}.py` |
| Settings panel | `astraeus/dashboard/ui/settings.py` |
| Simulation figures + model | `astraeus/dashboard/{figures,simulation}.py` |
| Ingestion (the one engine) | `astraeus/core/ingestion.py::RemoteDiscoveryEngine` |
| Detection pipeline | `astraeus/analysis/detection.py::detect_transit_candidate` |
| Multi-planet orchestrator | `astraeus/core/orchestrator.py::run_multi_planet_search` |
| Experiment logging | `astraeus/analysis/logging.py` |
| PDF manuscript export | `astraeus/analysis/reporting.py::generate_academic_report` |
| Deprecated code | `deprecated/` (excluded from pytest via `pytest.ini --ignore=deprecated`) |

---

## Verification

This document reflects the import graph as verified in Bucket 1 (Phase 1
discovery, `reports/bucket1_orphan_investigation.md`) by reading import
statements directly, not by guessing from filenames. To re-verify the live
entry path after future changes:

```bash
streamlit run app.py          # must launch; sidebar nav routes all 6 tabs
python -m pytest tests/ -v    # regression gate (see reports/bucket1_posttest.txt)
```

To find what imports a given module, prefer the CodeGenome MCP
(`get_neighbors`) when available; otherwise ripgrep the module path and its
exported symbols across the repo.
