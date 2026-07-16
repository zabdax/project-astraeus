# PROJECT ASTRAEUS — Complete Knowledge Base

> **Purpose:** This is the *single source of truth* for the entire Project Astraeus codebase. Written for any AI model (or human) that needs to understand, modify, debug, or extend the project. It captures the full architecture, every module's purpose and contract, the live launch path, all known bugs / fixes / quirks, and the conventions every contributor must follow.
>
> **Branch in sync with this doc:** `v.0.0.2` (live entry path) + R7-R8 round-2 diagnostic fixes (2026-07-06 → 2026-07-12).
> **Python:** 3.10+ (tested on 3.11/3.12).
> **Primary author:** Zubayer Hasan Shaad ("ZUXLO"). MIT-licensed.
>
> **How to read this:** Sections 1–6 give orientation. Sections 7–23 are the deep module-by-module reference. Section 24 covers tests/CI. Section 25 enumerates the post-briefing changes. Sections 26–32 cover conventions, dead code, environment, roadmap, and the Q&A guide. If you only have 2 minutes, read §3 (live launch path), §8 (detection pipeline), and §32 (Q&A guide).

---

## Table of Contents

1. [What this project is](#1-what-this-project-is)
2. [Tech stack and runtime context](#2-tech-stack-and-runtime-context)
3. [The ONE live launch path](#3-the-one-live-launch-path)
4. [Top-level layout (complete)](#4-top-level-layout-complete)
5. [The 6 dashboard tabs](#5-the-6-dashboard-tabs)
6. [Data ingestion — one engine, two entry points](#6-data-ingestion--one-engine-two-entry-points)
7. [The analysis pipeline — overview](#7-the-analysis-pipeline--overview)
8. [`detect_transit_candidate` — the scientific core](#8-detect_transit_candidate--the-scientific-core)
9. [BLS Search Engine — the periodogram workhorse](#9-bls-search-engine--the-periodogram-workhorse)
10. [TLS cross-validation](#10-tls-cross-validation)
11. [Detrending Engine](#11-detrending-engine)
12. [Vetting engines — U/V shape, geometry, physical properties](#12-vetting-engines--uv-shape-geometry-physical-properties)
13. [TTV (Transit Timing Variation) analysis](#13-ttv-transit-timing-variation-analysis)
14. [N-body solver](#14-n-body-solver)
15. [Multi-planet orchestrator](#15-multi-planet-orchestrator)
16. [Simulation layer](#16-simulation-layer)
17. [PDF manuscript export](#17-pdf-manuscript-export)
18. [Experiment tracking and logging](#18-experiment-tracking-and-logging)
19. [LLM gateway and AI co-pilot](#19-llm-gateway-and-ai-co-pilot)
20. [The dashboard shell (layout, components, settings)](#20-the-dashboard-shell-layout-components-settings)
21. [LightkurveClient — the data acquisition layer in depth](#21-lightkurveclient--the-data-acquisition-layer-in-depth)
22. [NASA Exoplanet Archive client](#22-nasa-exoplanet-archive-client)
23. [Time-unit normalization](#23-time-unit-normalization)
24. [Constants, configuration, and key data classes](#24-constants-configuration-and-key-data-classes)
25. [The test surface and CI](#25-the-test-surface-and-ci)
26. [Round-7 / Round-8 fixes log (post-v0.0.2 briefing)](#26-round-7--round-8-fixes-log-post-v002-briefing)
27. [Deprecated / dead paths — DO NOT IMPORT](#27-deprecated--dead-paths--do-not-import)
28. [What is WORKING right now (verified)](#28-what-is-working-right-now-verified)
29. [Known rough edges, placeholders, and open issues](#29-known-rough-edges-placeholders-and-open-issues)
30. [Conventions, env vars, branch hygiene, commit style](#30-conventions-env-vars-branch-hygiene-commit-style)
31. [Known breakage points](#31-known-breakage-points)
32. [Dev infrastructure, tooling, and roadmap](#32-dev-infrastructure-tooling-and-roadmap)
33. [Question-answering guide for a downstream AI](#33-question-answering-guide-for-a-downstream-ai)

---

## 1. What this project is

**Project ASTRAEUS** ("Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space") is a physics-first computational astrophysics platform for **exoplanet transit modeling**, **multi-planet discovery**, **MCMC Bayesian parameter retrieval**, **N-body stability analysis**, and **AI-assisted analysis**, packaged inside an interactive **Streamlit dashboard** with a floating AI chat co-pilot and one-click PDF manuscript export.

Tagline (from README): *"Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space."*

### Core research question

> *How accurately can exoplanet transit parameters be recovered from noisy photometric data using first-principles modeling?*

The answer is computed by building the physics from scratch: Kepler's equation, sky-plane transit geometry, limb-darkened flux integrals, multi-planet iterative BLS subtraction, TTV extraction, N-body dynamics, and finally Markov Chain Monte Carlo (MCMC) posterior sampling — **with no black-box ML shortcuts**.

### Core principles (from README)

- Every model has an explicit physical derivation — no black-box ML shortcuts
- All assumptions and parameter bounds are documented and validated
- Results are fully reproducible from raw data to final figures
- Uncertainties are always propagated (MCMC credible intervals, not just point estimates)
- Vetting thresholds live as named constants in `astraeus/core/constants.py` — magic numbers get extracted on every bucket refactor

### What is NOT in scope (aspirational, NOT implemented)

- **`prd_v2.md`** ("Version 2.0" PRD) describes a Next.js + TypeScript + Three.js frontend with FastAPI backend, PostgreSQL, Qdrant, LangGraph/LangChain. **None of this is built.** The actual codebase is the Streamlit/Python stack described here. The v2 PRD is aspirational portfolio vision.

---

## 2. Tech stack and runtime context

### Language & frameworks

| Layer | Tech | Version | Role |
|---|---|---|---|
| Language | Python | 3.10+ (tested 3.11/3.12) | Whole codebase |
| UI | Streamlit | 1.41.1 | Interactive multi-page dashboard |
| Charts | Plotly | 5.24.1 | Interactive 3D orbits + light curves |
| Charts | Matplotlib | 3.10.9 | Static scientific figures + Agg-rasterized PDF chart fallback |
| Numerics | NumPy | 2.2.6 | All array math; **all light-curve arrays are float64** |
| Numerics | SciPy | 1.15.3 | `scipy.optimize.curve_fit` for vetting, `scipy.ndimage.median_filter` for detrend fallback, `scipy.integrate.quad_vec` for limb-darkened flux |
| Astronomy | Astropy | 6.1.7 | Units, `BoxLeastSquares` (BLS), `LombScargle`, `SkyCoord` |
| Data | Lightkurve | ≥ 2.4.0 | MAST / NASA archive client |
| Data | Pandas | 2.2.3 | DataFrame manipulation |
| Network | requests | 2.32.3 | Direct MAST/S3/TAP HTTP |
| Cloud | boto3 | ≥ 1.28.0 | AWS S3 unsigned (MAST stpubdata fallback) |
| MCMC | emcee | 3.1.6 | Ensemble sampler (used in `error_analysis.py`, currently off the live UI path) |
| PDF | reportlab | ≥ 4.1.0, < 4.2.0 | PDF manuscript generation |
| PDF charts | kaleido | 0.2.1 | Plotly → PNG for PDF embedding (graceful fallback to Matplotlib if missing) |
| Transit sim | batman | (optional) | High-precision trapezoidal subtraction; falls back to in-house Trapezoidal model if unavailable |
| Detrending | wotan | (optional) | Biweight time-windowed detrending; falls back to median filter if unavailable |
| TLS | transitleastsquares | (optional) | Cross-validation of BLS candidates; NOT in `requirements.txt` |

### Environment variables

| Var | Default | Purpose |
|---|---|---|
| `ASTRAEUS_LIGHTKURVE_CACHE_DIR` | `<tmp>/astraeus_lightkurve_cache` | Cache root for the `LightkurveClient` |
| `ASTRAEUS_FORCE_NETWORK` | (unset) | When set to `"1"`, the cache-first fallback in `_try_serve_from_cache` is **bypassed** — used by the QA harness to exercise the dynamic MAST/S3 path |
| `GOOGLE_API_KEY` | (none) | LLM gateway provider key |
| `OPENAI_API_KEY` | (none) | LLM gateway provider key |
| `ANTHROPIC_API_KEY` | (none) | LLM gateway provider key |
| (Ollama) | (none) | Local daemon on `localhost:11434` |

### Test markers (`pytest.ini`)

- `@smoke` — fast end-to-end pipeline smoke tests (sub-minute CI gate)
- `@network` — tests requiring live network access (NASA Exoplanet Archive, MAST)
- `@slow` — long-running tests (stress, bench, multi-minute)
- `--ignore=deprecated` — pytest collection excludes everything under `deprecated/`

---

## 3. The ONE live launch path

```text
$ streamlit run app.py                        # PROJECT ROOT
        │
        ▼
   app.py
        │
        ├─ astraeus/dashboard/ui/layout.py::workbench_layout()         # 3-panel workbench + left nav
        ├─ astraeus/dashboard/ui/styles.py::inject_page_styles()       # page-level CSS
        ├─ astraeus/dashboard/ui/components.py::render_floating_chat() # bottom-right AI chat popover
        │
        ├─ if selected_feature == "Discover":  INLINE in app.py:235-360
        │      └─ detective-style ledger view of pre-computed candidates
        │         (sidebar: SNR threshold slider, "Dual-Zone Grid: ACTIVE"
        │          placeholder, "Manuscript Export" button → generate_academic_report)
        │
        └─ else: route.py::render_route(feature, ...)
              ├─ Simulation   → ui/pages/simulator.py
              ├─ Lab          → ui/pages/lab.py
              ├─ Detective    → ui/pages/detective.py
              ├─ History      → ui/pages/history.py
              └─ Settings     → ui/pages/settings.py
```

### Critical for any downstream model

**`astraeus/ui/dashboard.py`** and any path beginning with `astraeus/ui/` is **DEAD** — moved to `deprecated/astraeus_ui_dashboard/` in Bucket 1. Do **NOT** import from `astraeus.ui.*`. The live UI is `app.py` at project root.

The **live `app.py`** imports:
- `astraeus.core.orchestrator.{submit_multi_planet_search, get_job_status, cancel_job, JobState}` (multi-planet search as a background job)
- `astraeus.simulation.synthetic.{SyntheticTransitScenario, generate_synthetic_transit_series}` (demo data for the "Run Live Analysis" button)
- `astraeus.dashboard.ui.{layout.workbench_layout, styles.inject_page_styles, components.render_floating_chat}`
- `astraeus.analysis.reporting.generate_academic_report` (PDF manuscript)
- `route.render_route` (page dispatch for non-Discover tabs)

The `app.py` Discover tab is **hard-coded** to a `BASELINE_PAYLOAD` (4 pre-computed Kepler-90 candidates) at `app.py:29-38`. It does **not** invoke the discovery pipeline — it just renders the static payload. The real discovery happens in the **Detective** tab.

---

## 4. Top-level layout (complete)

```text
project-astraeus/                                   # working tree root
│
├── app.py                                          # ONLY live Streamlit entry point
├── route.py                                        # Routes non-Discover tabs to ui/pages/*
├── config.json                                     # LLM provider + API keys (NO keys set in repo)
├── requirements.txt                                # Runtime deps
├── requirements-dev.txt                            # Dev/QA deps (pytest, etc.)
├── pytest.ini                                      # markers @smoke, @slow, @network; --ignore=deprecated
├── pytest_out.txt, pytest_pipeline.log, *.log      # Test run traces (root dir)
├── err.log, err2.log                               # Historical stderr traces from LightkurveClient
├── error.log                                       # empty
│
├── ui/                                             # Live Streamlit feature pages
│   └── pages/
│       ├── simulator.py                            # Simulation Workbench
│       ├── lab.py                                  # Lab (sensitivity_engine)
│       ├── detective.py                            # Detective (multi-planet discovery)
│       ├── history.py                              # Experiment history viewer
│       └── settings.py                             # Settings panel
│
├── astraeus/                                       # Core Python package
│   ├── main.py                                     # CLI: RealDataPipeline (TrES-2b Kepler Q1)
│   │
│   ├── core/                                       # Physics + data engine
│   │   ├── __init__.py                             # Re-exports
│   │   ├── config.py                               # JSON config loader + validator
│   │   ├── constants.py                            # ⭐ ALL vetting/detection thresholds
│   │   ├── geometry.py                             # Circle overlap & sky-separation
│   │   ├── ingestion.py                            # RemoteDiscoveryEngine (Streamlit + headless)
│   │   ├── kepler.py                               # Newton-Raphson Kepler equation solver
│   │   ├── lightkurve_client.py                    # ⭐ LightkurveClient (MAST, S3, cache-first)
│   │   ├── llm_gateway.py                          # LLMClient (provider-agnostic)
│   │   ├── nasa_archive.py                         # NASAExoplanetArchive (TAP pscomppars)
│   │   ├── nbody_solver.py                         # ⭐ Pure-numpy Symplectic Velocity Verlet
│   │   ├── orbital_models.py                       # calculate_orbital_position
│   │   ├── orbits.py                               # KeplerianOrbit
│   │   ├── orchestrator.py                         # ⭐ run_multi_planet_search + async submit
│   │   ├── sensitivity_engine.py                   # Fast uniform-disk transit model
│   │   ├── time_units.py                           # to_bjd() — mission epoch → BJD full
│   │   ├── transit_model.py                        # Limb-darkened flux (generate_model_flux)
│   │   ├── validation.py                           # require_*_quantity() helpers
│   │   │
│   │   └── clients/                                # Phase 0 SOLID refactor seams (LIVE, not yet wired)
│   │       ├── __init__.py                         # Package init
│   │       ├── _clock.py                           # ClockPort, RealClock
│   │       ├── _fs.py                              # FsPort, RealFs
│   │       ├── _net.py                             # HttpClientPort, RequestsHttpClient, HttpResponse + fixture recorder CLI
│   │       └── lightkurve_row.py                   # LightkurveRowPort (narrow surface)
│   │
│   ├── data/                                       # Local ingest + adapter
│   │   ├── __init__.py                             # re-exports
│   │   ├── adapter.py                              # DataAdapter (CSV/JSON/FITS → {time, flux, flux_err, metadata})
│   │   ├── loader.py                               # DataFactory (Strategy: NASAArchiveLoader/CSVLoader/JSONLoader)
│   │   └── preprocessing.py                        # inject_gaussian_noise, etc.
│   │
│   ├── simulation/                                 # Synthetic + completeness sweep
│   │   ├── __init__.py                             # Re-exports
│   │   ├── synthetic.py                            # SyntheticTransitScenario, generate_synthetic_transit_series, run_injection_recovery
│   │   └── completeness.py                         # ⭐ CompletenessSweepConfig, run_completeness_sweep
│   │
│   ├── analysis/                                   # Detection/fitting/reporting (scientific core)
│   │   ├── __init__.py                             # Re-exports
│   │   ├── bls_search.py                           # ⭐ BLSSearchEngine (autoperiod, alias rejection)
│   │   ├── detection.py                            # ⭐⭐ detect_transit_candidate (the entry point)
│   │   ├── detrending.py                           # DetrendingEngine (Lomb-Scargle + Wotan biweight)
│   │   ├── error_analysis.py                       # MCMC posterior sampling (emcee)
│   │   ├── explanation.py                          # LLM-driven scientific interpretation
│   │   ├── fitting.py                              # Model fitting utilities
│   │   ├── geometric_validation.py                 # GeometricValidator (secondary eclipse, flat-bottom)
│   │   ├── logging.py                              # ExperimentLedger (atomic JSON writes)
│   │   ├── optimization.py                         # MAP estimation
│   │   ├── physical_properties.py                  # PhysicalPropertiesEngine
│   │   ├── reporting.py                            # ⭐ generate_academic_report (PDF)
│   │   ├── ttv_analysis.py                         # TTVAnalyzer (O-C residuals)
│   │   ├── ttv_nbody_validation.py                 # N-body vs extracted TTV cross-check
│   │   └── vetting.py                              # VettingEngine (U-vs-V shape, chi²-Δ)
│   │
│   ├── visualization/                              # Matplotlib static figures
│   │   ├── __init__.py                             # Re-exports
│   │   └── plots.py                                # plot_completeness_map, etc.
│   │
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── pipeline.py                             # RealDataPipeline (the CLI orchestrator)
│   │
│   ├── dashboard/                                  # Shared library imported by app.py + ui/pages
│   │   ├── __init__.py
│   │   ├── figures.py                              # make_light_curve_figure, make_residuals_figure, make_multi_orbit_animation_html
│   │   ├── scenario.py                             # DashboardTransitScenario dataclass
│   │   ├── simulation.py                           # DashboardSimulation, generate_dashboard_simulation
│   │   ├── validation.py                           # validate_scenario, generate_stable_seed
│   │   │
│   │   ├── ui/                                     # LIVE shell
│   │   │   ├── __init__.py
│   │   │   ├── layout.py                           # workbench_layout(), render_left_nav(), apply_astro_theme()
│   │   │   ├── styles.py                           # inject_page_styles()
│   │   │   ├── components.py                       # render_floating_chat() (popover)
│   │   │   └── settings.py                         # render_settings_panel()
│   │   │
│   │   └── services/                               # ORPHANED / NOT touched by Bucket 1
│   │       ├── __init__.py
│   │       ├── action_deck.py
│   │       ├── data_ingestion.py
│   │       └── mcmc_retrieval.py
│   │
│   └── logs/
│       └── research_log.md                         # Stub
│
├── tests/                                          # 35+ pytest files + conftest
│   ├── conftest.py                                 # Resets Streamlit DeltaGeneratorSingleton
│   ├── qa_init.py, qa_all.py, qa_case.py           # QA harness
│   ├── simulate_backend.py                         # Backend simulation runner
│   ├── test_adapter.py, test_loader.py             # DataAdapter / DataFactory
│   ├── test_agent_detective.py                     # Detective agent routing + noise injection
│   ├── test_bulletproof_detector.py                # Mathematical aliasing, state binding safety
│   ├── test_chaos_integration_suite.py             # Chaos integration
│   ├── test_completeness_sweep.py                  # Completeness sweep
│   ├── test_dashboard_simulation.py                # Dashboard sim
│   ├── test_debug_metadata_network.py              # Network metadata debug
│   ├── test_experiment_history.py                  # History ledger
│   ├── test_fetched_analyze_button.py              # Detective "Analyze Telemetry" button flow
│   ├── test_global_matrix_stress_test.py           # Global stress (parametrized)
│   ├── test_i1_classifier_multiplanet.py            # Round-2 I1 fix
│   ├── test_i2_bjd_unit.py                         # Round-2 I2 fix: BJD unit
│   ├── test_i3_hostname_alias.py                   # Round-2 I3 fix: NASA hostname aliases
│   ├── test_i4_apptest_smoke.py                    # Round-2 I4 fix: AppTest smoke
│   ├── test_j1_alias_rejection.py                  # Round-2 J1: BLS window-aware alias rejection
│   ├── test_j2_orchestrator_states.py              # Round-2 J2: orchestrator state machine
│   ├── test_j3_bls_single_signal_regression.py     # Round-2 J3: BLS single-signal regression
│   ├── test_j3_orchestrator_e2e_verified.py        # Round-2 J3: orchestrator E2E
│   ├── test_j3_syn5p_small_recovery.py             # Round-2 J3: SYN-5P small recovery
│   ├── test_lab_realtime.py                        # Sensitivity Lab realtime
│   ├── test_mcmc.py                                # MCMC unit tests
│   ├── test_multi_planet_scaling.py                # Multi-planet scaling
│   ├── test_multi_planet_search_real_data.py       # Kepler-90b real-data scenario
│   ├── test_nasa_archive_network.py                # NASA archive network tests (@network)
│   ├── test_nbody_solver.py                        # N-body Kepler-90b 6-planet
│   ├── test_orbital_models.py                      # Orbital mechanics
│   ├── test_physics.py                             # First-principles physics
│   ├── test_pipeline_smoke.py                      # E2E smoke (Bucket 6)
│   ├── test_pipeline_stress_test.py                # Pipeline stress
│   ├── test_preprocessing.py                       # Preprocessing
│   ├── test_r8_vetting_override_regression.py      # Round-2 R8: "Likely Planet" override gated on is_valid
│   ├── test_solid_matrix_diagnostic.py             # SOLID matrix diagnostic
│   ├── test_synthetic_simulation.py                # Synthetic sim
│   ├── test_system_flight_bench.py                 # System flight bench (@smoke + @slow)
│   ├── test_transit_model.py                       # Transit model
│   ├── test_ttv_nbody_validation.py                # TTV vs N-body
│   ├── test_ui_flow.py                             # UI flow (file_uploader mock — Bucket 8 fix)
│   ├── test_vetting_threshold_hardening.py         # 9 threshold tests (Bucket 2)
│   └── test_workbench_navigation.py                # Workbench nav
│
├── scripts/                                        # QA runners + manual tests
│   ├── qa_runner.py                                # v1 runner
│   ├── qa_runner_v2.py                             # v2 runner (cached + dynamic dual-mode)
│   ├── qa_targets.yaml                             # manifest of targets
│   ├── README.md
│   └── manual_tests/                               # Awaiting pytest conversion
│
├── docs/
│   ├── ARCHITECTURE.md                             # Authoritative architecture doc
│   ├── astraeus_agent_implementation_briefs.md     # ⭐ Round-2 R7-R8 diagnostic briefs
│   ├── round-8-plan.md                             # ⭐ Round-8 plan with full bucket specs (Buckets 0-10)
│   └── superpowers/
│       ├── plans/                                  # 3 implementation plans
│       │   ├── 2026-06-23-completeness-sweep.md
│       │   ├── 2026-06-27-qa-v2-dual-mode.md
│       │   └── 2026-06-30-data-ingestion-solid-refactor.md
│       └── specs/                                  # 3 design specs
│           ├── 2026-06-23-completeness-sweep-design.md
│           ├── 2026-06-27-qa-v2-dual-mode-design.md
│           └── 2026-06-30-data-ingestion-solid-refactor-design.md
│
├── dev-knowledge-base/                             # (empty in working tree)
│
├── deprecated/                                     # 3 deprecated clusters (pytest --ignore)
│   ├── debug_metadata_network.py
│   ├── global_matrix_stress_test.py
│   ├── pipeline_stress_test.py
│   ├── run_test.py
│   ├── solid_matrix_diagnostic.py
│   ├── system_flight_bench.py
│   ├── test_engine.py
│   ├── test_fetch.py
│   ├── test_ingest.py
│   ├── test_nasa.py
│   ├── test_orchestrator.py
│   ├── trace_download_deadlock.py
│   ├── astraeus_ui_dashboard/                      # Old `astraeus/ui/dashboard.py` copy
│   ├── astraeus_dashboard_ui/                      # Old dead dashboard panels
│   └── astraeus_data_discovery/                    # Second RemoteDiscoveryEngine (replaced)
│
├── logs/                                           # experiments.json ledger + QA/streamlit logs
├── outputs/                                        # Sweep artifacts etc.
├── reports/                                        # Generated audit reports (gitignored)
├── runs/                                           # Runtime outputs (gitignored)
│
├── .genome/                                        # CodeGenome MCP cache (MUST use MCP first)
├── .cursor/                                        # Cursor IDE settings
├── .github/                                        # GitHub Actions CI workflows (Bucket 5)
├── .streamlit/                                     # Streamlit config
├── .pytest_cache/
├── .agents/                                        # Agent infrastructure
└── __pycache__/
```

---

## 5. The 6 dashboard tabs

| Tab | Where | What it does | Live imports |
|---|---|---|---|
| **Discover** (default landing) | inline in `app.py:235-360` | Pre-computed Kepler-90 candidates ledger + SNR slider + Generate Manuscript PDF button + per-candidate phase-folded synthetic plot. **Dual-Zone Grid: ACTIVE** and **1.5x Wing Subtraction: ACTIVE** are static UI labels in `app.py:259-260`, NOT live toggles. The phase-folded figures are synthesized from the candidate dict (deterministic seeded `np.random.default_rng`), NOT derived from real photometry. | `astraeus.dashboard.ui.{layout,styles,components}`, `astraeus.analysis.reporting.generate_academic_report`, `astraeus.core.orchestrator.{submit_multi_planet_search, get_job_status, cancel_job, JobState}`, `astraeus.simulation.synthetic.{SyntheticTransitScenario, generate_synthetic_transit_series}` |
| **Simulation** | `ui/pages/simulator.py` | Interactive orbital parameters (sliders for radius ratio, period, eccentricity, inclination, SNR). Live 3D orbit viewer + simulated light curve + residuals. SVG icon styling. Supports multi-planet (Add Planet button). | `astraeus.dashboard.figures.{make_light_curve_figure, make_residuals_figure, make_multi_orbit_animation_html}`, `astraeus.core.transit_model.generate_multi_planet_transit`, `astraeus.dashboard.simulation.semi_major_axis_for_solar_mass`, `astraeus.data.preprocessing.inject_gaussian_noise`, `astraeus.core.orbital_models.calculate_orbital_position` |
| **Lab** | `ui/pages/lab.py` | Sensitivity Lab: sliders (radius ratio, inclination, period, a/Rs, limb darkening) to fit a model to a reference dataset. Uses `get_model_curve` from `sensitivity_engine.py` — high-speed, vectorized uniform-disk transit. | `astraeus.core.sensitivity_engine.get_model_curve` |
| **Detective** | `ui/pages/detective.py` | Real-data discovery. Pulls via `RemoteDiscoveryEngine.fetch_data`, runs `run_multi_planet_search`. Supports file upload for CSV/JSON/FITS via `DataAdapter`. Dual-Zone Hybrid Grid BLS (1.5× wing padding). | `astraeus.analysis.detection.detect_transit_candidate`, `astraeus.core.orchestrator.run_multi_planet_search`, `astraeus.core.ingestion.{RemoteDiscoveryEngine, DataAdapter}`, `astraeus.data.adapter.DataAdapter` |
| **History** | `ui/pages/history.py` | Loads `logs/experiments.json`. Shows dataframe + Restore buttons (per-experiment). | `astraeus.analysis.logging.load_experiment_history` |
| **Settings** | `ui/pages/settings.py` | Thin wrapper around `render_settings_panel` — LLM provider / API key form. | `astraeus.dashboard.ui.settings.render_settings_panel` |

---

## 6. Data ingestion — one engine, two entry points

**Single source of truth:** `astraeus/core/ingestion.py::RemoteDiscoveryEngine` (line 24).

```text
RemoteDiscoveryEngine (stateless facade)
   ├─ _fetch_data_impl(target, mission)              # pure-Python, no Streamlit dependency
   │      ├─ NASAExoplanetArchive.normalize_target_name(target)
   │      ├─ NASAExoplanetArchive.fetch_metadata(canonical)  # TAP pscomppars
   │      │
   │      └─ if mission == "NASA Exoplanet Archive":
   │             └─ _bridge_to_time_series(...)     # resolves Kepler-N → TIC, then tries TESS then Kepler
   │         elif mission in TESS/Kepler variants:
   │             └─ LightkurveClient.download_pipeline(target, "TESS"/"Kepler")
   │         elif mission == "Combined Baseline (Kepler + TESS)":
   │             └─ LightkurveClient.download_combined_fusion(pl_name)
   │
   └─ fetch_data(target, mission)                   # @st.cache_data(ttl=3600) wrapper
          └─ attached dynamically at module load; lazy `import streamlit as st`
             inside the function body so headless scripts never pay the cost.
```

### Why one engine covers both contexts

`_fetch_data_impl` is Streamlit-free, so headless stress/diagnostic scripts call it directly. The `@st.cache_data` wrapper lives only in the separate `_cached_fetch_data` function (`ingestion.py:217`), which does `import streamlit as st` *lazily inside its body* — so it is only engaged when called from an active Streamlit script context.

### Mission routing table

| `mission` arg | Behavior |
|---|---|
| `"Kepler"` (and variants) | `LightkurveClient.download_pipeline(target, "Kepler")` |
| `"TESS"` (and variants) | `LightkurveClient.download_pipeline(target, "TESS")` |
| `"Combined Baseline (Kepler + TESS)"` | `LightkurveClient.download_combined_fusion(pl_name)` |
| `"NASA Exoplanet Archive"` | Metadata-only — **bridged** into TESS then Kepler via `_bridge_to_time_series` (FIX 1) |

### NASA Archive bridge (FIX 1)

When the user picks "NASA Exoplanet Archive" (which is metadata-only), the engine:
1. Normalizes the target name (`Kepler-13 b` → `Kepler-13 b`, `WASP-12b` → `WASP-12 b`).
2. Resolves to a MAST-searchable target via `_resolve_mission_target` — strips planet letter, matches prefixes (kepler-N, k2-N, tic, toi, kic, wasp, hat-p, tres, xo, kelt, gj, hd, hip, tyc).
3. Tries TESS first, falls back to Kepler.
4. Returns a `no_time_series` result with reason tag (`"Network Timeout"`, `"Target not observed"`, etc.) if both fail.

### Underlying pieces

- **`astraeus/core/nasa_archive.py::NASAExoplanetArchive`** — TAP client for `pscomppars` (and `ps` fallback for `pl_orbper`). Target name normalizer, metadata sanitizer, special-case hostname aliases.
- **`astraeus/core/lightkurve_client.py::LightkurveClient`** — MAST client. ~970 lines. See §21 for the deep dive.
- **`astraeus/core/time_units.py::to_bjd`** — Mission-specific time offset (BKJD for Kepler = BJD - 2454833, BTJD for TESS = BJD - 2457000) → BJD full. **I2 fix** (2026-07-06).

---

## 7. The analysis pipeline — overview

**`astraeus/analysis/detection.py::detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT, known_periods=None)`** runs, in order:

```
1. DETREND
   DetrendingEngine.estimate_stellar_rotation(time, flux)  → rotation period (days)
   DetrendingEngine.detrend(time, flux, rotation_period)   → smooth flux baseline

2. BLS SEARCH
   BLSSearchEngine.search(active_time, active_flux, known_periods=known_periods)
   → {period, snr, depth, t0, duration, confidence_score, periodogram}
   ── Window-aware alias rejection (J1b/J1c fixes) ──
   ── Duty-cycle physical mask (J3 fix, max 20%)    ──
   ── 5%-margin rejection near p_min / p_max (J3)   ──

3. TLS CROSS-VALIDATION  (J2c fix, 2026-07-06)
   if best_period > 0:
       try: transitleastsquares.transitleastsquares(active_time, active_flux)
            .power(period_min=best_period*0.95, period_max=best_period*1.05,
                   show_progress_bar=False, use_threads=1)   ← MUST be 1 (nested pool)
            → {FAP, SDE, period}
            tls_valid = (tls_sde >= 5.0 and |tls_period - best_period|/best_period < 0.05)
   ── THREE possible outcomes (J2c) ──
       tls_valid=True            → scientific success
       tls_valid=False,
         tls_environment_error   → "infra failure" (AssertionError / RuntimeError on Windows)
       tls_valid=False,
         tls_scientific_error    → "scientific failure" (numba, NaN, etc.)
       tls_valid=True            → ImportError: transitleastsquares missing (fail-open)

4. EMISSION GATE  (the candidate-emission decision)
   is_valid = (best_snr > snr_threshold
               and best_confidence >= DETECTION_CONFIDENCE_FLOOR
               and tls_valid)
   where DETECTION_CONFIDENCE_FLOOR = 7.0 (empirically fit; bucket 9.1)
         DETECTION_SNR_THRESHOLD_DEFAULT = 5.0 (reverted from 7 in bucket 9.2)

5. GEOMETRIC VALIDATION
   GeometricValidator.validate(active_time, active_flux, best_period, t0, duration, depth_fraction)
   → {v_shape_metric, flat_bottom_fraction, secondary_eclipse_depth,
      secondary_eclipse_snr, secondary_eclipse_detected}

6. VETTING (U-shape vs V-shape; bucket 10 hardening)
   VettingEngine.vet_transit_shape(active_time, active_flux, best_period, t0, duration,
                                   depth_fraction, snr=best_snr,
                                   threshold=VETTING_U_VS_V_CHI2_DELTA_THRESHOLD)
   → {vetting_status, vetting_confidence, u_shape_chi2, v_shape_chi2, delta_chi2_u, delta_chi2_v}
   result['v_shape_metric'] = 1.0 - vetting_confidence  (back-compat key)

7. PHYSICAL PROPERTIES  (BEFORE cross-vetting so the secondary-eclipse branch
                          can use a physically-grounded threshold — bucket 2)
   PhysicalPropertiesEngine.derive(period, depth_fraction, st_rad, st_teff, st_mass, sy_jmag)
   → {planet_radius_earth, equilibrium_temp_k, jwst_tsm_score}
   PhysicalPropertiesEngine.expected_occultation_depth_ppm(...)  → float | None
       if None → use VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM (800 ppm)
       else    → use physical value

8. FALSE-POSITIVE CROSS-VETTING (decision tree, R8 fix, I1 fix)
   Runs UNCONDITIONALLY on every peak (not gated on is_valid)
   fusing depth + V-shape + secondary-eclipse + ultra-short period
   → ONE OF:
     "Verified Planet Candidate"
     "Eclipsing Binary Detected"
     "V-Shaped False Positive Risk (Potential Grazing Binary)"
     "Verified Planet Candidate (Atmospheric Occultation Detected)"
     "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"

9. TTV ANALYSIS
   TTVAnalyzer.calculate(active_time, active_flux, best_period, t0, duration)
   → ttv_data (list of {epoch, ttv_residual_min} dicts)

10. EXPERIMENT LOG
    save_experiment_log(params, metadata, fig_paths)  → appends to logs/experiments.json
```

Result is also written to `logs/experiments.json` (UUID + SHA256 dataset hash) via `save_experiment_log`.

### Result dict (key reference)

The full return dict (used by `app.py`, `ui/pages/detective.py`, `orchestrator.py`, and downstream consumers):

| Key | Type | Notes |
|---|---|---|
| `candidate_found` | bool | Mirrors `is_valid` (the emission gate) |
| `is_candidate` | bool | Mirror of `candidate_found` (back-compat) |
| `period_days` / `period` / `orbital_period` | float | Three back-compat aliases |
| `stellar_rotation_period_days` | float | From `DetrendingEngine.estimate_stellar_rotation` |
| `transit_depth` | float | Fractional depth |
| `stellar_radius` | float | From metadata (`st_rad` or `stellar_radius`) |
| `vetting_status` | str | The decision-tree result (see step 8 above) |
| `confidence_score` | float | From `BLSSearchEngine.search` (periodogram peak / median) |
| `snr` | float | From BLS |
| `depth` | float | Same as `transit_depth` (back-compat) |
| `duration` | float | Days |
| `t0` | float | Mid-transit time |
| `t0_bjd` | float | Explicit BJD-full t0 (I2 fix, 2026-07-06) |
| `time_unit` | str | Always `"BJD"` (I2 fix) |
| `periodogram` | dict | `{periods: [...], powers: [...]}` |
| `tls_fap` | float | TLS false-alarm probability |
| `tls_sde` | float | TLS signal-detection efficiency |
| `tls_period` | float | TLS best period |
| `tls_valid` | bool | True if TLS confirmed the BLS candidate |
| `tls_environment_error` | str \| None | Set if `(AssertionError, RuntimeError)` (J2c fix) |
| `tls_scientific_error` | str \| None | Set if any other `Exception` (J2c fix) |
| `vetting_confidence` | float | 0-1 |
| `u_shape_chi2` / `v_shape_chi2` | float | chi² fits |
| `delta_chi2_u` / `delta_chi2_v` | float | `chi2_flat - chi2_model` |
| `v_shape_metric` | float | `1.0 - vetting_confidence` (back-compat) |
| `planet_radius_earth` | float | R_p in Earth radii |
| `equilibrium_temp_k` | float | Day-side equilibrium T |
| `jwst_tsm_score` | float | Kempton TSM (transmission spectroscopy metric) |
| `secondary_eclipse_threshold_ppm` | float | Threshold actually used (800 fallback or physical) |
| `secondary_eclipse_threshold_mode` | str | `"fallback_fixed"` or `"physical"` |
| `ttv_data` | list | O-C residuals from TTVAnalyzer |

---

## 8. `detect_transit_candidate` — the scientific core

File: `astraeus/analysis/detection.py` (381 lines).

### Function signature

```python
def detect_transit_candidate(
    time, flux,
    target_name="Unknown",
    data_source="Unknown",
    metadata=None,
    snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT,  # = 5.0
    known_periods=None,
):
    if known_periods is None:
        known_periods = []
    ...
```

### Imports

```python
import numpy as np
from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.analysis.logging import save_experiment_log
from astraeus.analysis.vetting import VettingEngine
from astraeus.core.constants import (
    VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION,
    VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM,
    VETTING_ULTRA_SHORT_PERIOD_DAYS,
    VETTING_VSHAPE_LOW_SNR_GATE,
    DETECTION_CONFIDENCE_FLOOR,
    DETECTION_SNR_THRESHOLD_DEFAULT,
)
```

### Step 1: Detrend

```python
stellar_rotation_period_days = DetrendingEngine.estimate_stellar_rotation(time, flux)
flux = DetrendingEngine.detrend(time, flux, stellar_rotation_period_days)
active_time = time.copy()
active_flux = flux.copy()
if len(active_time) < 10:
    return {}
```

### Step 2: BLS Search (with J1b/J1c/J3 fixes)

```python
search_results = BLSSearchEngine.search(active_time, active_flux, known_periods=known_periods)
best_period   = search_results['period']
best_snr      = search_results['snr']
best_depth    = search_results['depth']
transit_time  = search_results['t0']
duration      = search_results['duration']
best_confidence = search_results['confidence_score']
```

### Step 3: TLS Cross-Validation (J2c fix, 2026-07-06)

```python
tls_fap = 1.0
tls_sde = 0.0
tls_period = best_period
tls_valid = False
tls_environment_error = None
tls_scientific_error = None

if best_period > 0:
    try:
        import transitleastsquares as tls
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = tls.transitleastsquares(active_time, active_flux)
            # Narrow the search space around the BLS period to save time
            tls_period_min = best_period * 0.95
            tls_period_max = best_period * 1.05
            if tls_period_min < 0.5 and tls_period_max > 0.5:
                tls_period_min = 0.5
            elif tls_period_max < 0.5:
                raise ValueError("period_min < period_max required")
            # CRITICAL (J2c): use_threads=1 is required
            # because detect_transit_candidate runs inside
            # astraeus.core.orchestrator._subprocess_search_worker
            # which is spawned daemon=True; on Windows, multiprocessing
            # forbids daemonic processes from spawning their own
            # children, so TLS's default use_threads=cpu_count() path
            # raises AssertionError. Locked by
            # tests/characterize/test_tls_call_path_contract.py.
            results = model.power(
                period_min=tls_period_min,
                period_max=tls_period_max,
                show_progress_bar=False,
                use_threads=1,
            )
            tls_fap = results.FAP
            tls_sde = results.SDE
            tls_period = results.period
            if tls_sde >= 5.0 and abs(tls_period - best_period) / best_period < 0.05:
                tls_valid = True
    except ImportError:
        print("WARNING: transitleastsquares not installed. Skipping TLS cross-validation.")
        tls_valid = True  # Fail open if missing
    except (AssertionError, RuntimeError) as e:
        # INFRASTRUCTURE / ENVIRONMENT failure (J2c)
        tls_environment_error = f"{type(e).__name__}: {e}"
        print(f"[TLS-INFRA-ERROR] ...")
        tls_valid = False
    except Exception as e:
        # SCIENTIFIC failure (numba type error, NaN, etc.) (J2c)
        tls_scientific_error = f"{type(e).__name__}: {e}"
        print(f"[TLS-SCI-ERROR] ...")
        tls_valid = False
```

### Step 4: Emission Gate

```python
is_valid = (
    best_snr > snr_threshold
    and best_confidence >= DETECTION_CONFIDENCE_FLOOR
    and tls_valid
)
```

### Step 5: Hoist metadata

```python
global_payload = metadata or {}
archive_metadata = global_payload.get('metadata', global_payload)
st_rad = float(archive_metadata.get('st_rad') or archive_metadata.get('stellar_radius') or 1.0)
st_teff = float(archive_metadata.get('st_teff', 5778.0))
st_mass = float(archive_metadata.get('st_mass', 1.0))
sy_jmag = float(archive_metadata.get('sy_jmag', 10.0))

raw_depth = float(best_depth)
transit_depth_fraction = raw_depth / 100.0 if raw_depth > 0.1 else raw_depth
```

### Step 6: Build the result dict

```python
result = {
    'candidate_found': is_valid,
    'is_candidate': is_valid,
    'period_days': best_period,
    'period': best_period,
    'orbital_period': best_period,
    'stellar_rotation_period_days': stellar_rotation_period_days,
    'transit_depth': transit_depth_fraction,
    'stellar_radius': st_rad,
    'vetting_status': 'candidate' if is_valid else 'rejected',  # Default; overridden below
    'confidence_score': search_results['confidence_score'],
    'snr': best_snr,
    'depth': transit_depth_fraction,
    'duration': duration,
    't0': transit_time,
    't0_bjd': transit_time,         # I2 fix: explicit unit
    'time_unit': 'BJD',             # I2 fix
    'periodogram': search_results['periodogram'],
    'tls_fap': tls_fap,
    'tls_sde': tls_sde,
    'tls_period': tls_period,
    'tls_valid': tls_valid,
    'tls_environment_error': tls_environment_error,   # J2c fix
    'tls_scientific_error': tls_scientific_error,      # J2c fix
}
```

### Step 7: Geometric validation + shape vetting

```python
geom_metrics = GeometricValidator.validate(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction)
result.update(geom_metrics)

vetting_metrics = VettingEngine.vet_transit_shape(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction, snr=best_snr)
result.update(vetting_metrics)
result['v_shape_metric'] = 1.0 - vetting_metrics['vetting_confidence']  # back-compat
```

### Step 8: Physical properties + secondary-eclipse threshold (bucket 2)

```python
phys_props = PhysicalPropertiesEngine.derive(best_period, transit_depth_fraction, st_rad, st_teff, st_mass, sy_jmag)
result.update(phys_props)

expected_occultation_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
    planet_radius_earth=phys_props.get('planet_radius_earth', 0.0),
    stellar_radius_solar=st_rad,
    planet_equilibrium_temp_k=phys_props.get('equilibrium_temp_k', 0.0),
    stellar_teff_k=st_teff,
)
if expected_occultation_ppm is None:
    sec_eclipse_threshold_ppm = VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM
    sec_eclipse_threshold_mode = "fallback_fixed"
else:
    sec_eclipse_threshold_ppm = expected_occultation_ppm
    sec_eclipse_threshold_mode = "physical"
result['secondary_eclipse_threshold_ppm'] = sec_eclipse_threshold_ppm
result['secondary_eclipse_threshold_mode'] = sec_eclipse_threshold_mode
sec_eclipse_threshold_fraction = sec_eclipse_threshold_ppm / 1.0e6
```

### Step 9: False-Positive Cross-Vetting (R8 fix, I1 fix — runs UNCONDITIONALLY)

```python
is_ultra_short_period = float(best_period) < VETTING_ULTRA_SHORT_PERIOD_DAYS
sec_depth = geom_metrics.get('secondary_eclipse_depth', 0.0)

if transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION:
    result['vetting_status'] = "Verified Planet Candidate"
elif (vetting_metrics['vetting_status'] == "Ambiguous/False Positive"
      and geom_metrics['secondary_eclipse_detected']
      and (best_snr <= VETTING_VSHAPE_LOW_SNR_GATE or sec_depth >= sec_eclipse_threshold_fraction)):
    result['vetting_status'] = "Eclipsing Binary Detected"
elif (best_snr <= VETTING_VSHAPE_LOW_SNR_GATE
      and not is_ultra_short_period
      and vetting_metrics['vetting_status'] == "Ambiguous/False Positive"):
    result['vetting_status'] = "V-Shaped False Positive Risk (Potential Grazing Binary)"
elif geom_metrics['secondary_eclipse_detected']:
    if sec_depth < sec_eclipse_threshold_fraction:
        result['vetting_status'] = "Verified Planet Candidate (Atmospheric Occultation Detected)"
    else:
        result['vetting_status'] = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
elif vetting_metrics['vetting_status'] == "Likely Planet" and is_valid:
    # R8 fix (2026-07-12): gate the "Likely Planet" override on the production
    # emission gate (is_valid). Previously this branch unconditionally set
    # "Verified Planet Candidate" — bypassing the TLS gate. Round 7's J7c
    # run hit this on the real Kepler-90 curve: TLS correctly rejected
    # (tls_sde=4.22 < 5.0, tls_valid=False), but this branch then stamped
    # "Verified Planet Candidate" anyway. The orchestrator's GUARDRAIL 1
    # then tripped the wrong way.
    result['vetting_status'] = "Verified Planet Candidate"
elif not is_valid:
    pass  # Keep the line-79 default ("rejected")
```

### Step 10: TTV + log

```python
result['ttv_data'] = TTVAnalyzer.calculate(active_time, active_flux, best_period, transit_time, duration)
save_experiment_log(
    params={
        "target_name": target_name,
        "period": best_period,
        "stellar_rotation_period_days": stellar_rotation_period_days,
        "snr": best_snr,
        "data_source": data_source,
        "is_valid_candidate": bool(is_valid),
    },
    metadata=metadata or {},
    fig_paths=[],
)
return result
```

### Helper function: `validate_bls_candidate`

```python
def validate_bls_candidate(transit_depth: float, out_of_transit_flux: np.ndarray,
                            in_transit_count: int, snr_threshold: float = 5.0) -> tuple[bool, float]:
    if len(out_of_transit_flux) == 0 or in_transit_count <= 0:
        return False, 0.0
    local_noise_std = np.std(out_of_transit_flux)
    if local_noise_std == 0:
        return False, 0.0
    calculated_snr = (transit_depth / local_noise_std) * np.sqrt(in_transit_count)
    return calculated_snr > snr_threshold, float(calculated_snr)
```

---

## 9. BLS Search Engine — the periodogram workhorse

File: `astraeus/analysis/bls_search.py` (234 lines).

### `BLSSearchEngine.compute_snr_depth(time, flux, p, t0, dur) -> (snr, depth)`

Phase-folds the data at `(p, t0, dur)`, computes `in_transit` mask, returns `(depth, snr)` from in/out medians + std.

### `BLSSearchEngine.search(time, flux, scan_depth=1, known_periods=None, frequency_factor=None) -> dict`

**The main entry point.** Performs:
1. Dynamic search-space bounds: `p_min=0.5`, `p_max = T_baseline/2` (with a 450d cap on short baselines — J3 fix for the 600d planet in SYN-5P).
2. **`astropy.timeseries.BoxLeastSquares.autoperiod`** with a curve-size-adaptive `frequency_factor` (J1b fix):
   - `frequency_factor = max(1.0, T_baseline^2 / 4500.0)` capped at `500.0`
   - 10d smoke: ff=1.0, ~1801 periods
   - 200d kepler90d: ff=8.9, ~89k periods, 7.2s wall
   - 1500d syn5p 5-planet: ff=500, ~90k periods, 3.6s wall, 4/5 recovered
3. **Physical mask** (J3 fix, root-cause): `(period, duration)` pairs where `duration > 0.2 * period` are degenerate (the box is wider than the orbital phase). Set `power = -inf` for these so they cannot win `argmax`. The 0.2 duty-cycle cap is the standard physical upper bound for transit + grazing-binary configurations.
4. **Window-aware alias rejection** (J1c fix): computes a Lomb-Scargle periodogram of the time-sampling window, takes the top 5 window frequencies, then iterates through best peaks. For each candidate period, checks:
   - **Integer harmonics** (0.25×, 0.33×, 0.5×, 1×, 2×, 3×, 4×, 5×) against `known_periods` (5% tolerance)
   - **Window aliases**: `f_cand ≈ |f_prev ± k * f_window| / m` for k, m ∈ {1..5}
   - **5%-margin rejection near p_min / p_max** (J3 follow-up)
5. **Final fallback**: if everything rejected, take the top sorted peak anyway.
6. **Confidence score**: `best_power / np.median(res.power)`.

Returns `{period, duration, t0, snr, depth, confidence_score, periodogram: {periods, powers}}`.

### `BLSSearchEngine.mask_transit(time, flux, period, t0, duration) -> (time_masked, flux_masked)`

Masks a 1.5×-duration window around each transit (used by the orchestrator).

### What changed vs. the v0.0.2 briefing

- **Default `scan_depth=1` is unused** — kept for back-compat. The actual grid coarseness is now controlled by `frequency_factor`.
- **`frequency_factor` parameter** — explicit override possible. Default is curve-size-adaptive (J1b fix).
- **Window-aware alias rejection** (J1c fix) — uses Lomb-Scargle of the time sampling to detect alias frequencies, then rejects candidates that are aliases or harmonics of known periods.
- **Physical mask at 0.2 duty cycle** (J3 fix) — root-cause fix for `(P=0.5d, dur=0.4d)` and similar degenerate boundary peaks.
- **5%-margin rejection at p_min / p_max** (J3 follow-up) — kills noise peaks near the search bounds.

---

## 10. TLS cross-validation

The codebase does **not** have a `tls.py` of its own. TLS lives as a **library call** inside `detect_transit_candidate` (Step 3) and uses the `transitleastsquares` package.

### What it does

Runs `transitleastsquares.transitleastsquares(time, flux).power(period_min, period_max, show_progress_bar=False, use_threads=1)` on the BLS-narrowed 0.95×–1.05× period window. Returns `{FAP, SDE, period}`. A candidate is TLS-validated when `tls_sde >= 5.0` and `|tls_period - best_period| / best_period < 0.05`.

### Three possible outcomes (J2c fix, 2026-07-06)

| Outcome | tls_valid | Sentinel field | Meaning |
|---|---|---|---|
| Scientific success | `True` | (none) | TLS ran, SDE ≥ 5.0, period within 5% |
| `ImportError` | `True` | (none) | `transitleastsquares` not installed — fail-open |
| Infra failure | `False` | `tls_environment_error: "AssertionError: ..."` | Windows daemonic-process AssertionError, RuntimeError, OOM during grid construction |
| Scientific failure | `False` | `tls_scientific_error: "TypeError: ..."` | numba type error, NaN, malformed input |

The infrastructure branch was previously silently folded into `tls_valid=False` (same as scientific). This made "no planets found" indistinguishable from "the gate is broken". The fix lets downstream consumers (the orchestrator's `_subprocess_search_worker`, monitor thread, and UI) tell them apart.

### The `use_threads=1` constraint (CRITICAL — J2c)

`detection.py` is invoked from `astraeus.core.orchestrator._subprocess_search_worker`, which is spawned `daemon=True`. On Windows, multiprocessing forbids daemonic processes from spawning their own children. TLS's default `use_threads=cpu_count()` instantiates `multiprocessing.Pool(processes=use_threads)` and raises `AssertionError: "daemonic processes are not allowed to have children"`. The fix forces `use_threads=1`, keeping TLS single-threaded inside the worker.

**Performance**: ~80s per call on a 45,853-cadence curve with the 0.95×-1.05× BLS-narrowed window (J2c profile measurement).

**Constraint lock**: `tests/characterize/test_tls_call_path_contract.py` pins this contract. **Do not remove or relax `use_threads=1` without updating the test and the comment.**

### Test reference

`tests/characterize/test_tls_call_path_contract.py::test_tls_except_block_distinguishes_infra_from_scientific` — pins the J2c contract.

---

## 11. Detrending Engine

File: `astraeus/analysis/detrending.py`.

### `DetrendingEngine.estimate_stellar_rotation(time, flux) -> float`

Uses `astropy.timeseries.LombScargle.autopower` over `[0.1, 10.0]` day⁻¹. Subsamples to ≤2000 points for large arrays. Returns `1.0 / frequency[argmax(power)]`.

### `DetrendingEngine.detrend(time, flux, stellar_rotation_period_days, st_rad=None) -> np.ndarray`

Pipeline:
1. Asymmetric sigma clipping — removes `flux > median + 3*sigma` (positive anomalies only; preserves transit dips).
2. **Dynamic window scaling** based on stellar radius (if provided):
   - `st_rad < 0.3` → 0.5d window
   - `st_rad >= 0.8` → 2.0d window
   - Linear interpolation in between
   - Otherwise: `clamp(stellar_rotation_period_days * 0.5, 0.5d, 1.5d)`
3. If `wotan` is installed: `wotan.flatten(time, clean_flux, window_length=window_length_days, method='biweight')`, NaN-fill with 1.0.
4. Otherwise (fallback): `scipy.ndimage.median_filter(clean_flux, size=window_length_points)`, divide out the trend, return `clean_flux / trend`.

Constants:
- `MIN_TRANSIT_PRESERVING_WINDOW_DAYS = 0.5`
- `MAX_TRANSIT_PRESERVING_WINDOW_DAYS = 1.5`

---

## 12. Vetting engines — U/V shape, geometry, physical properties

### `VettingEngine.vet_transit_shape(...)` (`astraeus/analysis/vetting.py`)

Fits a **trapezoidal U-shape template** (planet transit with 10% ingress/egress) and a **V-shape template** (grazing binary) to the phase-folded data, plus a flat null hypothesis. Returns chi² values for each and a verdict.

**Bucket 10 hardening (2026-07-06)**: New default `threshold=VETTING_U_VS_V_CHI2_DELTA_THRESHOLD = 0.001`. Requires `delta_chi2_u > delta_chi2_v + threshold` (instead of the old `delta_chi2_u > delta_chi2_v`, which had no significance floor). Empirical justification at `reports/bucket10_threshold_audit.md` §3:
- Real U-shape (depth 0.01): +0.0021
- V-shape (eclipsing binary): -0.0007
- Marginal/noise: ~0

**Override SNR bypass**: `if snr > 10.0` the threshold is bypassed (high-SNR wins regardless).

Returns `{vetting_status, vetting_confidence, u_shape_chi2, v_shape_chi2, delta_chi2_u, delta_chi2_v}`. `vetting_status` is `"Likely Planet"` or `"Ambiguous/False Positive"`.

Edge cases (returns 0-confidence defaults):
- `< 3` samples in window → `'Insufficient Data'`
- `local_median == 0 or NaN` → `'Inconclusive'`
- Any `curve_fit` exception → `'Indeterminate'`

### `GeometricValidator.validate(...)` (`astraeus/analysis/geometric_validation.py`)

Phase-folds the data and computes:
- `v_shape_metric` (always 0; computed in `VettingEngine`)
- `flat_bottom_fraction` — fraction of in-transit samples that are at the minimum flux ± 10% slack (constants: `GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES=8`, `GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK=0.10`)
- `secondary_eclipse_depth`, `secondary_eclipse_snr`, `secondary_eclipse_detected` — searches for a dip in a window around phase 0.5 (constants: `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW=0.05`, `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER=0.05`, `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER=0.15`, `GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES=3`, `VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD=3.0`).

### `PhysicalPropertiesEngine.derive(...)` (`astraeus/analysis/physical_properties.py`)

Computes:
- `planet_radius_earth = st_rad * sqrt(transit_depth_fraction) * R_SUN_TO_R_EARTH` (where `R_SUN_TO_R_EARTH = 109.2`)
- `equilibrium_temp_k` — using Kepler's 3rd law for semi-major axis and `T_eq = T_eff * sqrt(R_star / (2a)) * (1 - A)^0.25` (Bond albedo = 0.3)
- `jwst_tsm_score` — Kempton TSM (transmission spectroscopy metric) for JWST prioritization. Uses radius bins for `tsm_scale` (0.190, 1.26, 1.28, 1.15) and `mass = R^2.06`.

### `PhysicalPropertiesEngine.expected_occultation_depth_ppm(...)` (Bucket 2 headline fix)

Returns `float | None`. In the **Rayleigh-Jeans limit**, the secondary-eclipse depth simplifies to:

```
depth_ppm = (R_p / R_star)^2 * (T_planet / T_star) * 1e6
```

`R_p / R_star` uses `R_SUN_TO_R_EARTH` for unit conversion. `T_planet / T_star` is capped at 1.0 (a planet cannot emit more thermal flux than the star in any bandpass without violating energy conservation).

Returns `None` if any required input is missing or non-positive; the caller falls back to `VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0` and records the mode in the result dict.

This is the **headline fix for the original "800 ppm false-binary" bug** — old flat 800 ppm constant misclassified hot, large planets around cool stars.

---

## 13. TTV (Transit Timing Variation) analysis

Two modules:

### `astraeus/analysis/ttv_analysis.py::TTVAnalyzer.calculate(time, flux, period, t0, duration) -> list`

Iterates epoch by epoch from `epoch_t0` (wrapped to the data range). For each epoch, finds the 10% lowest-flux samples within ±0.5×duration of the predicted mid-transit, computes a depth-weighted mean time, and returns the **O-C residual in minutes** (`(t_obs - t_calc) * 1440.0`).

Returns `list[dict]` with `{epoch, ttv_residual_min}`.

### `astraeus/analysis/ttv_nbody_validation.py`

Bucket 9.2 validation work. Uses the N-body solver to **predict** TTV amplitudes from masses/period ratios and cross-checks against extracted TTVs.

Periodic check: **Lomb-Scargle** period extraction on TTV series (commit `c465706`). Analytical amplitude proxy filter (commit `902e211`). Grid-search validation against N-body truth (commit `d8e181c`).

---

## 14. N-body solver

File: `astraeus/core/nbody_solver.py` (~600 lines).

**Pure-numpy Symplectic Velocity Verlet (Störmer-Verlet / Leapfrog) integrator.** No external astronomy packages.

### Internal units

- Length: AU
- Mass: M_sun
- Time: years
- **G = 4π²** (in AU³ M_sun⁻¹ yr⁻²)
- Softening ε² = 1e-4 AU²

### Constants

| Symbol | Value | Meaning |
|---|---|---|
| `G_AU3_MSUN_YR2` | 4π² | Gravitational constant |
| `AU_TO_RSUN` | 215.032 | 1 AU ≈ 215 R_sun |
| `YR_TO_DAYS` | 365.25 | Julian year in days |
| `M_EARTH_IN_MSUN` | 3.003e-6 | Earth mass in M_sun |
| `R_EARTH_IN_RSUN` | 0.00917 | Earth radius in R_sun |
| `SOFTENING_SQ` | 1e-4 | Gravitational softening |
| `ENERGY_DRIFT_THRESHOLD` | 1e-4 | Early-exit on numerical drift |
| `VELOCITY_SANITY_CAP` | 100.0 | AU/yr ≈ 47 km/s |

### Data classes

```python
@dataclass
class PlanetParams:
    mass_msun: float
    semi_major_axis_au: float
    eccentricity: float = 0.0
    initial_phase_rad: float = 0.0

@dataclass
class StabilityResult:
    is_stable: bool
    survival_time_years: float
    max_eccentricity_drift: float
    termination_reason: str  # "completed" | "collision" | "ejection" | "energy_divergence" | "Physical Boundary Breach"
    colliding_pair: Optional[tuple] = None
    ejected_body: Optional[int] = None
    final_eccentricities: list = field(default_factory=list)
    energy_relative_error: float = 0.0
```

### Public surface

```python
def run_stability_analysis(stellar_mass_msun, planets, n_steps=50_000, dt_years=None) -> StabilityResult
    # From PlanetParams list; dt auto = min_period / 100 if None

def run_stability_integration(positions, velocities, masses, n_steps=10_000, dt=0.01) -> StabilityResult
    # From raw state vectors

def check_system_stability(stellar_mass_msun, planet_dicts, n_steps=50_000, dt_years=None) -> dict
    # Dict-based API; JSON-safe return

def estimate_mass_from_radius(radius_earth) -> float
    # Weiss-Marcy 2014 power law; returns M_sun
```

### Used by

- `ui/pages/simulator.py` (lazy import)
- `tests/test_nbody_solver.py` — validates against Kepler-90 6-planet system (includes merged Kepler-90b scenarios from `test_engine.py`).

### Physics references

- Velocity Verlet: Swope et al. 1982, J. Chem. Phys. 76, 637
- Hill radius: Hamilton & Burns 1992, Icarus 96, 43
- Weiss-Marcy mass-radius: Weiss & Marcy 2014, ApJL 783, L6

---

## 15. Multi-planet orchestrator

File: `astraeus/core/orchestrator.py` (~580 lines).

### `subtract_planetary_signal(flux, time, period, epoch, duration, depth_ppm, metadata=None) -> np.ndarray`

Subtracts a transit signal. **Hybrid: batman-package first, Trapezoidal fallback.**

- Pads the window by 25% on each wing (50% total, "1.5× wing subtraction" label).
- **batman path**: `batman.TransitParams()` with `rp = sqrt(depth_ppm / 1e6)`, `a = max(1.0, period / (pi * duration))`, `inc = 90`, `ecc = 0`, `w = 90`, `limb_dark = "quadratic"`, `u = [0.1, 0.3]` (or from metadata). `batman.TransitModel(params, time).light_curve(params)` then `cleaned_flux += (1.0 - transit_model)`.
- **Trapezoidal fallback**: flat bottom + linear ingress/egress ramps (10% of duration each). Triggered on any `Exception` from batman; logs `[Fallback] batman failed or unavailable`.

### `run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1) -> list[dict]`

The synchronous orchestrator. Loops up to `max_signals` iterations:

1. Calls `detect_transit_candidate(...)`.
2. **GUARDRAIL 1 (SNR/vetting break):** if `snr < snr_floor` OR `vetting_status` doesn't start with `"Verified Planet Candidate"`, halt.
3. **GUARDRAIL 2 (duplicate/harmonic detection):** skip if new period within 5% of any previous OR a 0.5×/2× harmonic. Up to 3 retries; subtract anyway to erode residual.
4. **Subtract** the transit from `current_working_flux` via `subtract_planetary_signal(...)`.
5. Loop.

Returns list of candidate dicts + prints consolidated JSON.

### Async submission: `submit_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1) -> job_id`

**Spawns a daemon multiprocessing process** to run the search. Communicates back via a `multiprocessing.Queue`:

```python
{'type': 'running'}                   # worker has started
{'type': 'iteration', 'iteration': N} # beginning iteration N
{'type': 'candidate', 'data': dict}   # accepted candidate
{'type': 'done'}                      # search finished normally
{'type': 'error', 'error': str}       # search failed
```

A daemon monitor thread drains the queue and updates `JOB_REGISTRY`. Public helpers:

```python
def get_job_status(job_id) -> dict | None  # snapshot
def cancel_job(job_id) -> None              # hard terminate
class JobState:                             # PENDING / RUNNING / DONE / FAILED / CANCELLED
```

**J2c critical constraint** (commented in code at `orchestrator.py:535-551`): the worker is spawned `daemon=True`. On Windows, daemonic processes cannot spawn their own children. This is what forces `use_threads=1` in `detection.py`'s TLS call.

### The subprocess worker (`_subprocess_search_worker`)

A near-mirror of `run_multi_planet_search` with two differences:
- Sends status messages via `result_queue` instead of printing
- **R8 fix (2026-07-12)**: GUARDRAIL 1 has a `_GUARDRAIL1_MARGINAL_TOLERANCE = 3` budget — if 3 consecutive marginal results (snr < floor or vetting ambiguous) occur, the worker breaks early. Up to 3 marginal subtractions are still attempted to erode residual.

### Recent hard test evidence (`reports/bucket9.2_*`)

Post-fix FP rate 0% on synthetic validation.

---

## 16. Simulation layer

### `astraeus/simulation/synthetic.py`

#### `SyntheticTransitScenario` (frozen dataclass)

Default values:
- `duration: 10.0 d`
- `period: 3.0 d`
- `eccentricity: 0.0`
- `radius_ratio: 0.1`
- `snr: 200.0`
- `samples: 4_000`
- `seed: 42`
- `stellar_radius: 1.0 R_sun`
- `semi_major_axis: 10.0 R_sun`
- `inclination: 90.0 deg`

Class method: `SyntheticTransitScenario.hot_jupiter()` returns the default 10-day hot-Jupiter scenario.

#### `LightCurveSeries` (frozen dataclass)

Holds `time_days`, `theoretical_flux`, `observed_flux`. Property: `residuals = observed - theoretical`.

#### `generate_synthetic_transit_series(scenario) -> LightCurveSeries`

Generates time grid (linspace), computes theoretical flux from `calculate_orbital_position` + `calculate_sky_separation` + `generate_geometric_transit`, injects Gaussian noise via `inject_gaussian_noise`.

#### `run_injection_recovery(time, flux, injected_period, injected_r_ratio, injected_b, injected_epoch, known_planets=None, metadata=None) -> dict`

1. Validates physical constraints (`r_ratio < 1.0`, `b < 1 + r_ratio`).
2. Checks baseline ≥ 2× injected period.
3. Optionally subtracts known planets.
4. Generates the injected transit model (with native geometry engine).
5. Runs a bounded-grid BLS (1000 periods, 0.95×–1.05× window) and computes recovery metrics.
6. Returns `{signal_recovered, period_error_delta, snr_attenuation, recovered_period, recovered_snr, recovered_depth, injected_snr}`.

**Memory isolation countermeasure**: explicit `del` + `gc.collect()` at the end to prevent OOM during sweeps.

### `astraeus/simulation/completeness.py`

#### `CompletenessSweepConfig` (frozen dataclass)

Default grid:
- `period_min_days: 0.5`, `period_max_days: 30.0`, `period_count: 4`
- `radius_ratio_min: 0.005`, `radius_ratio_max: 0.10`, `radius_ratio_count: 3`
- `snr_values: (10.0, 30.0, 100.0)`
- `n_injections: 5`, `seed: 1729`
- `use_full_pipeline: False`
- `duration_days: 90.0`, `samples: 4_000`
- `impact_parameter: 0.3`, `transit_epoch_fraction: 0.5`
- `cache_dir: "outputs/completeness_sweeps"`

Validates in `__post_init__`: `duration_days >= 2 * period_max_days`.

#### `CompletenessSweepResult` (frozen dataclass)

3D arrays over `(periods, radius_ratios, snrs)`:
- `recovery_rate`, `period_err_median`, `period_err_std`, `depth_err_median`, `depth_err_std`, `n_recovered`, `cell_runtime_seconds`

Plus: `config_hash`, `total_runtime_seconds`, `cache_hits`, `cache_misses`, `started_at_iso`, `finished_at_iso`.

Methods: `to_dict()` (JSON-serializable, NaN→null), `save(path)` (atomic `.tmp + os.replace`), `load(path)`.

#### `run_completeness_sweep(config, *, progress_callback=None) -> CompletenessSweepResult`

Sweeps the grid with **per-cell caching and resumability**:
- Cache dir: `cache_dir / sha256(config) / cells / <cell_hash>.json`
- Manifest: `cache_dir / sha256(config) / manifest.json`
- Each cell run records `{cell, result, schema_version, written_at_iso, config_hash}`.
- Phase 1 measurement: each cell ~5.7s; default full sweep ~17 min.
- Validated vs. `run_injection_recovery` directly.

#### Visualization

`astraeus/visualization/plots.py::plot_completeness_map(...)` — heatmap + SNR-slope plot.

---

## 17. PDF manuscript export

File: `astraeus/analysis/reporting.py`.

### `generate_academic_report(metrics_payload, figures=None) -> io.BytesIO`

Called from `app.py`'s Discover tab → "Generate Research Manuscript" button.

**Backend: reportlab** (PDF generation).

**Figure embedding pipeline (multi-layer fallback)**:
1. **Type firewall**: `_is_plotly_figure` duck-checks for `.to_image` + `.data`; non-figures route to canvas fallback.
2. **Kaleido** (`kaleido==0.2.1`): Plotly → PNG → reportlab `Image`. Requires headless browser deps.
3. **Matplotlib fallback** (`_rasterize_with_matplotlib`): rebuilds the chart from Plotly trace data using matplotlib's `Agg` backend (no browser deps). Supports scatter + line traces, preserves title, axis labels, dark theme.
4. **Styled text canvas** (`_build_fallback_canvas`): a labeled placeholder when both above fail.

Output is returned as an in-memory `BytesIO`; `st.download_button` offers it.

**Schema (strict, validated by `_validate_schema`)**:

```python
metrics_payload = {
    "star_id": str,                       # REQUIRED
    "candidates": [                       # REQUIRED
        {
            "candidate_id": str,          # ← OR "planet_id"
            "period": float,
            "snr": float,
            "depth": float,
            "epoch": float,               # ← OR "t0"
        },
        ...
    ],
    "introduction": str,                  # optional
    "optimization_summary": str,          # optional
}
figures = {                              # optional
    "<star_id>-1<N>": plotly.Figure,     # keys follow <star_id>-1<N> convention
    ...
}
```

The function:
- Deep-copies the payload (defensive against pass-by-reference mutation).
- Creates a `SimpleDocTemplate` with letter-size pages, 0.75" margins.
- Uses `NumberedCanvas` (custom canvas that adds "Generated: YYYY-MM-DD HH:MM:SS" + "Page X of Y" footer to every page).
- Sanitizes text via `sanitize_text` (regex-replaces Greek letters, ±, °, ≥, ≤, etc. into ReportLab-friendly ASCII).
- Renders sections: Title, Executive Abstract (boxed), 1. Introduction, 2. Transit Optimization, 3. Planetary Properties Ledger (table), 4. Figure Layouts.
- Tables are chunked at 8 rows (`MAX_ROWS = 8`).
- Cleans up tracked streams + `gc.collect()` in the `finally` block.

### `generate_completeness_report(result, config, fig_paths) -> dict`

Returns a JSON-shaped summary of a completeness sweep (distinct from the academic PDF; completeness data doesn't fit the academic schema).

---

## 18. Experiment tracking and logging

File: `astraeus/analysis/logging.py`.

### `save_experiment_log(params, metadata, fig_paths) -> uuid`

Appends an entry to `logs/experiments.json` with `{id (UUID), timestamp, dataset_hash, params, metadata, fig_paths}`. Called by every `detect_transit_candidate` invocation.

### `load_experiment_history() -> list[dict]`

Reads full ledger from `logs/experiments.json`. Returns `[]` if the file doesn't exist or fails to parse.

### `generate_dataset_hash(metadata) -> sha256`

Reproducibility anchor — SHA256 of the sorted-JSON encoding of `metadata["dataset"]` (or `metadata` itself).

### `ExperimentLedger` class

Atomic-write variant (`.tmp + os.replace`). Used by older callers; `save_experiment_log` is the canonical path for new code.

### `LOG_FILE = "logs/experiments.json"`

The single experiment ledger. Suppressed during pytest via conftest isolation (bucket 9.2). Auto-appended on every detection call.

---

## 19. LLM gateway and AI co-pilot

File: `astraeus/core/llm_gateway.py`.

### `LLMClient(provider, api_key=None, model_name=None, system_prompt=...)`

Provider-agnostic. Loads API key from env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).

| Provider | Default model | Requires |
|---|---|---|
| `openai` | `gpt-4o` | `OPENAI_API_KEY` (or `api_keys.openai` in config.json) |
| `anthropic` | `claude-3-opus-20240229` | `ANTHROPIC_API_KEY` |
| `google` | `gemini-1.5-pro-latest` | `GOOGLE_API_KEY` (or `api_keys.google` in config.json) |
| `ollama` | `llama3` | local Ollama daemon at `localhost:11434` |

Methods: `_call_openai`, `_call_anthropic`, `_call_google`, `_call_ollama` (all private), `generate_response(prompt, context=None) -> str`.

### Used by

- `astraeus/dashboard/ui/components.py::render_floating_chat` (UI chat popover, bottom-right of workbench). The current implementation is a **mock** — generates a placeholder response. Real LLM calls are not yet wired.
- `astraeus/analysis/explanation.py::get_scientific_explanation` (natural-language result interpretation; expects JSON response with `physics_interpretation`, `parameter_breakdown`, `uncertainty_analysis` keys).

### Configuration

`astraeus/core/config.py::load_config(filepath="config.json")` and `validate_config(config)`. The repo's `config.json` ships with empty API keys:

```json
{
    "llm_provider": "google",
    "llm_model": "gemini-1.5-pro-latest",
    "api_keys": {
        "google": "",
        "openai": "",
        "anthropic": ""
    }
}
```

Users must set keys in `config.json` or via env vars.

---

## 20. The dashboard shell (layout, components, settings)

File: `astraeus/dashboard/ui/`.

### `layout.py`

- `apply_astro_theme()` — injects CSS for a dark "Astro-vibe" theme. Base bg `#0A0E17`, sidebar `#0F172A`, headers `#A78BFA` (soft purple), font `Fira Code`. Uses `:has()` selectors for sticky sidebar header/footer.
- `render_left_nav() -> str` — renders the 6-button sidebar nav. Returns `st.session_state.current_route`. Options: Simulation, Lab, Detective, Discover, History, Settings (with `:material/` icons).
- `workbench_layout()` — contextmanager that yields `(selected_feature, main_panel, right_panel)`. Uses `st.columns([7, 3], gap="large")` for the main + right panel, with an "Assets Panel" checkbox to collapse.

### `styles.py`

- `inject_page_styles()` — small page-level CSS refinements (block-container padding, sidebar border, metric border). Composes with `apply_astro_theme`.

### `components.py`

- `render_floating_chat()` — uses `st.popover("AI Assistant")` (the source has rendering issues with the emoji). Fixed bottom-right (CSS `position: fixed; bottom: 30px; right: 30px`). Chat input + scrollable message history (400px). **Current implementation is MOCK** — returns a placeholder, doesn't actually call `LLMClient`. Real wiring is TODO.

### `settings.py`

- `initialize_settings()` — loads `config.json` into `st.session_state` on first call.
- `render_settings_panel()` — LLM provider dropdown (`google`, `openai`, `anthropic`, `ollama`), model name text input, API key password input.

### `figures.py`

Plotly chart builders: `make_light_curve_figure`, `make_residuals_figure`, `make_multi_orbit_animation_html`.

### `simulation.py`

`DashboardSimulation` dataclass (frozen), `generate_dashboard_simulation(scenario)`, `semi_major_axis_for_solar_mass(period_days)` (Kepler's 3rd law for solar-mass host). Uses `astropy.units` throughout.

### `scenario.py` / `validation.py`

`DashboardTransitScenario` dataclass, `validate_scenario`, `generate_stable_seed`.

---

## 21. LightkurveClient — the data acquisition layer in depth

File: `astraeus/core/lightkurve_client.py` (~970 lines). The most complex module in the project.

### Precision policy (module docstring)

> All time, flux, and flux_err arrays MUST be stored as `np.float64`. Shallow transit dips (< 400 ppm) occupy the 4th–5th decimal digit of normalised flux; float32 provides only ~7 significant digits, which is insufficient to preserve these signals through downstream BLS and trapezoid fitting. Every extraction and concatenation site in this module therefore carries an explicit `dtype=np.float64` guard.

### Module-level constants

```python
_LIGHTKURVE_CACHE_DIR = "~/.lightkurve/cache"
_ASTRAEUS_LIGHTKURVE_CACHE_DIR = os.environ.get("ASTRAEUS_LIGHTKURVE_CACHE_DIR", "<tmp>/astraeus_lightkurve_cache")
_MAX_DOWNLOAD_SEGMENTS = 12            # Kepler row-by-row fallback limit (H1 patch 2026-07-06)
_MAST_DOWNLOAD_URL = "https://mast.stsci.edu/api/v0/Download/file"
_TESS_READ_TIMEOUT = 600.0            # ≥600s per FIX 2.3
_KEPLER_READ_TIMEOUT = 180.0
_CONNECT_TIMEOUT = 10.0
_STREAM_CHUNK_BYTES = 1 << 20         # 1 MiB chunks keep peak memory flat
_STREAM_MAX_ATTEMPTS = 3
_STREAM_BACKOFF_BASE = 2.0            # 2s, 4s, 8s with full jitter
_S3_PUBLIC_BUCKET = "stpubdata"
_S3_TESS_KEY_PREFIX = "tess/public"
_S3_KEPLER_KEY_PREFIX = "kepler/public"
_TESS_LC_DOWNLOAD_TIMEOUT = 300.0     # TESS SPOC download_all budget
_TESS_LC_MAX_RETRIES = 3
_TESS_LC_RETRY_BACKOFF = 4.0          # 4s, 8s, 16s with jitter
```

### Curated well-known target → TIC/KIC lookup

```python
_TARGET_TIC_TABLE: dict[str, str] = {
    "TRAPPIST-1": "278892590",
    "AU Mic": "441420236",
    "TOI-700": "150428135",
    "WASP-12 b": "86396382",
    "HD 80606 b": "79075148",
    "Kepler-11": "011442793",   # KIC, 9-digit zero-padded
    "Kepler-4": "006541920",
    "Kepler-20": "006850504",
    "Kepler-90": "006114424",
    "K2-138": "211315939",
}
```

`_resolve_target_to_tic(t_name)` — direct hit, then substring match, returns `""` if not found.

### Methods (in dependency order)

| Method | Purpose |
|---|---|
| `_wipe_lightkurve_cache()` | `rmtree` of `~/.lightkurve/cache` (best-effort) |
| `_wipe_download_dir(download_dir)` | `rmtree(ignore_errors=True)` + `makedirs` |
| `_download_cache_dir()` | Ensures `_ASTRAEUS_LIGHTKURVE_CACHE_DIR` exists |
| `_call_with_timeout(fn, args, kwargs, timeout, label)` | Generic thread-based timeout wrapper for any callable |
| `_download_with_timeout(row, timeout, download_dir)` | Wraps `row.download()` in `_call_with_timeout` |
| `_is_fits_corruption(exc)` | Matches `"truncated"`, `"corrupt"`, `"not a fits"`, `"end-of-file"`, `"header missing"`, `"block does not begin"` in the exception message |
| `_row_cache_path(row, download_dir)` | Reproduces lightkurve's hard-coded `mastDownload/<obs>/<id>/<file>` cache layout |
| `_classify_stream_failure(exc)` | Returns a coarse failure tag: `"Target not observed"`, `"Stream truncated"`, `"Metadata mismatch"`, `"Network Timeout"`, or `"Download error: <msg>"` |
| `_s3_key_from_uri(data_uri)` | Maps a MAST dataURI to an S3 object key on `stpubdata`. Handles TESS prefix + Kepler prefix. Returns `None` for TESSCut products. |
| `_s3_download(s3_key, final_path)` | Anonymous boto3 download from `s3://stpubdata/{key}` to `final_path` via `.tmp` + `os.replace`. Region `us-east-1`, `signature_version=UNSIGNED`. |
| `_is_valid_fits(path)` | Reads first 80 bytes, checks for `SIMPLE  =` or `XTENSION=` magic. Used to evict corrupt stubs. |
| `_stream_mast_download(row, download_dir, read_timeout)` | **The workhorse.** Streams a MAST data product to disk with: FITS-validity probe + corrupt-stub eviction, S3 pre-try, HTTP streaming with 1 MiB chunks + Content-Length truncation check, exponential backoff with full jitter, atomic `.tmp + os.replace`, S3 post-retry fallback. |
| `_prioritize_search_results(search, mission_type)` | Drops long-cadence Kepler (exptime ≥ 1000s) and long-cadence TESS (exptime > 1800s) rows. Sorts by file size. |
| `_download_tess_lightcurves(search_result, download_dir)` | TESS-specific: per-sector validation, mixed-cadence detection, 120s row-read-timeout. Returns `(lc_list, error)`. |
| `_try_serve_from_cache(t_name, mission_type, download_dir)` | Cache-first fallback for when MAST search is unreachable. Scans `mastDownload/<mission>/` for valid FITS files matching the target's TIC/KIC. Builds a stitched LC, **applies BJD offset (I2 fix)**, returns `(lc_dict, None)` on hit. |
| `download_pipeline(t_name, mission_type)` | **The main public entry point.** Cache-first check, then MAST search, then per-mission download path, then float64 extraction, then BJD offset (I2 fix), then valid-mask + sort. Returns `(lc_dict, error)`. |
| `download_combined_fusion(safe_canonical)` | Kepler + TESS fusion. Queries NASA TAP for `ra, dec`, then runs both `download_pipeline` calls, per-mission median-normalizes, concatenates, returns unified dict. **I2 fix**: removed a redundant `(_UNIFIED_EPOCH - mission_epoch)` offset (both `download_pipeline` results are already in BJD full). |

### TESS multi-sector SPOC path

1. Cache-first via `_try_serve_from_cache`.
2. `lk.search_lightcurve(t_name, mission="TESS", author="SPOC")` (90s timeout).
3. `_prioritize_search_results` to keep short-cadence only (≤ 1800s exptime).
4. `_download_tess_lightcurves` — per-sector streaming + validation:
   - Each sector is staged to `mastDownload/TESS/<obs>/<id>/<file>` layout
   - `row.download()` is then local-only (lightkurve finds the file in cache)
   - 120s row-read-timeout (was 60s, bumped to handle fresh-FITS parse)
   - All-NaN flux → skip; empty LC → skip; mixed cadence → warn
5. `lk.LightCurveCollection(lc_list).stitch(corrector_func=lambda lc: lc.normalize())` — per-sector normalization kills baseline cliffs.
6. `stitched.remove_nans()`.
7. Float64 extraction + BJD offset + valid mask + sort.
8. Return `{time, flux, flux_err, time_unit: "BJD", bjd_epoch_offset_applied: 2457000.0}`.

### Kepler row-by-row path

1. Cache-first via `_try_serve_from_cache`.
2. `lk.search_lightcurve(t_name, mission="Kepler", author="Kepler")` (90s timeout).
3. For each row in `search[:_MAX_DOWNLOAD_SEGMENTS]` (H1 patch: 12, not 3):
   - `_stream_mast_download` (180s read-timeout).
   - 3 retry attempts of `row.download()`.
   - FITS-corruption detection + cache eviction on failure.
   - Break on first success.
4. `lk.LightCurveCollection(lc_list).stitch()`.
5. Same float64 + BJD + valid-mask pipeline.

### Why `_MAX_DOWNLOAD_SEGMENTS = 12` (H1 patch, 2026-07-06)

Original cap of 3 yielded a stitched baseline of ~218d for Kepler-90, starving 4/8 known planets (e, f, g, h with periods 91–331d) below the BLS 2.5×-period minimum. Longest known Kepler-90 period = 331.6d → 2.5×period = 829d. At ~88d/quarter for long-cadence Kepler, 12 quarters gives ~1056d baseline, which exceeds 2.5 × longest_target_period with margin.

### I2 fix (BJD unit normalization, 2026-07-06)

Before: `lc.time` was in BKJD (Kepler = BJD - 2454833) or BTJD (TESS = BJD - 2457000), silently compared to NASA `pl_tranmid` (BJD full) → 2454833-day offsets with no error signal.

After: every return dict carries `time_unit: "BJD"` and `bjd_epoch_offset_applied: 2454833.0` (or 2457000.0). The conversion happens at the ingestion boundary so downstream consumers get a consistent, explicitly-labeled epoch.

The same fix was applied to `astraeus/data/loader.py::extract_lightcurve_arrays` (which calls `to_bjd` from `astraeus/core/time_units.py`).

---

## 22. NASA Exoplanet Archive client

File: `astraeus/core/nasa_archive.py` (~250 lines).

### `NASAExoplanetArchive.normalize_target_name(raw: str) -> str`

Regex-based normalizer. Recognizes prefixes: `wasp`, `hat-p`, `kepler`, `k2`, `toi`, `tres`, `xo`, `gj`, `kelt`, `hd`, `hip`, `tyc`. Canonicalizes casing: `"wasp-12b"` → `"WASP-12 b"`, `"hatp-32b"` → `"HAT-P-32 b"`, etc.

### `NASAExoplanetArchive.sanitize_meta(meta: dict) -> dict`

Defaults for `orbital_period`, `pl_orbper`, `transit_depth`, `pl_trandep`, `stellar_radius`, `st_rad`, `st_teff`, `st_mass`, `sy_jmag`. Handles masked arrays and NaN/Inf.

### `NASAExoplanetArchive._metadata_name_candidates(canonical_name) -> list[str]`

Returns an ordered list of aliases to try in TAP queries. Key entries:
- The canonical name itself.
- `_KNOWN_ARCHIVE_ALIASES` special-cases (`"Kepler-13 b"` → `"KOI-13 b"`).
- `Kepler-N b` → `Kepler-N A b` (letter case variation).
- `Kepler-90` → `KOI-351` (Kepler-90 is KOI-351 in pscomppars; the generic `Kepler-N → KOI-N` would be wrong for it).
- **I3 fix (2026-07-06)**: Generic `Kepler-N → KOI-N` and `K2-N → K2-N` aliases for catalogued multi-planet systems, applied to any host name not already special-cased.
- Host star names (no planet letter) get a `"<host> b"` fallback.

### `NASAExoplanetArchive.fetch_metadata(canonical_name) -> tuple[dict, str | None]`

For each candidate alias:
1. TAP query: `SELECT pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror FROM pscomppars WHERE pl_name='<alias>' OR hostname='<alias>'`
2. 3 retries with 2s backoff on failure.
3. Returns `(meta_dict, error_or_None)`.

In the meta dict:
- `pl_orbper` — with `pl_period` and `pl_orbpererr1` fallbacks; then `_fetch_ps_orbital_period` from the `ps` table; defaults to `0.0`.
- `st_rad` — direct, or derived from `st_lum` + `st_teff` via `R = sqrt(10^L) * (5778/T_eff)^2`.
- `pl_trandep` — **I3 fix**: robust fallback chain: `pl_trandep` → `pl_ratror^2` → `pl_rade / (109.2 * st_rad) ^ 2` → `0.0` with `transit_depth_source` audit trail. NASA archive `pl_trandep` semantics: `>= 1.0` is in percent, `< 1.0` is a fraction.

---

## 23. Time-unit normalization

File: `astraeus/core/time_units.py`.

```python
_MISSION_BJD_OFFSET = {
    "Kepler": 2454833.0,
    "K2": 2454833.0,
    "TESS": 2457000.0,
}

def bjd_offset_for_mission(mission: str) -> float: ...
def to_bjd(time, mission: str) -> np.ndarray: ...
```

**I2 fix context**: Lightkurve returns time arrays in mission-specific offset units (BKJD for Kepler, BTJD for TESS). Every downstream consumer in this codebase — the orchestrator's BLS, the orchestrator's t0, the NASA archive comparison path, the reporting layer — was historically handed these arrays in BKJD/BTJD without unit awareness. Any comparison to a NASA `pl_tranmid` value (BJD full) was therefore silently offset by ~2454833 days.

This module centralizes the conversion so the fix lives in one place. Used by `astraeus/data/loader.py::extract_lightcurve_arrays` and called inline in `lightkurve_client.py::download_pipeline` and `lightkurve_client.py::_try_serve_from_cache`.

---

## 24. Constants, configuration, and key data classes

### `astraeus/core/constants.py` — the single source of truth

#### Geometry

```python
BOUND_ECCENTRICITY_MINIMUM = 0.0
BOUND_ECCENTRICITY_MAXIMUM = 1.0
HIGH_ECCENTRICITY_INITIAL_GUESS_THRESHOLD = 0.8
POSITIVE_QUANTITY_MINIMUM = 0.0
KEPLER_NEWTON_TOLERANCE = 1.0e-12
KEPLER_NEWTON_MAX_ITERATIONS = 64
HALF_TURN_ANGLE = π * u.rad
HALF_TURNS_PER_FULL_TURN = 2.0
FULL_TURN_ANGLE = 2π * u.rad
REFERENCE_LENGTH_UNIT = u.AU
```

#### Vetting (bucket 2)

```python
VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION = 0.03   # depth ceiling for planet candidate
VETTING_VSHAPE_LOW_SNR_GATE = 20.0                  # V-shape only vetoes when SNR is NOT overwhelming
VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD = 3.0        # GeometricValidator detection floor
VETTING_ULTRA_SHORT_PERIOD_DAYS = 1.5
VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0       # fallback when physical threshold unavailable
VETTING_U_VS_V_CHI2_DELTA_THRESHOLD = 0.001          # bucket 10: significance floor
```

#### GeometricValidator (bucket 2)

```python
GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES = 8
GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK = 0.10
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW = 0.05
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER = 0.05
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER = 0.15
GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES = 3
```

#### Detection emission gates (bucket 9.1 / 9.2)

```python
DETECTION_SNR_THRESHOLD_DEFAULT = 5.0    # caller-tunable; reverted from 7 in bucket 9.2
DETECTION_CONFIDENCE_FLOOR = 7.0         # load-bearing noise-rejection gate; unconditional
```

`DETECTION_CONFIDENCE_FLOOR = 7.0` is **empirically fit** to the bucket 9.1 sweep (50 pure-noise realizations + 5 real-signal scenarios):
- Noise confidence: min=1.79, median=2.87, max=5.96
- Real-signal confidence: floor=9.02, typical ~13-22

> The statistic itself — peak BLS power divided by median periodogram power — is analogous to Horne & Baliunas (1986) and Schwarzenberg-Czerny (1997), but those papers describe how to compute a **formal** false-alarm probability from the periodogram via chi-squared statistics; they do NOT bless "peak/median ratio of 7" as a threshold. A future maintainer should NOT read the literature references as implying 7.0 is justified by first-principles FAP — it is not. It is empirically fit to the synthetic sweep. See `reports/bucket9.1_summary.md` §6.

### `astraeus/core/config.py`

```python
def load_config(filepath: str = "config.json") -> Dict[str, Any]
def validate_config(config: Dict[str, Any]) -> None
```

Validates `llm_provider`, `llm_model`, `api_keys`.

### `astraeus/core/validation.py`

```python
def require_convertible_unit(value, unit, name) -> None
def require_non_negative_quantity(value, name) -> None
def require_positive_quantity(value, name) -> None
```

Used in `geometry.py` and `transit_model.py` for input checking.

### Key data classes (quick reference)

- `JobState` (orchestrator.py) — `PENDING`, `RUNNING`, `DONE`, `FAILED`, `CANCELLED`
- `PlanetParams`, `StabilityResult` (nbody_solver.py)
- `SyntheticTransitScenario`, `LightCurveSeries` (simulation/synthetic.py)
- `CompletenessSweepConfig`, `CompletenessSweepResult` (simulation/completeness.py)
- `DashboardSimulation` (dashboard/simulation.py)
- `DashboardTransitScenario` (dashboard/scenario.py)

---

## 25. The test surface and CI

### `tests/` — 35+ pytest files (`pytest -q`)

The full list of test files (organized by bucket/era):

**Discovery / unit tests:**
- `test_adapter.py` — `DataAdapter` unit tests (CSV/JSON/FITS)
- `test_orbital_models.py` — Orbital mechanics unit tests
- `test_physics.py` — First-principles physics tests
- `test_transit_model.py` — Transit model tests
- `test_preprocessing.py` — Preprocessing unit tests
- `test_synthetic_simulation.py` — Synthetic sim tests
- `test_loader.py` — `DataFactory` tests

**Detection / vetting tests:**
- `test_mcmc.py` — MCMC unit tests
- `test_bulletproof_detector.py` — Mathematical aliasing, state binding safety
- `test_dashboard_simulation.py` — Dashboard sim tests
- `test_vetting_threshold_hardening.py` — 9 threshold tests (Bucket 2)
- `test_ttv_nbody_validation.py` — TTV vs N-body cross-validation
- `test_completeness_sweep.py` — Completeness sweep tests
- `test_experiment_history.py` — History ledger tests

**Network tests:**
- `test_nasa_archive_network.py` — NASA archive network tests (`@network`)
- `test_debug_metadata_network.py` — Network metadata debug

**Stress / diagnostic (parametrized):**
- `test_pipeline_stress_test.py` — Pipeline stress
- `test_global_matrix_stress_test.py` — Global stress (parametrized, `@slow`)
- `test_solid_matrix_diagnostic.py` — SOLID matrix diagnostic
- `test_system_flight_bench.py` — System flight bench (`@smoke` + `@slow`)

**UI tests:**
- `test_ui_flow.py` — UI flow (file_uploader mock — Bucket 8 fix)
- `test_workbench_navigation.py` — Workbench nav (file_uploader mock — Bucket 8 fix)
- `test_fetched_analyze_button.py` — Detective "Analyze Telemetry" button flow

**Real data tests:**
- `test_multi_planet_search_real_data.py` — Kepler-90b real-data scenario
- `test_lab_realtime.py` — Sensitivity Lab realtime

**N-body tests:**
- `test_nbody_solver.py` — N-body Kepler-90b 6-planet

**Multi-planet tests:**
- `test_multi_planet_scaling.py` — Multi-planet scaling
- `test_agent_detective.py` — Detective agent routing + the **noise injection regression** (red by design, then fixed in bucket 9)
- `test_chaos_integration_suite.py` — Chaos integration
- `test_pipeline_smoke.py` — E2E smoke (Bucket 6)

**Round-2 diagnostic tests (2026-07-06 → 2026-07-12):**
- `test_i1_classifier_multiplanet.py` — Cross-vetting runs unconditionally
- `test_i2_bjd_unit.py` — BJD unit normalization
- `test_i3_hostname_alias.py` — NASA hostname aliases
- `test_i4_apptest_smoke.py` — AppTest smoke
- `test_j1_alias_rejection.py` — BLS window-aware alias rejection
- `test_j2_orchestrator_states.py` — Orchestrator state machine
- `test_j3_bls_single_signal_regression.py` — BLS single-signal regression
- `test_j3_orchestrator_e2e_verified.py` — Orchestrator E2E
- `test_j3_syn5p_small_recovery.py` — SYN-5P small recovery
- `test_r8_vetting_override_regression.py` — "Likely Planet" override gated on `is_valid`

### `tests/conftest.py` and `tests/_fixtures/fakes.py`

`conftest.py` resets Streamlit `DeltaGeneratorSingleton` between tests (Bucket 5 fix that unmasked 3 file_uploader mock bugs in Bucket 8). `_fixtures/fakes.py` provides shared test doubles (`FakeLightkurveRow`, `FakeSearchResult`, `FakeHttpClient`, `FakeClock`, `FakeFs`).

### CI / GitHub Actions (Bucket 5)

`.github/workflows/` (Bucket 5): **fast-gate** job runs `@smoke`-marked tests + a sample of full suite; **non-blocking full-suite** runs the rest. Posttest output is saved to `docs/ci/bucket5_*`.

### Markers (`pytest.ini`)

- `@smoke` (fast, CI gating)
- `@network` (require live network)
- `@slow` (excluded by default)

### Test baseline (latest)

Bucket 9.1 post-fix: 81 passed, 1 skipped, 33 deselected, exit 0. Bucket 9.2 same envelope. Bucket 3 baseline (earlier): 85 passed.

### QA scripts (`scripts/`)

- `qa_runner.py` — v1 runner.
- `qa_runner_v2.py` — **v2 runner**, cached + dynamic dual-mode (8 cached + 5 dynamic targets). Markdown reporter (`v2_harness`).
- v2 phases: A = backend pre-flight (cache-or-network); B = UI flow with 3 snapshots per target.
- `qa_targets.yaml` — manifest of 8 cached + 5 dynamic targets used by v2 harness.
- `scripts/manual_tests/` — awaiting pytest conversion. Most have already been pulled into `tests/test_*.py`; originals moved to `deprecated/` as they're upgraded.

---

## 26. Round-7 / Round-8 fixes log (post-v0.0.2 briefing)

The v0.0.2 briefing was snapshotted at 2026-07-05. Between then and now (2026-07-12), several round-2 diagnostic fixes landed. They are referenced as `H1`, `I1`, `I2`, `I3`, `I4`, `J1b`, `J1c`, `J2`, `J2c`, `J3`, `J7c`, `R7`, `R8` in the code comments. Here's the full log:

### H1 patch (2026-07-06) — Kepler row-by-row segment limit

`lightkurve_client.py::_MAX_DOWNLOAD_SEGMENTS`: `3 → 12`. A cap of 3 yielded a ~218d stitched baseline for Kepler-90, starving planets e/f/g/h (91–331d) below the BLS 2.5×-period minimum. 12 quarters gives ~1056d baseline, covering 2.5 × longest target period with margin.

### I1 fix (2026-07-06) — Cross-vetting runs unconditionally

In `detection.py`, the false-positive cross-vetting branches were previously gated on `is_valid = (snr > snr_threshold) and (confidence_score >= DETECTION_CONFIDENCE_FLOOR)`. In a multi-planet curve, the periodogram-wide `confidence_score` is elevated by every other signal, so a clean peak at p1 can fail the 7.0 floor when 4 other real planets also contribute periodogram power. The fix: cross-vetting runs **unconditionally** on every peak that BLS returns. The emission-gate `is_valid` still controls `candidate_found` / `is_candidate` for callers that want a strict "must-clear-the-floor" emission.

### I2 fix (2026-07-06) — BJD unit normalization

See §23. Every LC dict now carries `time_unit: "BJD"` and `bjd_epoch_offset_applied`. Affected files: `lightkurve_client.py` (3 sites: `_try_serve_from_cache`, `download_pipeline`, `download_combined_fusion`), `data/loader.py` (`extract_lightcurve_arrays`, `NASAArchiveLoader.load`), `time_units.py` (centralized `to_bjd`), `detection.py` (added `t0_bjd` + `time_unit` to result dict).

### I3 fix (2026-07-06) — Robust depth-fallback chain in NASA archive

When `pl_trandep` is NULL and the secondary fallbacks (`pl_ratror`, geometric `pl_rade / st_rad`) also fail, the depth was silently returned as 0.0. Now we fall back through `pl_trandep` → `pl_ratror^2` → `pl_rade / (109.2 * st_rad)^2` → explicit `0.0` with `transit_depth_source` audit trail. Round-1 evidence: Kepler-90 i has NULL `pl_trandep` — under the old code, that planet's depth was lost with no indication.

### I3 fix (2026-07-06) — Generic NASA hostname aliases

Generic `Kepler-N → KOI-N` and `K2-N → K2-N` aliases added for catalogued multi-planet systems. Previously only `Kepler-13 b → KOI-13 b` and `Kepler-90 → KOI-351` were special-cased.

### I4 fix (2026-07-06) — AppTest smoke

`test_i4_apptest_smoke.py` added. (See test suite list.)

### J1b fix (2026-07-06) — BLS curve-size-adaptive `frequency_factor`

In `bls_search.py::search`, replaced the legacy `np.linspace` linear grid with `astropy.timeseries.BoxLeastSquares.autoperiod` driven by an empirical `frequency_factor = max(1.0, T_baseline^2 / 4500.0)` capped at 500. Profile data:
- 10d smoke (ff=1.0, 1801 periods)
- 200d kepler90d (ff=8.9, 89k periods, 7.2s wall)
- 1500d syn5p 5-planet (ff=500, 90k periods, 3.6s wall, 4/5 recovered)

### J1c fix (2026-07-06) — BLS window-aware alias rejection

In `bls_search.py::search`, added Lomb-Scargle periodogram of the time sampling to detect window alias frequencies. Rejects candidates that are integer harmonics (0.25×, 0.33×, 0.5×, 1×, 2×, 3×, 4×, 5×) or window aliases (`f_cand ≈ |f_prev ± k*f_window| / m` for k, m ∈ {1..5}) of `known_periods`.

### J2 / J2c fix (2026-07-06) — TLS nested-pool + three-outcome gate

`detection.py` TLS call forces `use_threads=1` because `detect_transit_candidate` runs inside `orchestrator._subprocess_search_worker` (daemon=True on Windows, where daemonic processes can't spawn children). TLS's default `use_threads=cpu_count()` would raise `AssertionError: "daemonic processes are not allowed to have children"`.

Three TLS outcomes are now tracked via sentinels: `tls_valid=True` (success), `tls_environment_error` (`AssertionError`/`RuntimeError`), `tls_scientific_error` (any other `Exception`). The infra branch is logged loudly with `[TLS-INFRA-ERROR]` prefix.

Test: `tests/characterize/test_tls_call_path_contract.py::test_tls_except_block_distinguishes_infra_from_scientific`.

### J3 fix (2026-07-06) — BLS physical mask at 0.2 duty cycle

In `bls_search.py::search`, `(period, duration)` pairs where `duration > 0.2 * period` are set to `power = -inf` so they cannot win `argmax`. Root-cause fix for degenerate boundary peaks (e.g. `P=0.5d, dur=0.4d`). The 0.2 cap is the standard physical upper bound for transit + grazing-binary configurations.

### J3 follow-up — 5%-margin rejection near p_min / p_max

A candidate like `(P=0.5002d, dur=0.1d)` is at the duty-cycle boundary AND very near `p_min=0.5d`, where the autoperiod grid concentrates degenerate points. These are noise peaks, not real signals. 5% margin at p_min and p_max (matching `test_j3_bls_single_signal_regression.py` and `test_j3_syn5p_small_recovery.py`).

### J7c — Kepler-90 E2E run

Confirmed the J-series fixes on the real Kepler-90 curve. Surfaced the R8 bug below.

### R7 — orchestrator state machine + monitoring

In `orchestrator.py`, the subprocess worker `_subprocess_search_worker` and monitor thread `_monitor_worker` are the canonical R7 surface. The async `submit_multi_planet_search` returns a `job_id` for `get_job_status` polling. Cancellation via `cancel_job` hard-terminates the daemon process.

### R8 fix (2026-07-12) — "Likely Planet" override gated on emission gate

In `detection.py`'s false-positive cross-vetting, the branch that overrides the "Likely Planet" shape-vet verdict to "Verified Planet Candidate" was previously unconditional. On the J7c real Kepler-90 run: iter 1 found a spurious 489.13d peak, TLS correctly rejected (`tls_sde=4.22 < 5.0`, `tls_valid=False`), but this branch then stamped "Verified Planet Candidate" anyway, and the orchestrator accepted and subtracted the spurious signal, burning an iteration slot.

Fix: gate the override on `is_valid` (the conjunction of SNR threshold + confidence_score floor + TLS gate). The orchestrator's GUARDRAIL 1 in the subprocess worker also has defense-in-depth (`_GUARDRAIL1_MARGINAL_TOLERANCE = 3` — up to 3 marginal subtractions before breaking early).

Test: `tests/test_r8_vetting_override_regression.py`.

### Other recent quality-of-life improvements

- **PDF figure embedding: Matplotlib fallback** (Vector A2 / STEP-1 headless handling). When `kaleido` is missing or Chromium fails, `_rasterize_with_matplotlib` rebuilds the chart from Plotly trace data using matplotlib's `Agg` backend. Worst case: a styled text canvas placeholder.
- **`LightkurveClient` H1 patch** + I2 BJD normalization + FITS validity probe + S3 fallback chain (3 retry paths: pre-MAST, post-MAST, atomic temp + rename) + TESS short-cadence prioritization (drop exptime > 1800s).

---

## 27. Deprecated / dead paths — DO NOT IMPORT

Anything matching these is dead, was moved in Bucket 1, and is excluded by `pytest.ini`:

- `astraeus.ui.*` → `deprecated/astraeus_ui_dashboard/` (older copy of `app.py`; only importer was a non-pytest chaos script).
- `astraeus.dashboard.ui.{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py` → `deprecated/astraeus_dashboard_ui/` (self-referential dead cluster).
- `astraeus.data.discovery` → `deprecated/astraeus_data_discovery/` (second `RemoteDiscoveryEngine`).
- `astraeus/dashboard/services/{action_deck.py, data_ingestion.py, mcmc_retrieval.py}` — **ORPHANED**, not touched in Bucket 1. Imported only by deprecated UI panels and deprecated `data/discovery.py`. Flagged in `reports/bucket1_orphan_investigation.md` §5 for later cleanup.
- `astraeus/ui/dashboard.py` → `deprecated/astraeus_ui_dashboard/` — older parallel copy of `app.py`.

### Heuristic for new code

- **If you want a streamlit component**, look in `astraeus/dashboard/ui/` (layout, styles, components, settings).
- **If you want an ingestion façade**, use `astraeus.core.ingestion.RemoteDiscoveryEngine`.
- **If you want a page implementation**, look in `ui/pages/`.

---

## 28. What is WORKING right now (verified)

✅ Streamlit app launches (`streamlit run app.py` from project root).
✅ Dashboard renders 3-panel workbench with 6-tab sidebar navigation.
✅ Discover tab renders the precomputed Kepler-90 baseline payload, per-candidate phase-folded synthetic plots, SNR slider, Manuscript button → PDF download.
✅ Floating AI chat popover renders (mock response, no live LLM unless keys set).
✅ Remote data fetch works **with cache-first fallback**: in offline / MAST-down scenarios, TESS or Kepler LCs are assembled from local FITS cache (no network).
✅ TESS multi-sector SPOC stitch handles mixed-cadence sectors, per-sector normalization kills baseline cliffs, corrupt sectors evicted.
✅ Kepler streaming falls back to unsigned S3 stpubdata when MAST HTTPS hangs.
✅ `detect_transit_candidate` runs the 9-stage pipeline and applies dual-gate (SNR + confidence floor) + TLS validation so pure-noise BLS false positives are rejected.
✅ Vetting decision tree (U/V shape + secondary-eclipse + depth) labels correctly across all 5 buckets (Verified, Binary, V-shaped, Atmospheric Occultation, Binary at Phase 0.5).
✅ Multi-planet orchestrator finds Kepler-90b-like systems in real data, with anti-duplicate/harmonic guardrail + R8 defense-in-depth.
✅ Async multi-planet search via `submit_multi_planet_search` with status polling + cancellation.
✅ N-body solver (Velocity Verlet) runs Kepler-90b six-planet scenario stably (verified in `test_nbody_solver.py`).
✅ TTV analysis + Lomb-Scargle periodicity extraction + analytical amplitude proxy filter all wired.
✅ Completeness sweep runs and caches 18 cells in ~17 min (bucket 3 verified).
✅ PDF manuscript compiles via reportlab + kaleido with **graceful Matplotlib fallback** (Vector A2 / STEP-1 headless handling).
✅ Experiment history ledger writes `logs/experiments.json` atomically; History tab reads it.
✅ `python astraeus/main.py` runs TrES-2b Kepler Q1 end-to-end via `RealDataPipeline`.
✅ I2 fix: every LC dict now carries `time_unit: "BJD"` and `bjd_epoch_offset_applied` (no more silent 2454833-day offsets).
✅ H1 patch: Kepler row-by-row limit raised to 12 segments (~1056d baseline → covers all known Kepler-90 planets).
✅ J1b/J1c/J3 fixes: BLS uses curve-size-adaptive frequency_factor, window-aware alias rejection, and 0.2 duty-cycle physical mask.
✅ J2c fix: TLS gate distinguishes infrastructure failure from scientific failure via `tls_environment_error` / `tls_scientific_error` sentinels.
✅ R8 fix: "Likely Planet" override in cross-vetting gated on the production emission gate (`is_valid`).
✅ 81 pytest baseline passes (`@smoke` + main suite; some `@slow` and `@network` deselected).

---

## 29. Known rough edges, placeholders, and open issues

⚠️ **Discover tab is hard-coded to a Kepler-90 baseline payload** (`BASELINE_PAYLOAD` in `app.py:29-38`). It does NOT actually invoke the discovery pipeline — it just renders 4 pre-computed candidates (266.9d, 211.7d, 238.6d, 663.1d). The real discovery happens in the **Detective** tab.

⚠️ **`"Dual-Zone Grid: ACTIVE"`** and **`"1.5x Wing Subtraction: ACTIVE"`** are static UI labels in the Discover sidebar (`app.py:259-260`). The actual Dual-Zone logic lives only in the Detective page's pipeline.

⚠️ **Decorative phase-folded figures** in `app.py` (`_build_phase_folded_figure`) are **synthesized from the candidate's own depth/duration/t0** — they read the candidate dict and render a deterministic box-window dip + Gaussian noise. They are NOT derived from real photometry.

⚠️ **`astraeus/dashboard/services/`** (`action_deck.py`, `data_ingestion.py`, `mcmc_retrieval.py`) is **dead/orphaned**: only imported by the deprecated UI panels and deprecated `data/discovery.py`. Not touched in Bucket 1.

⚠️ **Solid/SRP refactor is designed but only Phase 0 (seams) landed.** The plan at `docs/superpowers/plans/2026-06-30-data-ingestion-solid-refactor.md` is untracked; Phase 0 added `HttpClientPort`, `FsPort`, `ClockPort`, `LightkurveRowPort` protocols in `astraeus/core/clients/` (no production rewire). The implementation plan calls for `MastStreamer`, `S3FallbackDownloader`, `TapClient`, and `PsCompanion` to plug onto `HttpClientPort` in subsequent phases.

⚠️ **README/PRD are partially stale.** They don't mention: TTV analysis, N-body solver, multi-planet orchestrator, vetting engine, physical properties engine, completeness sweep, experiment ledger, or that there is one ingestion engine with two entry points. The **authoritative doc is `docs/ARCHITECTURE.md`** plus this knowledge base.

⚠️ **`prd_v2.md`** (newer PRD, "Version 2.0") is **aspirational portfolio vision** — Next.js + TypeScript + Three.js frontend, FastAPI backend, PostgreSQL, Qdrant, LangGraph/LangChain, etc. **None of this is built.** The actual codebase is the Streamlit/Python stack described above.

⚠️ **`astraeus/analysis/detection.py:198` default** — when `vetting_status == "Likely Planet"` and `is_valid` (R8 fix), falls to `Verified Planet Candidate`. Behavior is sound but worth knowing.

⚠️ **TTV analysis on multi-planet systems** (Detective Keplerian pipeline) only extracts O-C from single BLS winner; doesn't yet propagate the multi-planet subtraction residuals into per-planet TTV curves.

⚠️ **`astraeus/dashboard/services/mcmc_*` are not implemented.** All MCMC UI infrastructure (`mcmc_panel.py`, `mcmc_form.py`) was deprecated — only MCMC test (`test_mcmc.py`) and `analysis/error_analysis.py` (emcee) remain.

⚠️ **Floating AI chat (`components.py::render_floating_chat`) is currently MOCK** — generates a placeholder response. Real `LLMClient` wiring is TODO.

⚠️ **`scripts/manual_tests/`** are flagged for pytest conversion. `deprecated/` already contains moved originals.

⚠️ **`boto3>=1.28.0`** is a runtime dep (`requirements.txt`) used only for the S3 fallback in `LightkurveClient` — costs ~80 MB of install weight for a rarely-triggered path.

⚠️ **Testing of UI tabs is structural** (workbench navigation, file_uploader mock) — NOT visual regression. `err.log` / `pytest_out.txt` / `qa_results.json` carry recent run traces.

⚠️ **TLS dependency is optional.** `transitleastsquares` is not in `requirements.txt`. If missing, `tls_valid = True` (fail-open) and a warning is printed. Real BLS+TLS work needs `pip install transitleastsquares`.

---

## 30. Conventions, env vars, branch hygiene, commit style

### Numeric precision
- **All light-curve arrays are `np.float64`** — explicit `dtype=np.float64` guards throughout `LightkurveClient`. Sub-400 ppm transit signals cannot survive float32.

### Vetting thresholds
- All live in `astraeus/core/constants.py` — not inlined as magic numbers. Bucket refactors (2, 9.1, 9.2, 10) replaced inline constants with named ones.

### Cache directories
- `~/.lightkurve/cache` (lightkurve's default)
- `os.environ.get("ASTRAEUS_LIGHTKURVE_CACHE_DIR", "<tmp>/astraeus_lightkurve_cache")` (astraeus's)
- Both writable under `tests/conftest.py`.

### Experiment ledger
- `logs/experiments.json` — every `detect_transit_candidate` call appends an entry. Atomic writes via `.tmp + os.replace` (in `ExperimentLedger`). Suppressed during pytest via conftest isolation (bucket 9.2).

### Reporting figure keys
- `<star_id>-1<N>` convention (e.g. `KIC 11442793-11` for candidate 1). Generated figures are deterministic per candidate via a seeded `np.random.default_rng`.

### Test configuration
- `pytest.ini` excludes `deprecated/` and registers `@smoke`, `@slow`, `@network` markers.
- `ASTRAEUS_FORCE_NETWORK=1` env var bypasses the Lightkurve cache lookup — used by QA harness to exercise the dynamic MAST/S3 path.

### Branch hygiene
- Active branch: `v.0.0.2`. Three merge commits locked the bucket 8/9/9.2 work into this branch. No tags exist yet.

### Commit convention
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`, `merge:`) with a scope tag (`(ingest)`, `(qa)`, `(analysis)`, `(batching)`, `(ci)`, …).

### ASCII-only constraint in PDF
- `reportlab` core fonts can't render non-ASCII. `reporting.py::sanitize_text` regex-replaces Greek letters (α→alpha), ±, °, ≥, ≤, em-dash, smart quotes, etc. into ASCII before embedding.

---

## 31. Known breakage points

The user has reported casualties. Most likely problem zones, ranked by frequency:

1. **LLM chat not responding** — `config.json` `api_keys` are empty; provider reports OK but calls fail silently. Must set keys in config or via env vars. (Note: the live floating chat is a **mock** anyway; this only affects the MCMC explanation path.)

2. **MAST search hangs / timeouts** — lightkurve's default 180s read timeout can't serve TESS FFIs. v0.0.2 already raised this to 600s (`_TESS_READ_TIMEOUT`). If you see truncated FITS or `Empty data_uri` warnings, check the cache dir.

3. **PDF manuscript figures render as placeholders** — missing `kaleido==0.2.1` (or version mismatch with installed `plotly` 5.24). v0.0.2+ added a Matplotlib rasterizer fallback (`_rasterize_with_matplotlib`) that rebuilds the chart from trace data using Agg backend. Worst case: a styled text canvas placeholder.

4. **Discover tab "shows zero candidates"** — only if `BASELINE_PAYLOAD` is mutated in session_state. Reset clears it back to the 4-planet Kepler-90 baseline.

5. **Multi-planet orchestrator infinite-loops on duplicate** — bounded by `max_duplicate_retries=3` and `iteration > max_signals + max_duplicate_retries`. If it still loops, suspect `batman` import failure (silent fallback to Trapezoidal is correct; log line `[Fallback] batman failed or unavailable` is expected).

6. **TLS gate emits "infra error"** — Windows daemonic-process `AssertionError`. J2c fix surfaces this as `tls_environment_error` (not silent). Either run on Linux/macOS, or accept the `tls_valid=False` and let the R8 defense-in-depth guard catch it.

7. **`err.log` / `err2.log` at project root** — historical stderr traces from LightkurveClient (S3 fallback, cache eviction, FITS corruption). These are NOT errors; they're the engine's "I'm being careful" chatter.

8. **pytest deselects 33 tests** — those are `@slow` or `@network` markers. Run with `pytest -m ""` to include.

9. **TLS not installed** — `tls_valid = True` (fail-open). Real BLS+TLS work needs `pip install transitleastsquares`.

10. **BLS+TLS profile ~80s per call on long curves** — the J2c profile. Mitigated by the 0.95×-1.05× window. If you find this too slow, the only safe tuning is to expand the period window slightly (looser gating), never to relax `use_threads=1` (which would crash on Windows daemonic workers).

---

## 32. Dev infrastructure, tooling, and roadmap

### Dev infrastructure

- **`.windsurfrules` & `AGENTS.md`** — mandate CodeGenome MCP usage: prefer `search_nodes`, `get_neighbors`, `get_changes` over `grep`. Cache at `.genome/watcher.db`.
- **`.genome/`** — CodeGenome graph cache (live). If MCP transport is up, query via `http://127.0.0.1:7331/mcp` (stdio or HTTP) before falling back to direct file reads.
- **`dev-knowledge-base/`** — Currently empty in the working tree. Was intended as research notes; **this document is the canonical knowledge base instead.**
- **`docs/superpowers/`** — 3 design+plan doc pairs:
  - `2026-06-23-completeness-sweep` (designed + implemented)
  - `2026-06-27-qa-v2-dual-mode` (designed + implemented)
  - `2026-06-30-data-ingestion-solid-refactor` (designed; **Phase 0 seams landed**, full refactor not yet implemented)
- **`docs/ARCHITECTURE.md`** — Authoritative architecture doc. (Read this if you only read one doc.)
- **`docs/round-8-plan.md`** — Full bucket-by-bucket implementation plan (Buckets 0-10) for the post-MVP polish sequence.
- **`docs/astraeus_agent_implementation_briefs.md`** — Round-2 R7-R8 implementation briefs.
- **`scripts/qa_targets.yaml`** — manifest of 8 cached + 5 dynamic targets used by v2 harness.
- **`tests/reports/`** — solid_audit_log.json, ai_audit_payload.json, run logs.
- **`outputs/completeness_sweeps/<sha256(config)>/`** — per-sweep outputs.
- **`reports/`** — Generated audit reports (gitignored). Includes `bucket1_orphan_investigation.md`, `bucket2_threshold_audit.md`, `bucket9.1_signal_detection_audit.md`, `bucket9.2_summary.md`, `bucket10_threshold_audit.md`, etc.

### Roadmap

#### Done (in this branch)

- Buckets 0, 1, 2, 5, 6, 7, 8, 9.1, 9.2, 10 — see `docs/round-8-plan.md` for the full sequence.
- H1 patch (Kepler row-by-row segment limit).
- I1, I2, I3, I4 fixes (round-2 diagnostic).
- J1b, J1c, J2, J2c, J3 fixes (round-2 diagnostic).
- R7 (orchestrator state machine) and R8 ("Likely Planet" override gating).
- Matplotlib PDF figure fallback (Vector A2 / STEP-1 headless handling).
- I3 fix: robust depth-fallback chain in NASA archive.

#### Open (designed, not implemented)

- **Bucket 3 (full) — Injection-recovery completeness sweep expansion.** Phase 1 (5×3×3 = 45 cells) is built and tested. Bucket 3 proper extends the grid to cover the parameter space needed for the publishable completeness map.
- **Bucket 4 (full) — N-body ↔ TTV cross-validation.** Bucket 9.2 work started this. Needs a full empirical TTV study.
- **Bucket 5 (remaining) — Network-test consolidation.** Some tests still do network I/O at import time; needs cleanup.
- **Solid/SRP refactor — Phase 1+.** Only Phase 0 (seams) landed. The plan calls for `MastStreamer`, `S3FallbackDownloader`, `TapClient`, `PsCompanion` to plug onto `HttpClientPort`. Currently the seams are unused by production code.
- **MCMC UI revival.** All MCMC UI infrastructure was deprecated. The `emcee`-based MCMC in `analysis/error_analysis.py` is unit-tested but not wired into a dashboard control surface.
- **Floating AI chat — real LLM wiring.** Currently a mock. `LLMClient` is ready; needs UI plumbing.
- **`prd_v2.md` aspirational frontend** — Next.js + TypeScript + Three.js. NOT IMPLEMENTED; treat as portfolio vision only.

---

## 33. Question-answering guide for a downstream AI

This doc is structured so the following kinds of questions map cleanly to sections:

| If the user asks… | Read… |
|---|---|
| "How do I run the app?" | §3, §5 |
| "What is this project?" | §1 |
| "What tech stack is used?" | §2 |
| "Where is the layout / repo structure?" | §4 |
| "What do the 6 dashboard tabs do?" | §5 |
| "How does data ingestion work?" | §6, §21, §22, §23 |
| "How does transit detection work?" | §7, §8 |
| "How does BLS work?" | §9 |
| "How does TLS work?" | §10 |
| "How does detrending work?" | §11 |
| "How does vetting work?" | §12 |
| "TTV analysis?" | §13 |
| "N-body solver?" | §14 |
| "Multi-planet orchestrator?" | §15 |
| "Simulation / completeness sweep?" | §16 |
| "How do I generate a PDF report?" | §17, §5 (Discover tab) |
| "Where are experiments logged?" | §18 |
| "Where's the LLM integration?" | §19 |
| "How is the dashboard shell structured?" | §20 |
| "Where are the constants / config?" | §24 |
| "How is the test suite organized?" | §25 |
| "What changed since v0.0.2?" | §26 |
| "What NOT to import / touch?" | §27 |
| "What's working / broken?" | §28, §29 |
| "How are env vars / branches managed?" | §30 |
| "What is a common failure mode?" | §31 |
| "Where's the design doc / roadmap?" | §32 |
| "Why doesn't the README match the code?" | §29 (⚠️ staleness list) |
| "What's in `prd_v2.md` — is it real?" | §29 (no — aspirational) |
| "How do I add a new analysis engine?" | §24 conventions + §12 for the engine pattern |

End of knowledge base. For corrections or additions, update the relevant section and bump the snapshot date in §0.
