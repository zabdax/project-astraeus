# PROJECT ASTRAEUS — v0.0.2 Briefing

> **Purpose:** Self-contained description of the v0.0.2 state of Project Astraeus, suitable for feeding into another LLM for Q&A. Captures what's working, what's present in the code, what is deprecated, and known rough edges.
>
> **Snapshot date:** 2026-07-05
> **Branch:** `v.0.0.2` (in sync with `origin/v.0.0.2`)
> **Working tree:** 1 modified file (`logs/experiments.json` — auto-appended), 1 untracked (`docs/superpowers/plans/2026-06-30-data-ingestion-solid-refactor.md`)
> **Python:** 3.10+ (project tested on 3.11/3.12 — pycache dirs show both)

---

## 1. What this project is

Computational astrophysics platform for exoplanet transit modeling + MCMC parameter retrieval + AI-assisted analysis. Single-language Python + Streamlit app. First-principles physics engine (no ML physics shortcuts), Bayesian retrieval (emcee), and a multi-tab Streamlit dashboard with LLM copilot and PDF manuscript export.

Tagline (from README): *"Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space."*

**Author:** Zubayer Hasan Shaad ("ZUXLO"). MIT-licensed.

---

## 2. Top-level layout (live, ignore `deprecated/`)

```
project-astraeus/
├── app.py                         # ONLY live Streamlit entry point
├── route.py                       # Routes non-Discover tabs
├── config.json                    # LLM provider + API keys (no keys set in repo)
├── requirements.txt               # Runtime deps (numpy, scipy, astropy, lightkurve, emcee, etc.)
├── requirements-dev.txt           # Dev/QA deps (pytest, etc.)
├── pytest.ini                     # markers @smoke, @slow; --ignore=deprecated
├── .windsurfrules, AGENTS.md      # CodeGenome MCP directives (must use .genome MCP first if available)
│
├── ui/                            # Live Streamlit feature pages (UI root lives here)
│   └── pages/                     # NOTE: separate from astraeus/dashboard/ui/
│       ├── simulator.py           # Simulation Workbench
│       ├── lab.py                 # Lab (sensitivity_engine)
│       ├── detective.py           # Detective (multi-planet discovery)
│       ├── history.py             # Experiment history viewer
│       └── settings.py            # Settings panel
│
├── astraeus/                      # Core Python package
│   ├── main.py                    # CLI: RealDataPipeline (TrES-2b Kepler Q1)
│   ├── core/                      # Physics + data engine (12 modules)
│   ├── data/                      # Local ingest + adapter (3 live + 1 deprecated)
│   ├── simulation/                # Synthetic + completeness sweep
│   ├── analysis/                  # Detection/fitting/reporting (12 modules)
│   ├── visualization/             # Matplotlib static figures + completeness map
│   ├── workflows/                 # RealDataPipeline CLI orchestrator
│   ├── dashboard/                 # Shared library imported by app.py + ui/pages
│   │   ├── ui/{layout,styles,components,settings}.py   # LIVE shell
│   │   ├── ui/{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py  # DEPRECATED→deprecated/astraeus_dashboard_ui/
│   │   ├── services/              # NOT touched by Bucket 1 (orphans)
│   │   ├── figures.py, simulation.py, scenario.py, validation.py  # LIVE
│   ├── logs/research_log.md       # Stub
│   └── data/discovery.py          # DEPRECATED→deprecated/astraeus_data_discovery/
│
├── tests/                         # 35 pytest files + conftest + reports/
├── scripts/                       # QA runners + manual tests (partially pytest-converted)
│   ├── qa_runner.py, qa_runner_v2.py, qa_targets.yaml
│   └── manual_tests/              # Awaiting pytest conversion
├── docs/
│   ├── ARCHITECTURE.md            # AUTHORITATIVE architecture doc — read first
│   ├── superpowers/{plans,specs}/ # 6 design docs (completeness-sweep, QA v2, SOLID refactor)
├── dev-knowledge-base/            # Research knowledge base
├── deprecated/                    # 3 deprecated clusters (pytest --ignore)
├── logs/                          # experiments.json ledger + QA/streamlit logs
├── outputs/                       # Sweep artifacts etc.
├── reports/                       # Generated audit reports (gitignored)
├── runs/                          # Runtime outputs (gitignored)
├── .genome/                       # CodeGenome MCP cache (must use MCP tools first)
└── .cursor/                       # Cursor IDE settings
```

---

## 3. The ONE live launch path

```
$ streamlit run app.py                        # project root
        │
        ▼
   app.py
        │
        ├─ astraeus/dashboard/ui/layout.py::workbench_layout()        # 3-panel canvas + sidebar
        ├─ astraeus/dashboard/ui/styles.py::inject_page_styles()
        ├─ astraeus/dashboard/ui/components.py::render_floating_chat() # bottom-right AI chat popover
        │
        ├─ if selected_feature == "Discover":  INLINE in app.py:192-292
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

All feature pages read data via:
    astraeus.core.ingestion.RemoteDiscoveryEngine.fetch_data(target, mission)
    astraeus.core.orchestrator.run_multi_planet_search(lightcurve_dict)
    astraeus.analysis.detection.detect_transit_candidate(time, flux, ...)
```

> **Critical for downstream models:** `astraeus/ui/dashboard.py` and any path beginning with `astraeus/ui/` is **dead** — moved to `deprecated/astraeus_ui_dashboard/`. Do not import from `astraeus.ui.*`. The live UI is `app.py` at project root.

---

## 4. Data ingestion — one engine, two entry points

Single source of truth: **`astraeus/core/ingestion.py::RemoteDiscoveryEngine`** (line 24).

```
RemoteDiscoveryEngine (stateless facade)
   ├─ _fetch_data_impl(target, mission)        # pure-Python, no Streamlit dependency
   │      └─ fetches NASA Archive metadata (TAP/pscomppars) then
   │         bridges to MAST via LightkurveClient.download_pipeline(...)
   │   supports missions: TESS / Kepler / NASA Exoplanet Archive (bridges→TESS,Kepler)
   │                      Combined Baseline (Kepler+TESS fusion)
   │
   └─ fetch_data(target, mission)              # @st.cache_data(ttl=3600) wrapper
          └─ attached dynamically at module load; lazy-imports streamlit
             inside its function body so headless scripts never pay the cost.
```

Underlying pieces:
- **`astraeus/core/nasa_archive.py::NASAExoplanetArchive`** — TAP client for `pscomppars`, target-name normalizer.
- **`astraeus/core/lightkurve_client.py::LightkurveClient`** — MAST client. Big module (~920 lines). Handles:
  - **Cache-first fallback** — if MAST search is unreachable but FITS files exist in `_ASTRAEUS_LIGHTKURVE_CACHE_DIR` (default: `$TMP/astraeus_lightkurve_cache`), assembles a stitched LC from disk → zero network. Bypassed via `ASTRAEUS_FORCE_NETWORK=1` env var.
  - **TESS multi-sector SPOC** (`_download_tess_lightcurves`) — uses `download_all()`, per-sector validation (drop empty/all-NaN), per-sector median normalization via `stitch(corrector_func=lambda lc: lc.normalize())` to kill baseline cliffs.
  - **Kepler row-by-row** (`_stream_mast_download`) — per-segment streaming with atomic-rename into `mastDownload/<obs>/<id>/<file>` layout, exponential backoff (2s/4s/8s with jitter), FITS-validity probe (SIMPLE= / XTENSION= header), corrupt-stub eviction.
  - **S3 anonymous fallback** — `s3://stpubdata/{kepler|tess}/public/...` via unsigned `boto3`, used both pre-MAST (best-effort) and post-MAST-retry (last resort).
  - **Float64 precision policy** — every extraction/concatenation enforces `dtype=np.float64` (shallow transits <400 ppm need it; float32 only gives ~7 digits).
  - **TIC table** — small curated dict for offline name→TIC lookup (TRAPPIST-1, AU Mic, TOI-700, Kepler-11/4/20/90, K2-138, WASP-12b, HD 80606b).
  - **Timeouts** — TESS read 600s (was 180s), Kepler read 180s, TESS LC `download_all` 300s, connect 10s.

---

## 5. Detection pipeline — the scientific core

**`astraeus/analysis/detection.py::detect_transit_candidate(time, flux, ..., snr_threshold=7.0)`** runs, in order:

```
1. DETREND
   DetrendingEngine.estimate_stellar_rotation(time, flux)  → rotation period days
   DetrendingEngine.detrend(...)                           → smooth flux baseline

2. BLS SEARCH
   BLSSearchEngine.search(active_time, active_flux)
   → {period, snr, depth, t0, duration, confidence_score, periodogram}
   ── emission gate (BOTH must pass) ──
       best_snr > snr_threshold   (default 7.0)
       best_confidence >= DETECTION_CONFIDENCE_FLOOR   (hardcoded safety floor;
                                                        defeats BLS false positives in pure noise)

3. GEOMETRIC VALIDATION
   GeometricValidator.validate(time, flux, period, t0, dur, depth)
   → impact parameter, duration consistency,
     secondary_eclipse_depth, secondary_eclipse_detected

4. VETTING (U-shape vs V-shape; bucket 9.1/10 work)
   VettingEngine.vet_transit_shape(...) + chi²-Δ U-vs-V
   → vetting_confidence, vetting_status
   result['v_shape_metric'] = 1.0 - vetting_confidence  (back-compat key)

5. PHYSICAL PROPERTIES (BEFORE cross-vetting, so secondary-eclipse branch
   can use physically-grounded threshold — bucket 2 fix)
   PhysicalPropertiesEngine.derive(period, depth, st_rad, st_teff, st_mass, jmag)
   → {planet_radius_earth, equilibrium_temp_k, semi_major_axis_au, ...}
   PhysicalPropertiesEngine.expected_occultation_depth_ppm(...)  # either a value
                                                                  # or None→fallback

6. FALSE-POSITIVE CROSS-VETTING (decision tree)
   fuses SNR + V-shape + secondary-eclipse + depth + ultra-short period
   → ONE OF:
     "Verified Planet Candidate"
     "Eclipsing Binary Detected"
     "V-Shaped False Positive Risk (Potential Grazing Binary)"
     "Verified Planet Candidate (Atmospheric Occultation Detected)"
     "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"

7. TTV ANALYSIS
   TTVAnalyzer.calculate(time, flux, period, t0, dur)
   → ttv_data (O-C residuals)
```

Result is also appended to `logs/experiments.json` via `save_experiment_log(...)` (UUID + SHA256 dataset hash).

---

## 6. Multi-planet orchestrator

**`astraeus/core/orchestrator.py::run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1)`**

Loops up to `max_signals` iterations. Each iteration:
1. Calls `detect_transit_candidate(...)` (above).
2. **Guardrail 1 — SNR/vetting break:** if `snr < snr_floor` OR `vetting_status` doesn't start with `"Verified Planet Candidate"`, halt.
3. **Guardrail 2 — duplicate/harmonic detection:** skip if new period within 5% of any previous OR a 0.5×/2× harmonic. Up to 3 retries; subtract anyway to erode residual.
4. **Subtract** the transit from `current_working_flux` via `subtract_planetary_signal(...)` — tries `batman` (high-precision) first, falls back to a Trapezoidal model with 10% ingress/egress ramps.
5. Loop.

Returns list of candidate dicts + prints consolidated JSON.

**Recent hard test evidence (`reports/bucket9.2_*`):** post-fix FP rate 0% on synthetic validation.

---

## 7. N-body solver (NEW in v0.0.2)

**`astraeus/core/nbody_solver.py`** — pure-numpy Symplectic Velocity Verlet (Störmer-Verlet / Leapfrog) integrator. No external astronomy packages.

Internal units: AU, M_sun, yr → G = 4π². Softening ε² = 1e-4 AU².

Public surface:
```
@dataclass PlanetParams(mass_msun, semi_major_axis_au, eccentricity, initial_phase_rad)
@dataclass StabilityResult(is_stable, survival_time_years, max_eccentricity_drift,
                           termination_reason ∈ {"completed","collision","ejection",
                                                 "energy_divergence","Physical Boundary Breach"},
                           colliding_pair, ejected_body, final_eccentricities,
                           energy_relative_error)

run_stability_analysis(stellar_mass_msun, planets, n_steps=50_000, dt_years=None)
    # from PlanetParams list; dt auto = min_period / 100 if None

run_stability_integration(positions, velocities, masses, n_steps=10_000, dt=0.01)
    # from raw state vectors

check_system_stability(stellar_mass_msun, planet_dicts)  # dict-based API; JSON-safe return

estimate_mass_from_radius(radius_earth)  # Weiss-Marcy 2014 power law; returns M_sun
```

Used by Simulator page (lazy import) and validated against Kepler-90 (`tests/test_nbody_solver.py`).

---

## 8. TTV analysis

Two modules:
- **`astraeus/analysis/ttv_analysis.py::TTVAnalyzer.calculate(time, flux, period, t0, dur)`** — invoked by detector step 7. Extracts O-C residuals.
- **`astraeus/analysis/ttv_nbody_validation.py`** — bucket 9.2 validation work (uses n-body solver to predict TTV amplitudes from masses/period ratios and cross-checks against extracted TTVs).

Periodic check: **`Lomb-Scargle`** period extraction on TTV series (commit `c465706`).
Analytical amplitude proxy filter (commit `902e211`).
Grid-search validation against N-body truth (commit `d8e181c`).

---

## 9. Simulation — synthetic + completeness sweep

**`astraeus/simulation/synthetic.py`** (mature)
- `SyntheticTransitScenario` dataclass (per-cell physical params).
- `generate_synthetic_transit_series(...)` — builds `LightCurveSeries` with controllable SNR/depth/duration.
- `run_injection_recovery(scenario, n_injections)` — runs `detect_transit_candidate` on injected signals, returns recovery stats. Exposes `recovered_depth` (bucket 3).

**`astraeus/simulation/completeness.py`** (new in v0.0.2; buckets 3)
- `CompletenessSweepConfig` (frozen dataclass; default period 0.5–30 d × 4, radius ratio 0.005–0.10 × 3, SNR {10,30,100}, 5 injections/cell, 90 d baseline × 4000 samples).
- `run_completeness_sweep(...)` — sweeps the grid, caches per-cell results on disk under `outputs/completeness_sweeps/<sha256(config)>/cell_<...>.json`.
- `CompletenessSweepResult` — `to_dict/save/load`. Atomic manifest writes (`.tmp` → `os.replace`).
- Phase 1 measurement: each cell takes ~5.7 s → default full sweep ~17 min.
- Validated vs. `run_injection_recovery` directly.

**Visualization:** `astraeus/visualization/plots.py::plot_completeness_map(...)` — heatmap + SNR-slope plot.

---

## 10. Vetting / physical / geometric engines

All in `astraeus/analysis/`. All `__init__`-ed as engines with static/classmethods:

| Engine | Module | Job |
|---|---|---|
| `DetrendingEngine` | `detrending.py` | Stellar rotation estimation + Savitzky-Golay detrend |
| `BLSSearchEngine` | `bls_search.py` | BLS periodogram + confidence_score |
| `GeometricValidator` | `geometric_validation.py` | Impact parameter, duration consistency, secondary-eclipse detection |
| `VettingEngine` | `vetting.py` | U-vs-V transit shape, chi²-Δ significance floor (bucket 10) |
| `PhysicalPropertiesEngine` | `physical_properties.py` | Radius/mass/equilibrium temp; **physically-derived secondary-eclipse threshold** (bucket 2) |
| `TTVAnalyzer` | `ttv_analysis.py` | O-C residual extraction |

Constants live in **`astraeus/core/constants.py`** (single source of truth for thresholds):
```
VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION
VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM   (800 ppm fallback when physical inputs missing)
VETTING_ULTRA_SHORT_PERIOD_DAYS
VETTING_VSHAPE_LOW_SNR_GATE
DETECTION_CONFIDENCE_FLOOR                (load-bearing noise-rejection gate)
DETECTION_SNR_THRESHOLD_DEFAULT            (= 5.0, bucket 9.1 reverted from 7)
```

---

## 11. LLM gateway

**`astraeus/core/llm_gateway.py`** — `LLMClient` is provider-agnostic. Providers in `config.json`:

| Provider | Default model | Requires |
|---|---|---|
| google | `gemini-1.5-pro-latest` | `GOOGLE_API_KEY` (or `api_keys.google` in config.json — empty in repo) |
| openai | `gpt-4o` | `OPENAI_API_KEY` |
| anthropic | `claude-3-opus-20240229` | `ANTHROPIC_API_KEY` |
| ollama | `llama3` | local Ollama daemon |

Used by:
- `astraeus/dashboard/ui/components.py::render_floating_chat` (UI chat popover, bottom-right of workbench).
- `astraeus/analysis/explanation.py` (natural-language result interpretation).

**Note:** No API keys committed; users must set keys in `config.json` or via env vars.

---

## 12. PDF manuscript export

**`astraeus/analysis/reporting.py::generate_academic_report(metrics_payload, figures=...)`** (called from `app.py` Discover tab → "Generate Research Manuscript" button).

Backend: `reportlab` (PDF generation). Figure embedding: `kaleido==0.2.1` (Plotly → PNG). If `kaleido` not installed, charts fall back to styled placeholder canvases and a warning is logged.

Output is returned as an in-memory BytesIO; `st.download_button` offers it.

Schema:
- `metrics_payload = {star_id, candidates: [{candidate_id, period, snr, depth, epoch}], introduction, optimization_summary}`
- `figures` keys follow `<star_id>-1<N>` convention.

---

## 13. Experiment tracking

**`astraeus/analysis/logging.py`**:
- `save_experiment_log(params, metadata, fig_paths) -> uuid` — appends entry to `logs/experiments.json`.
- `load_experiment_history() -> list[dict]` — read full ledger.
- `generate_dataset_hash(metadata) -> sha256` — reproducibility anchor.
- `ExperimentLedger` class — atomic-write variant (`.tmp` + `os.replace`).
- Each `detect_transit_candidate` call appends one entry; the History Streamlit tab loads the ledger.

---

## 14. The 6 dashboard tabs

| Tab | Where | What it does | Live imports |
|---|---|---|---|
| **Discover** (default) | inline in `app.py:192-292` | Pre-computed Kepler-90 candidates ledger + SNR slider + Generate Manuscript PDF button + per-candidate phase-folded synthetic plot. **Dual-Zone Grid: ACTIVE** is a UI placeholder, not a live toggle. | `astraeus.dashboard.ui.{layout,styles,components}`, `astraeus.analysis.reporting.generate_academic_report` |
| **Simulation** | `ui/pages/simulator.py` | Interactive orbital parameters (sliders for radius ratio, period, eccentricity, inclination, SNR). Live 3D orbit viewer + simulated light curve + residuals. | `astraeus.dashboard.figures`, `astraeus.core.transit_model`, `astraeus.dashboard.simulation`, `astraeus.data.preprocessing`, `astraeus.core.orbital_models`, (lazy) `astraeus.core.nbody_solver` |
| **Lab** | `ui/pages/lab.py` | Sensitivity exploration. | `astraeus.core.sensitivity_engine` |
| **Detective** | `ui/pages/detective.py` | Real-data discovery. Pulls via `RemoteDiscoveryEngine.fetch_data`, runs `run_multi_planet_search`. Dual-Zone Hybrid Grid BLS (1.5× wing padding). | `astraeus.analysis.detection.detect_transit_candidate`, `astraeus.core.orchestrator.run_multi_planet_search`, `astraeus.core.ingestion.{RemoteDiscoveryEngine, DataAdapter}`, (lazy) `astraeus.core.nbody_solver` |
| **History** | `ui/pages/history.py` | Loads `logs/experiments.json`. | `astraeus.analysis.logging.load_experiment_history` |
| **Settings** | `ui/pages/settings.py` | LLM provider / API key form. | `astraeus.dashboard.ui.settings.render_settings_panel` |

---

## 15. CLI / scripted workflows

**`python astraeus/main.py`** — runs `RealDataPipeline(target_name="TrES-2b", mission="Kepler", quarter=1)` end-to-end. Pipeline code at `astraeus/workflows/pipeline.py`.

**QA scripts (live, under `scripts/`):**
- `qa_runner.py`, `qa_runner_v2.py` — point at `qa_targets.yaml`. v2 = cached/dynamic dual-mode (8 cached + 5 dynamic targets). Markdown reporter (`v2_harness`).
- v2 phases: A = backend pre-flight (cache-or-network); B = UI flow with 3 snapshots per target.

**Manual tests (`scripts/manual_tests/`):** awaiting pytest conversion. Most have already been pulled into `tests/test_*.py`; originals moved to `deprecated/` as they're upgraded.

---

## 16. Test suite

`tests/` — **35 pytest files** (`pytest -q`):
- Discovery / unit: `test_adapter.py`, `test_orbital_models.py`, `test_physics.py`, `test_transit_model.py`, `test_preprocessing.py`, `test_synthetic_simulation.py`, `test_loader.py`.
- Detection / vetting: `test_mcmc.py`, `test_bulletproof_detector.py`, `test_dashboard_simulation.py`, `test_vetting_threshold_hardening.py`, `test_ttv_nbody_validation.py`, `test_completeness_sweep.py`.
- Network: `test_nasa_archive_network.py`, `test_debug_metadata_network.py`.
- Stress / diagnostic (parametrized): `test_pipeline_stress_test.py`, `test_global_matrix_stress_test.py`, `test_solid_matrix_diagnostic.py`, `test_system_flight_bench.py` (`@smoke` + `@slow`).
- UI: `test_ui_flow.py`, `test_workbench_navigation.py` (`file_uploader` mock consolidated in conftest fixture).
- Real data: `test_multi_planet_search_real_data.py` (Kepler-90b scenario).
- N-body: `test_nbody_solver.py` (Kepler-90b six-planet system, includes merged Kepler-90b scenarios from `test_engine.py`).
- Multi-planet: `test_multi_planet_scaling.py`, `test_agent_detective.py`, `test_chaos_integration_suite.py`, `test_lab_realtime.py`, `test_experiment_history.py`, `test_pipeline_smoke.py`, `test_adapter.py`.

**Markers** (`pytest.ini`): `@smoke` (fast, CI gating), `@slow` (excluded by default).

**`tests/conftest.py`** resets Streamlit `DeltaGeneratorSingleton` between tests. `tests/_fixtures/fakes.py` shared test doubles.

**Baseline** (bucket 9.1 post-fix): 81 passed, 1 skipped, 33 deselected, exit 0. Bucket 9.2 same envelope. Bucket 3 baseline (earlier): 85 passed.

---

## 17. CI / GitHub Actions

`.github/workflows/` (bucket 5): **fast-gate** job runs `@smoke`-marked tests + a sample of full suite; **non-blocking full-suite** runs the rest. Posttest output is saved to `docs/ci/bucket5_*`.

---

## 18. Dev infrastructure

- **`.windsurfrules` & `AGENTS.md`** — mandate CodeGenome MCP usage: prefer `search_nodes`, `get_neighbors`, `get_changes` over `grep`. Cache at `.genome/watcher.db`.
- **`.genome/`** — CodeGenome graph cache (live). If MCP transport is up, query via `http://127.0.0.1:7331/mcp` (stdio or HTTP) before falling back to direct file reads.
- **`dev-knowledge-base/`** — Research notes (architecture briefs, experiment rationale).
- **`docs/superpowers/`** — 3 design+plan doc pairs:
  - `2026-06-23-completeness-sweep` (designed + implemented)
  - `2026-06-27-qa-v2-dual-mode` (designed + implemented)
  - `2026-06-30-data-ingestion-solid-refactor` (designed; **Phase 0 seams landed in 5e68b19**, full refactor not yet implemented)
- **`scripts/qa_targets.yaml`** — manifest of 8 cached + 5 dynamic targets used by v2 harness.
- **`tests/reports/`** — solid_audit_log.json, ai_audit_payload.json, run logs.

---

## 19. What is WORKING right now (verified in this branch)

✅ Streamlit app launches (`streamlit run app.py` from project root).
✅ Dashboard renders 3-panel workbench with 6-tab sidebar navigation.
✅ Discover tab renders the precomputed Kepler-90 baseline payload, per-candidate phase-folded synthetic plots, SNR slider, Manuscript button → PDF download.
✅ Floating AI chat popover renders (no live LLM unless keys set).
✅ Remote data fetch works **with cache-first fallback**: in offline / MAST-down scenarios, TESS or Kepler LCs are assembled from local FITS cache (no network).
✅ TESS multi-sector SPOC stitch handles mixed-cadence sectors, per-sector normalization kills baseline cliffs, corrupt sectors evicted.
✅ Kepler streaming falls back to unsigned S3 stpubdata when MAST HTTPS hangs.
✅ `detect_transit_candidate` runs the 7-stage pipeline and applies dual-gate (SNR + confidence floor) so pure-noise BLS false positives are rejected.
✅ Vetting decision tree (U/V shape + secondary-eclipse + depth) labels correctly across all 5 buckets (Verified, Binary, V-shaped, Atmospheric Occultation, Binary at Phase 0.5).
✅ Multi-planet orchestrator finds Kepler-90b-like systems in real data, with anti-duplicate/harmonic guardrail.
✅ N-body solver (Velocity Verlet) runs Kepler-90b six-planet scenario stably (verified in `test_nbody_solver.py`).
✅ TTV analysis + Lomb-Scargle periodicity extraction + analytical amplitude proxy filter all wired.
✅ Completeness sweep runs and caches 18 cells in ~17 min (bucket 3 verified).
✅ PDF manuscript compiles via reportlab + kaleido (with graceful placeholder fallback).
✅ Experiment history ledger writes `logs/experiments.json` atomically; History tab reads it.
✅ `python astraeus/main.py` runs TrES-2b Kepler Q1 end-to-end via `RealDataPipeline`.
✅ 81 pytest baseline passes (`@smoke` + main suite; some `@slow` and `@network` deselected).

---

## 20. What is PARTIAL / placeholder / known rough edges

⚠️ **Discover tab is hard-coded to a Kepler-90 baseline payload** (`BASELINE_PAYLOAD` in `app.py:26-35`). It does NOT actually invoke the discovery pipeline — it just renders 4 pre-computed candidates (266.9 d, 211.7 d, 238.6 d, 663.1 d). The real discovery happens in the **Detective** tab.

⚠️ **`"Dual-Zone Grid: ACTIVE"`** and **`"1.5x Wing Subtraction: ACTIVE"`** are static UI labels in the Discover sidebar (`app.py:216-217`). The actual Dual-Zone logic lives only in the Detective page's pipeline.

⚠️ **Decorative phase-folded figures** in `app.py` (`_build_phase_folded_figure`) are **synthesized from the candidate's own depth/duration/t0** — they read the candidate dict and render a deterministic box-window dip + Gaussian noise. They are NOT derived from real photometry.

⚠️ **`astraeus/dashboard/services/`** (`action_deck.py`, `data_ingestion.py`, `mcmc_retrieval.py`) is **dead/orphaned**: only imported by the deprecated UI panels and deprecated `data/discovery.py`. Not touched in Bucket 1. Logging file `err.log` / `err2.log` at the root contains traces of these.

⚠️ **Solid/SRP refactor** is **designed but only Phase 0 (seams) landed**. The plan at `docs/superpowers/plans/2026-06-30-data-ingestion-solid-refactor.md` is untracked; ready to implement. Adds `HttpClientPort`, `FsPort`, `ClockPort`, `LightkurveRowPort` protocols and a `MastStreamerPort` collaborator.

⚠️ **README/PRD are partially stale.** They don't mention: TTV analysis, N-body solver, multi-planet orchestrator, vetting engine, physical properties engine, completeness sweep, experiment ledger, or that there is one ingestion engine with two entry points. The **authoritative doc is `docs/ARCHITECTURE.md`**.

⚠️ **`prd_v2.md`** (newer PRD, "Version 2.0") is **aspirational portfolio vision** — Next.js + TypeScript + Three.js frontend, FastAPI backend, PostgreSQL, Qdrant, LangGraph/LangChain, etc. **None of this is built.** The actual codebase is the Streamlit/Python stack described above.

⚠️ **`astraeus/analysis/detection.py:165` fallback** — when SNR high but vetting ambiguous and no secondary eclipse: falls to `VettingEngine` `Likely Planet` → "Verified Planet Candidate". Loose.

⚠️ **TTV analysis on multi-planet systems** (Detective Keplerian pipeline) only extracts O-C from single BLS winner; doesn't yet propagate the multi-planet subtraction residuals into per-planet TTV curves.

⚠️ **`documents/fastapi/portfolio`** are not implemented. All MCMC UI infrastructure (`mcmc_panel.py`, `mcmc_form.py`) was deprecated — only MCMC test (`test_mcmc.py`) remains.

⚠️ **`scripts/manual_tests/`** are flagged for pytest conversion. `deprecated/` already contains moved originals.

⚠️ **`boto3>=1.28.0`** is a runtime dep (`requirements.txt`) used only for the S3 fallback in LightkurveClient — costs ~80 MB of install weight for a rarely-triggered path.

⚠️ **Testing of UI tabs is structural** (workbench navigation, file_uploader mock) — NOT visual regression. `err.log` / `pytest_out.txt` / `qa_results.json` carry recent run traces.

---

## 21. Deprecated DO-NOT-IMPORT paths

Anything matching these is dead, was moved in Bucket 1, and is excluded by `pytest.ini`:

- `astraeus.ui.*` → `deprecated/astraeus_ui_dashboard/` (older copy of `app.py`; only importer was a non-pytest chaos script).
- `astraeus.dashboard.ui.{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py` → `deprecated/astraeus_dashboard_ui/` (self-referential dead cluster).
- `astraeus.data.discovery` → `deprecated/astraeus_data_discovery/` (second `RemoteDiscoveryEngine`).

> **Heuristic for new code:** if you want a streamlit component, look in `astraeus/dashboard/ui/` (layout, styles, components, settings). If you want an ingestion façade, use `astraeus.core.ingestion.RemoteDiscoveryEngine`. If you want a page implementation, look in `ui/pages/`.

---

## 22. Conventions & quirks worth knowing

- **All numeric light-curve arrays are `np.float64`** — explicit `dtype=np.float64` guards throughout `LightkurveClient`. Sub-400 ppm transit signals cannot survive float32.
- **Vetting thresholds live in `astraeus/core/constants.py`** — not inlined as magic numbers. Many bucket refactors (2, 9.1, 9.2, 10) replaced inline constants with named ones.
- **Cache directories:** `~/.lightkurve/cache` (lightkurve's default), `os.environ.get("ASTRAEUS_LIGHTKURVE_CACHE_DIR", "<tmp>/astraeus_lightkurve_cache")` (astraeus's). Both writable under `tests/conftest.py`.
- **`logs/experiments.json` is the experiment ledger** — every `detect_transit_candidate` call appends an entry. Atomic writes via `.tmp` + `os.replace` (in `ExperimentLedger`). Suppressed during pytest via conftest isolation (bucket 9.2).
- **Reporting wants specific keys:** `<star_id>-1<N>` for figure dicts (e.g. `KIC 11442793-11`). Generated figures are deterministic per candidate via a seeded `np.random.default_rng`.
- **`pytest.ini`** excludes `deprecated/` and registers `@smoke` / `@slow` markers.
- **`ASTRAEUS_FORCE_NETWORK=1`** env var bypasses the Lightkurve cache lookup — used by QA harness to exercise the dynamic MAST/S3 path.
- **Branch hygiene:** active branch is `v.0.0.2`. Three merge commits locked the bucket 8/9/9.2 work into this branch. No tags exist yet.
- **Commit convention:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`, `merge:`) with a scope tag (`(ingest)`, `(qa)`, `(analysis)`, `(batching)`, `(ci)`, …).

---

## 23. Known breakage points to ask about / verify

The user has reported casualties. Most likely problem zones, ranked by frequency:

1. **LLM chat not responding** — `config.json` `api_keys` are empty; provider reports OK but calls fail silently. Must set keys in config or via env vars.
2. **MAST search hangs / timeouts** — lightkurve's default 180 s read timeout can't serve TESS FFIs. v0.0.2 already raised this to 600 s (`_TESS_READ_TIMEOUT`). If you see truncated FITS or `Empty data_uri` warnings, check the cache dir.
3. **PDF manuscript figures render as placeholders** — missing `kaleido==0.2.1` (or version mismatch with installed `plotly` 5.24). `app.py` logs a warning on startup (`_check_headless_prerequisites`).
4. **Discover tab "shows zero candidates"** — only if `BASELINE_PAYLOAD` is mutated in session_state. Reset clears it back to the 4-planet Kepler-90 baseline.
5. **Multi-planet orchestrator infinite-loops on duplicate** — bounded by `max_duplicate_retries=3` and `iteration > max_signals + max_duplicate_retries`. If it still loops, suspect `batman` import failure (silent fallback to Trapezoidal is correct; log line `[Fallback] batman failed or unavailable` is expected).
6. **`err.log` / `err2.log` at project root** — historical stderr traces from LightkurveClient (S3 fallback, cache eviction, FITS corruption). These are NOT errors; they're the engine's "I'm being careful" chatter.
7. **pytest deselects 33 tests** — those are `@slow` or `@network` markers. Run with `pytest -m ""` to include.

---

## 24. What the doc does NOT cover but downstream Q&A should probe

- Internal shape of `BLS periodogram`, `BLSSearchEngine.confidence_score` (compute details — bucket 9.1 audit report has the empirical justification).
- Exact definitions of all geometric-validation outputs (read `geometric_validation.py`).
- `PhysicalPropertiesEngine.expected_occultation_depth_ppm` formula (physically derived; see bucket 2 audit `docs/bucket2_*`).
- `MAP estimation` (`analysis/optimization.py::find_best_fit`) — wired into the older pipeline; not currently on a live dashboard path.
- `error_analysis.py` (`emcee`-based MCMC) — implemented and unit-tested (`test_mcmc.py`); not wired into a current dashboard control surface.
- `reports/` and `runs/` directories — generated artifacts, gitignored. Reachable only if you ran sweeps/QA recently.

---

## 25. Question-answering guidance for a downstream model

This doc is structured so that the following kinds of questions map cleanly to sections:

| If the user asks… | Read… |
|---|---|
| "How do I run the app?" | §3, §14 |
| "How does data ingestion work?" | §4 |
| "How does transit detection work?" | §5 |
| "Multi-planet?" | §6, §8 |
| "N-body / TTV?" | §7, §8 |
| "Simulation / completeness sweep?" | §9 |
| "Where is the LLM integration?" | §11 |
| "How do I generate a PDF report?" | §12, §14 (Discover tab) |
| "Where are experiments logged?" | §13 |
| "What's working / broken?" | §19, §20, §23 |
| "What NOT to import / touch?" | §21 |
| "How is the test suite organized?" | §16, §17 |
| "Why doesn't the doc/README match the code?" | §20 (⚠️ staleness list) |
| "What's in `prd_v2.md` — is it real?" | §20 (no — aspirational) |
| "How do I add a new analysis engine?" | §10 conventions + §18 dev infra |

End of v0.0.2 briefing.
