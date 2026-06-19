# Astraeus — Module & Function Reference

> **Purpose:** Comprehensive reference document for every module, class, function, and workflow in the Astraeus codebase. Use this to understand what each component does and how to test it independently.

> **Last updated:** 2026-06-19 | **Branch:** v.0.0.2

---

## Table of Contents

- [1. `astraeus/core/` — Physics Engine & Infrastructure](#1-astraeuscore--physics-engine--infrastructure)
  - [1.1 `config.py`](#11-configpy)
  - [1.2 `constants.py`](#12-constantspy)
  - [1.3 `validation.py`](#13-validationpy)
  - [1.4 `geometry.py`](#14-geometrypy)
  - [1.5 `kepler.py`](#15-keplerpy)
  - [1.6 `orbits.py`](#16-orbitspy)
  - [1.7 `orbital_models.py`](#17-orbital_modelspy)
  - [1.8 `transit_model.py`](#18-transit_modelpy)
  - [1.9 `nbody_solver.py`](#19-nbody_solverpy)
  - [1.10 `nasa_archive.py`](#110-nasa_archivepy)
  - [1.11 `lightkurve_client.py`](#111-lightkurve_clientpy)
  - [1.12 `ingestion.py`](#112-ingestionpy)
  - [1.13 `orchestrator.py`](#113-orchestratorpy)
  - [1.14 `sensitivity_engine.py`](#114-sensitivity_enginepy)
  - [1.15 `llm_gateway.py`](#115-llm_gatewaypy)
- [2. `astraeus/analysis/` — Signal Processing & Detection](#2-astraeusanalysis--signal-processing--detection)
  - [2.1 `detrending.py`](#21-detrendingpy)
  - [2.2 `bls_search.py`](#22-bls_searchpy)
  - [2.3 `detection.py`](#23-detectionpy)
  - [2.4 `geometric_validation.py`](#24-geometric_validationpy)
  - [2.5 `physical_properties.py`](#25-physical_propertiespy)
  - [2.6 `ttv_analysis.py`](#26-ttv_analysispy)
  - [2.7 `fitting.py`](#27-fittingpy)
  - [2.8 `optimization.py`](#28-optimizationpy)
  - [2.9 `error_analysis.py`](#29-error_analysispy)
  - [2.10 `explanation.py`](#210-explanationpy)
  - [2.11 `logging.py`](#211-loggingpy)
  - [2.12 `reporting.py`](#212-reportingpy)
- [3. `astraeus/data/` — Data Handling & Ingestion](#3-astraeusdata--data-handling--ingestion)
  - [3.1 `adapter.py`](#31-adapterpy)
  - [3.2 `discovery.py`](#32-discoverypy)
  - [3.3 `loader.py`](#33-loaderpy)
  - [3.4 `preprocessing.py`](#34-preprocessingpy)
- [4. `astraeus/simulation/` — Synthetic Data Generation](#4-astraeussimulation--synthetic-data-generation)
  - [4.1 `synthetic.py`](#41-syntheticpy)
- [5. `astraeus/visualization/` — Plotting Utilities](#5-astraeusvisualization--plotting-utilities)
  - [5.1 `plots.py`](#51-plotspy)
- [6. `astraeus/workflows/` — Pipeline Orchestration](#6-astraeusworkflows--pipeline-orchestration)
  - [6.1 `pipeline.py`](#61-pipelinepy)
- [7. `astraeus/ui/` — Streamlit UI Pages](#7-astraeusui--streamlit-ui-pages)
  - [7.1 `dashboard.py`](#71-dashboardpy)
  - [7.2 `ui/pages/detective.py`](#72-uipagesdetectivepy)
  - [7.3 `ui/pages/lab.py`](#73-uipageslabpy)
  - [7.4 `ui/pages/history.py`](#74-uipageshistorypy)
  - [7.5 `ui/pages/settings.py`](#75-uipagessettingspy)
  - [7.6 `ui/pages/simulator.py`](#76-uipagessimulatorpy)
- [8. `astraeus/dashboard/` — Streamlit Dashboard (Legacy)](#8-astraeusdashboard--streamlit-dashboard-legacy)
  - [8.1 Key Dashboard Modules](#81-key-dashboard-modules)
- [9. Top-Level Scripts](#9-top-level-scripts)
  - [9.1 `app.py`](#91-apppy)
  - [9.2 `route.py`](#92-routepy)
  - [9.3 `runs/kepler90_blind_search.py`](#93-runskepler90_blind_searchpy)
  - [9.4 `find_cycles.py`](#94-find_cyclespy)
  - [9.5 `init_project.py`](#95-init_projectpy)
  - [9.6 `extract.py`](#96-extractpy)
  - [9.7 `test_engine.py` / `test_orchestrator.py` / `test_ingest.py`](#97-test-scripts)
- [10. `tests/` — Test Suite Overview](#10-tests--test-suite-overview)
- [11. Quick Test Commands](#11-quick-test-commands)

---

## 1. `astraeus/core/` — Physics Engine & Infrastructure

The core layer implements the fundamental physics, orbital mechanics, transit modeling, data fetching from NASA archives, and multi-planet orchestration.

### 1.1 `config.py`

**Purpose:** Loads and validates the JSON configuration file (`config.json`) that stores API keys and model settings.

| Function | Signature | Description |
|---|---|---|
| `load_config` | `(filepath: str = "config.json") -> Dict[str, Any]` | Reads `config.json`; returns `{}` if file missing or parse error. |
| `validate_config` | `(config: Dict[str, Any]) -> None` | Checks for required keys: `llm_provider`, `llm_model`, `api_keys`. Logs warning if missing. |

**Test approach:** Pass a valid JSON file path; verify keys are extracted. Pass a missing path; verify empty dict returned.

---

### 1.2 `constants.py`

**Purpose:** Defines shared physical constants and numerical limits used across the physics models.

| Constant | Value | Description |
|---|---|---|
| `BOUND_ECCENTRICITY_MINIMUM` | `0.0` | Lower bound for elliptical eccentricity |
| `BOUND_ECCENTRICITY_MAXIMUM` | `1.0` | Upper bound (exclusive) for elliptical orbits |
| `HIGH_ECCENTRICITY_INITIAL_GUESS_THRESHOLD` | `0.8` | Eccentricity above which the Kepler solver adjusts its initial guess |
| `KEPLER_NEWTON_TOLERANCE` | `1e-12` | Convergence tolerance for Newton-Raphson |
| `KEPLER_NEWTON_MAX_ITERATIONS` | `64` | Max iterations for Kepler solver |
| `HALF_TURN_ANGLE` | `π rad` | Half a full orbital turn |
| `FULL_TURN_ANGLE` | `2π rad` | Complete orbital revolution |
| `REFERENCE_LENGTH_UNIT` | `AU` | Standard length unit |

**Test approach:** Import and verify expected values; constants are read-only.

---

### 1.3 `validation.py`

**Purpose:** Provides reusable validation helpers that enforce type, unit, and physical constraints on Astropy `Quantity` objects.

| Function | Signature | Description |
|---|---|---|
| `require_quantity` | `(value, parameter_name) -> u.Quantity` | Raises `TypeError` if value is not an `astropy.units.Quantity`. |
| `require_convertible_unit` | `(value, expected_unit, parameter_name) -> u.Quantity` | Ensures the quantity can be converted to the expected unit family. |
| `require_positive_quantity` | `(value, parameter_name) -> u.Quantity` | Rejects zero or negative values (e.g., period, semi-major axis). |
| `require_non_negative_quantity` | `(value, parameter_name) -> u.Quantity` | Rejects negative values but allows zero (e.g., projected separation). |
| `require_bound_eccentricity` | `(eccentricity) -> u.Quantity` | Enforces `0 ≤ e < 1`. |

**Test approach:** Pass valid quantities; pass invalid ones (e.g., negative period, `e >= 1`); confirm exceptions.

---

### 1.4 `geometry.py`

**Purpose:** Projected-sky-plane geometric calculations — sky separation and circle overlap area — used by transit models.

| Function | Signature | Description |
|---|---|---|
| `calculate_sky_separation` | `(x, y, z) -> u.Quantity` | Returns `√(x² + y²)` — the projected star-planet center separation on the sky. Validates all inputs are convertible length quantities. |
| `calculate_circle_overlap_area` | `(separation, first_radius, second_radius) -> u.Quantity` | Computes the projected overlap area between two circular disks (star + planet). Handles three regimes: disjoint, contained, and intersecting (lens-area formula). |
| `_calculate_intersecting_circle_area` | `(separation, first_radius, second_radius) -> np.ndarray` | Internal: lens-area calculation for partially intersecting circles. |

**Test approach:** Verify disjoint circles return zero overlap. Verify concentric circles return π·min(R)². Verify unit validation raises on mismatched units.

---

### 1.5 `kepler.py`

**Purpose:** Solves Kepler's equation `M = E - e sin(E)` for eccentric anomaly `E`.

| Symbol / Class | Description |
|---|---|
| `KeplerEquationSolver` | Protocol defining the `solve()` interface — enables future solver backends. |
| `NewtonRaphsonKeplerSolver` | Frozen dataclass implementing Newton-Raphson iteration with adaptive initial guess (threshold at `e >= 0.8`). Configurable tolerance and max iterations. |
| `solve_kepler_equation` | `(mean_anomaly, eccentricity, solver=None) -> u.Quantity` | Public functional entry point. Delegates to the configured solver. Default is `NewtonRaphsonKeplerSolver`. |
| `solve_keplers_equation` | Alias for `solve_kepler_equation`. |

**Key methods of `NewtonRaphsonKeplerSolver`:**
- `solve(mean_anomaly, eccentricity) -> u.Quantity` — Returns eccentric anomaly in radians. Raises `RuntimeError` on non-convergence.
- `_normalize_mean_anomaly(mean_anomaly)` — Reduces phase to `[0, 2π)`.
- `_initial_guess(normalized_mean_anomaly, eccentricity_value)` — Uses `M ± e` for high eccentricity, `M` otherwise.

**Test approach:** Known-answer test: `M=π, e=0` → `E=π`. Edge cases: `e=0.99`, `e=0.0`. Verify tolerance is met.

---

### 1.6 `orbits.py`

**Purpose:** Keplerian orbit domain objects and coordinate transforms (Keplerian → Cartesian).

| Symbol | Description |
|---|---|
| `CartesianPosition` | Type alias: `tuple[u.Quantity, u.Quantity, u.Quantity]` for `(x, y, z)`. |
| `PlanarPosition` | Type alias: `tuple[u.Quantity, u.Quantity]` for `(x', y')`. |
| `KeplerianOrbit` | Frozen dataclass with `period`, `semi_major_axis`, `eccentricity`, `inclination`, and an injectable `solver`. |

| Function | Signature | Description |
|---|---|---|
| `calculate_mean_anomaly` | `(time, period) -> u.Quantity` | `M = (2π/P) × t`. Returns angle in radians. |
| `calculate_orbital_plane_position` | `(eccentric_anomaly, semi_major_axis, eccentricity) -> PlanarPosition` | `x' = a(cos(E) - e)`, `y' = a·√(1-e²)·sin(E)`. |
| `rotate_orbital_plane_by_inclination` | `(orbital_x, orbital_y, inclination) -> CartesianPosition` | Rotation about x-axis: `x` unchanged, `y = y'cos(i)`, `z = y'sin(i)`. |

**Key method of `KeplerianOrbit`:**
- `position_at(time) -> CartesianPosition` — Full pipeline: `time → M → E → (x', y') → (x, y, z)`.

**Test approach:** Verify circular orbit returns correct positions. Verify inclination rotation. Validate that `time=0` gives periapsis at positive x.

---

### 1.7 `orbital_models.py`

**Purpose:** Public facade module that re-exports core orbital symbols and provides `calculate_orbital_position`.

| Function | Signature | Description |
|---|---|---|
| `calculate_orbital_position` | `(time, period, semi_major_axis, eccentricity, inclination) -> CartesianPosition` | Convenience function that constructs a `KeplerianOrbit` and returns its position. |

**Re-exports:** `KeplerianOrbit`, `NewtonRaphsonKeplerSolver`, `solve_kepler_equation`.

**Test approach:** Same as `orbits.py` — verify round-trip consistency.

---

### 1.8 `transit_model.py`

**Purpose:** Generates analytical geometric transit light curves with quadratic limb darkening.

| Function | Signature | Description |
|---|---|---|
| `generate_geometric_transit` | `(separation, R_star, R_planet, u1=0, u2=0) -> u.Quantity` | Computes relative flux drop using numerical integration of limb-darkened stellar rings intersected by the planet disk. Uses `scipy.integrate.quad_vec`. Returns a dimensionless quantity. |
| `generate_model_flux` | `(time, period, semi_major_axis, eccentricity, inclination, R_star, R_planet, u1, u2) -> np.ndarray` | End-to-end: computes orbital position → sky separation → geometric transit. Sets flux drop to 0 when planet is behind star (`z < 0`). |
| `generate_multi_planet_transit` | `(time, planet_list) -> np.ndarray` | Multiplies individual planet fluxes for a multi-planet system. `planet_list` is a list of parameter dicts. |

**Test approach:** Verify out-of-transit flux = 1.0. Verify full-transit dip magnitude matches `√(depth)`. Test multi-planet multiplies correctly. Verify limb darkening reduces total depth.

---

### 1.9 `nbody_solver.py`

**Purpose:** N-body gravitational stability solver using a Symplectic Velocity Verlet integrator. Pure numpy — no external astronomy packages. Internal units: AU, M_sun, years (G = 4π²).

| Data Class | Fields | Description |
|---|---|---|
| `PlanetParams` | `mass_msun`, `semi_major_axis_au`, `eccentricity`, `initial_phase_rad` | Orbital parameters for one planet. |
| `StabilityResult` | `is_stable`, `survival_time_years`, `max_eccentricity_drift`, `termination_reason`, `colliding_pair`, `ejected_body`, `final_eccentricities`, `energy_relative_error` | Diagnostic payload from the solver. |

| Function | Signature | Description |
|---|---|---|
| `run_stability_analysis` | `(stellar_mass_msun, planets, n_steps=50000, dt_years=None) -> StabilityResult` | Full analysis from Keplerian elements. Auto-computes timestep as `min_period / 100`. Monitors collisions (Hill radii), ejections (e ≥ 1), energy divergence, velocity sanity. |
| `run_stability_integration` | `(positions, velocities, masses, n_steps, dt) -> StabilityResult` | Runs from raw Cartesian state vectors. Used by the UI for interactive N-body. |
| `check_system_stability` | `(stellar_mass_msun, planet_dicts, ...) -> dict` | Dict-based API wrapper for the frontend. Accepts JSON-friendly input, returns JSON-serializable dict. |
| `estimate_mass_from_radius` | `(radius_earth) -> float` | Weiss-Marcy 2014 mass-radius: `M ≈ R^2.06` for R < 4 R⊕, cubic scaling for gas giants. Returns mass in M_sun. |

**Internal helpers:**
- `_keplerian_to_cartesian(star_mass, planet)` — Keplerian elements → (pos, vel).
- `_hill_radius(m_planet, m_star, semi_major_axis)` — `R_H = a·(m_p/3M★)^(1/3)`.
- `_compute_accelerations(positions, masses)` — Pairwise gravity with softening.
- `_compute_osculating_eccentricity(pos, vel, mu)` — Instantaneous eccentricity from state vectors.
- `_compute_total_energy(positions, velocities, masses)` — E = KE + PE.

**Test approach:** Test 2-planet stable system (e.g., inner hot Jupiter + outer planet). Test unstable (close orbits). Verify energy conservation. Test `estimate_mass_from_radius` known values (Earth, Jupiter).

---

### 1.10 `nasa_archive.py`

**Purpose:** Interfaces with the NASA Exoplanet Archive TAP API to fetch stellar/planetary metadata.

| Class | Method | Description |
|---|---|---|
| `NASAExoplanetArchive` | `normalize_target_name(raw)` | Canonicalizes exoplanet names (e.g., `kepler 90 b` → `Kepler-90 b`). Handles WASP, HAT-P, K2, TOI, TrES, etc. |
| | `sanitize_meta(meta)` | Fills NaN/masked values with sensible defaults for `orbital_period`, `stellar_radius`, `st_teff`, etc. |
| | `_fetch_ps_orbital_period(safe_canonical)` | Fallback query to the `ps` table for orbital period if `pscomppars` fails. |
| | `_metadata_name_candidates(canonical_name)` | Generates alias list for fuzzy matching (e.g., `Kepler-13 b` → also tries `KOI-13 b`). |
| | `fetch_metadata(canonical_name) -> (dict, str\|None)` | Main entry point: queries `pscomppars` table, extracts `pl_orbper`, `st_rad`, `pl_trandep`, `st_teff`, `st_mass`, etc. Handles transit depth normalization (percent → fraction). Returns metadata dict + optional error string. |

**Test approach:** Mock HTTP responses. Test `normalize_target_name` with various formats. Verify `sanitize_meta` fills NaN values. Test `fetch_metadata` error handling.

---

### 1.11 `lightkurve_client.py`

**Purpose:** Downloads photometric time-series data from MAST via the `lightkurve` package with timeout protection and corruption recovery.

| Class | Method | Description |
|---|---|---|
| `LightkurveClient` | `_wipe_lightkurve_cache()` | Deletes the default lightkurve cache directory. |
| | `_wipe_download_dir(download_dir)` | Removes and recreates a specific download directory. |
| | `_download_cache_dir() -> str` | Returns (and creates) the Astraeus-specific cache directory. |
| | `_call_with_timeout(fn, args, kwargs, timeout, label)` | Runs any callable in a thread with a timeout. Returns `None` on timeout. |
| | `_download_with_timeout(row, timeout, download_dir)` | Downloads a single lightkurve search result row with timeout. |
| | `_is_fits_corruption(exc) -> bool` | Detects FITS file corruption by checking error message keywords. |
| | `_prioritize_search_results(search, mission_type)` | For Kepler: prefers long-cadence. Sorts by file size (smallest first). |
| | `download_pipeline(t_name, mission_type) -> (dict\|None, str\|None)` | Main download pipeline: searches → prioritizes → downloads → stitches → normalizes → removes NaNs. Handles TESS and Kepler. Returns `{time, flux, flux_err}` dict or error. |
| | `download_combined_fusion(safe_canonical) -> (dict\|None, str\|None)` | Downloads both TESS and Kepler data and concatenates into a unified time baseline. |

**Test approach:** Requires network access or mocked `lightkurve`. Test timeout handling. Test corruption detection. Verify output array shapes and NaN removal.

---

### 1.12 `ingestion.py`

**Purpose:** Facade that coordinates `NASAExoplanetArchive` and `LightkurveClient` for unified remote data discovery. Streamlit-cached.

| Class / Function | Description |
|---|---|
| `RemoteDiscoveryEngine` | Static class coordinating archive metadata + MAST time-series download. |
| `RemoteDiscoveryEngine._fetch_data_impl(target_name, mission)` | Dispatches to NASA archive for metadata, then LightkurveClient for time-series based on mission type (`TESS`, `Kepler`, `Combined Baseline`). |
| `RemoteDiscoveryEngine.fetch_data(target_name, mission)` | Streamlit `@st.cache_data`-wrapped version of `_fetch_data_impl`. |
| `_cached_fetch_data(target_name, mission)` | Internal Streamlit-cached fetch helper. |

**Returns:** Dict with keys `status`, `metadata`, `time`, `flux`, `flux_err`, `archive_error`, `mast_error`.

**Test approach:** Mock both archive and Lightkurve responses. Verify correct dispatch for different mission types.

---

### 1.13 `orchestrator.py`

**Purpose:** Multi-planet iterative search engine. Repeatedly runs detection → subtraction → re-detection to find up to `max_signals` planets.

| Function | Signature | Description |
|---|---|---|
| `subtract_planetary_signal` | `(flux, time, period, epoch, duration, depth_ppm, metadata) -> np.ndarray` | Removes a transit signal from flux. Tries `batman` package first; falls back to a trapezoidal model. Applies 25% window padding. |
| `run_multi_planet_search` | `(raw_lightcurve, max_signals=5, snr_floor=7.1) -> list` | Iterative search loop. For each iteration: runs `detect_transit_candidate`, checks SNR/vetting, deduplicates (within 5% or half/double harmonics), subtracts accepted signals. Returns list of candidate dicts. |

**Guardrails:**
1. SNR/Vetting break — stops when signal falls below threshold.
2. Duplicate detection — skips period within 5% or harmonics.
3. Iteration budget — stops after `max_signals + 3` duplicates.

**Test approach:** Use synthetic multi-planet light curves. Verify correct number of detected planets. Verify signal subtraction does not destroy subsequent detections.

---

### 1.14 `sensitivity_engine.py`

**Purpose:** High-speed vectorized transit model for interactive UI sliders. Avoids astropy units for performance.

| Function | Signature | Description |
|---|---|---|
| `get_model_curve` | `(params, time_array) -> np.ndarray` | Generates uniform-disk transit model. Params: `period`, `t0`, `rp_rs`, `a_rs`, `inc`. Returns flux array (1.0 = out-of-transit). Circular orbit assumption for speed. |

**Test approach:** Pass known parameters; verify out-of-transit flux = 1.0, transit depth matches `(R_p/R★)²`. Performance benchmark.

---

### 1.15 `llm_gateway.py`

**Purpose:** Unified gateway to interface with LLM providers (OpenAI, Anthropic, Google Gemini, local Ollama).

| Class | Method | Description |
|---|---|---|
| `LLMClient` | `__init__(provider, api_key, model_name, system_prompt)` | Initializes with provider config. Loads API key from env vars if not supplied. |
| | `_load_api_key() -> Optional[str]` | Reads from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` depending on provider. |
| | `_get_default_model() -> str` | Returns default model per provider (gpt-4o, claude-3-opus, gemini-1.5-pro, llama3). |
| | `generate_response(prompt, context) -> str` | Dispatches to the correct provider's API. Combines context + prompt. |
| | `_call_openai(prompt)`, `_call_anthropic(prompt)`, `_call_google(prompt)`, `_call_ollama(prompt)` | Provider-specific API calls with error handling. |

**Test approach:** Mock each provider's API. Verify prompt construction. Test missing API key handling. Test unsupported provider error.

---

## 2. `astraeus/analysis/` — Signal Processing & Detection

The analysis layer handles detrending, BLS period search, transit detection, validation, MCMC fitting, and reporting.

### 2.1 `detrending.py`

**Purpose:** Removes stellar variability from light curves.

| Class | Method | Description |
|---|---|---|
| `DetrendingEngine` | `estimate_stellar_rotation(time, flux) -> float` | Uses Lomb-Scargle periodogram to estimate the stellar rotation period (searches 0.1–10.0 day⁻¹). Down-samples to 2000 points if data is large. |
| | `detrend(time, flux, stellar_rotation_period_days) -> np.ndarray` | Detrends using `wotan` (biweight filter) if available, else falls back to `scipy.ndimage.median_filter`. Window: `min(1.5, max(0.5, rotation * 0.5))` days. |

**Test approach:** Generate sinusoidal light curve with rotation + transit dips. Verify transit dips preserved after detrending. Test fallback median filter path.

---

### 2.2 `bls_search.py`

**Purpose:** Box Least Squares period search using `astropy.timeseries.BoxLeastSquares`.

| Class | Method | Description |
|---|---|---|
| `BLSSearchEngine` | `compute_snr_depth(time, flux, p, t0, dur) -> (float, float)` | Computes SNR and depth for a single period/epoch/duration. Phase-folds, separates in/out of transit. |
| | `search(time, flux) -> dict` | Full BLS search. Dynamic period grid: dual-zone layout (0.5–20 and 20–350 days). Tests 11 durations. Anti-aliasing pass checks 0.5× and 2× harmonics. Returns `period`, `duration`, `t0`, `snr`, `depth`, `confidence_score`, `periodogram`. |
| | `mask_transit(time, flux, period, t0, duration) -> (np.ndarray, np.ndarray)` | Masks out transit windows (±2.5× duration) for residual analysis. |

**Test approach:** Inject sinusoidal transit at known period. Verify recovered period within tolerance. Test anti-aliasing on harmonic signals.

---

### 2.3 `detection.py`

**Purpose:** Single-planet transit detection pipeline that chains detrending → BLS → geometric validation → physical properties → TTV.

| Function | Signature | Description |
|---|---|---|
| `detect_transit_candidate` | `(time, flux, target_name, data_source, metadata, snr_threshold) -> dict` | Full detection pipeline. Runs up to 3 iterations of BLS search. Applies vetting: V-shape metric, secondary eclipse, depth thresholds. Assigns vetting status: `Verified Planet Candidate`, `Eclipsing Binary Detected`, `V-Shaped False Positive Risk`, or `Atmospheric Occultation Detected`. |
| `validate_bls_candidate` | `(transit_depth, out_of_transit_flux, in_transit_count, snr_threshold) -> (bool, float)` | Standalone SNR validation. |

**Vetting logic:**
- Depth < 3% → Verified Planet Candidate
- V-shape > 0.85 AND secondary eclipse AND (low SNR or deep eclipse) → Eclipsing Binary
- Low flat-bottom AND V-shape → V-Shaped False Positive Risk
- Shallow secondary (< 800 ppm) → Atmospheric Occultation

**Test approach:** Use synthetic transit data. Verify vetting status assignments for different signal shapes (boxy vs V-shaped, with/without secondary eclipse).

---

### 2.4 `geometric_validation.py`

**Purpose:** Validates transit signal shape to distinguish planets from eclipsing binaries.

| Class | Method | Description |
|---|---|---|
| `GeometricValidator` | `validate(time, flux, period, t0, duration, depth_fraction) -> dict` | Computes: `v_shape_metric` (curvature of transit profile), `flat_bottom_fraction` (fraction of in-transit points near minimum), `secondary_eclipse_depth`, `secondary_eclipse_snr`, `secondary_eclipse_detected`. Uses polynomial fit and second-derivative analysis. |

**Test approach:** Box-shaped transit → low v_shape, high flat_bottom. V-shaped (grazing binary) → high v_shape, low flat_bottom.

---

### 2.5 `physical_properties.py`

**Purpose:** Derives physical properties (planet radius, equilibrium temperature, JWST TSM score) from transit parameters.

| Class | Method | Description |
|---|---|---|
| `PhysicalPropertiesEngine` | `derive(period_days, transit_depth_fraction, st_rad, st_teff, st_mass, sy_jmag) -> dict` | Computes `planet_radius_earth` (from depth + stellar radius), `equilibrium_temp_k` (from stellar luminosity and semi-major axis), `jwst_tsm_score` (Kempton et al. 2018 metric with radius-dependent scaling). |

**Test approach:** Known system (e.g., Earth-like): verify radius ~ 1 R⊕. Verify TSM score is non-negative.

---

### 2.6 `ttv_analysis.py`

**Purpose:** Transit Timing Variation (TTV) analysis — measures epoch-by-epoch timing residuals.

| Class | Method | Description |
|---|---|---|
| `TTVAnalyzer` | `calculate(time, flux, period, t0, duration) -> list` | Iterates over each transit epoch, finds the weighted mean flux minimum within a transit window, and computes `ttv_residual_min = (t_obs - t_calc) × 1440`. Returns list of `{epoch, ttv_residual_min}` dicts. |

**Test approach:** Inject constant-period transit → TTV residuals should be near zero. Inject sinusoidal TTV → verify recovered amplitude.

---

### 2.7 `fitting.py`

**Purpose:** Bayesian objective functions for fitting transit models to light curves.

| Function | Signature | Description |
|---|---|---|
| `log_likelihood` | `(theta, time, flux, flux_err, fixed_params, param_names) -> float` | Gaussian log-likelihood. Constructs planet parameter dicts from theta, runs `generate_multi_planet_transit`, returns `-0.5 × Σ((data-model)/σ)²`. |
| `log_prior` | `(theta, param_names) -> float` | Uniform priors: `0 < radius_ratio < 1`, `0 ≤ inclination ≤ 90`, `0 ≤ u1, u2 ≤ 1`, `0 ≤ e < 1`. Returns `-inf` for out-of-bounds. |
| `log_probability` | `(theta, time, flux, flux_err, fixed_params, param_names) -> float` | `log_prior + log_likelihood`. |

**Test approach:** Verify prior returns `-inf` for invalid params. Verify likelihood peaks at known transit parameters.

---

### 2.8 `optimization.py`

**Purpose:** Non-linear optimization (Nelder-Mead) for finding MAP estimate before MCMC.

| Function | Signature | Description |
|---|---|---|
| `find_best_fit` | `(initial_guess_theta, time, flux, flux_err, fixed_params, param_names) -> (np.ndarray, bool)` | Minimizes negative log-probability using Nelder-Mead. Returns optimized parameters and convergence flag. |

**Test approach:** Start from perturbed initial guess; verify convergence toward true parameters.

---

### 2.9 `error_analysis.py`

**Purpose:** MCMC uncertainty quantification using the `emcee` ensemble sampler.

| Function | Signature | Description |
|---|---|---|
| `run_mcmc` | `(best_fit_theta, time, flux, flux_err, fixed_params, param_names, n_walkers=32, n_steps=2000, progress_callback, return_acceptance) -> tuple` | Initializes walkers in a Gaussian ball around `best_fit_theta`. Runs `emcee.EnsembleSampler`. Discards first 20% as burn-in. Returns flattened chain and 16/50/84 percentiles. Optionally returns mean acceptance fraction. |

**Test approach:** Use synthetic data with known parameters. Verify recovered percentiles contain true values. Check acceptance fraction is reasonable (~0.2–0.5).

---

### 2.10 `explanation.py`

**Purpose:** Generates scientific explanations of MCMC results using an LLM.

| Function | Signature | Description |
|---|---|---|
| `get_scientific_explanation` | `(params, uncertainties, residuals, provider, model_name, api_key) -> Dict[str, str]` | Sends fitted parameters, uncertainties, and residuals to an LLM. Returns dict with `physics_interpretation`, `parameter_breakdown`, `uncertainty_analysis`. Parses JSON response from LLM. |

**Test approach:** Mock LLM response. Verify JSON parsing and error handling.

---

### 2.11 `logging.py`

**Purpose:** Experiment tracking and persistence to JSON log files.

| Function / Class | Description |
|---|---|
| `generate_dataset_hash(metadata)` | SHA-256 hash of metadata for deduplication. |
| `save_experiment_log(params, metadata, fig_paths) -> str` | Appends an experiment entry (with UUID and timestamp) to `logs/experiments.json`. Returns the UUID. |
| `load_experiment_history() -> list` | Loads all past experiments from the JSON log. |
| `ExperimentLedger` | Class-based ledger with `log_candidate(target_metadata, calculated_period, signal_confidence, tracking_statistics, data_source, pipeline_timestamps)`. Uses atomic file writes (write-to-tmp then replace). |

**Test approach:** Save an experiment, reload, verify contents. Test hash generation. Test atomic write safety.

---

### 2.12 `reporting.py`

**Purpose:** Generates arXiv-style academic PDF reports using ReportLab.

| Class / Function | Description |
|---|---|
| `NumberedCanvas` | Custom ReportLab canvas that adds page numbers and timestamp footer. |
| `sanitize_text(text)` | Strips non-ASCII characters (Greek letters, emoji, special symbols) for ReportLab core fonts. |
| `_validate_schema(metrics_payload)` | Validates that payload has `star_id` and `candidates` list. |
| `extract_plot_image(fig, usable_width, tracked_streams)` | Extracts Plotly figures as PNG images for PDF embedding. Falls back to matplotlib re-rendering if Kaleido is unavailable, then to a styled text placeholder. |
| `_build_fallback_canvas(usable_width, reason)` | Renders a placeholder when figure extraction fails entirely. |
| `_rasterize_with_matplotlib(fig, tracked_streams)` | Rebuilds Plotly traces as matplotlib PNG (dark theme preserved). |
| `generate_academic_report(metrics_payload, figures) -> io.BytesIO` | Main entry point: builds a complete arXiv-style PDF with title, abstract, sections, properties table, and embedded figures. Returns in-memory PDF buffer. |

**Test approach:** Call with valid payload + mock figures. Verify PDF is non-empty bytes. Test with missing Kaleido to verify fallback path.

---

## 3. `astraeus/data/` — Data Handling & Ingestion

### 3.1 `adapter.py`

**Purpose:** Format-agnostic data adapter that normalizes CSV, FITS, and JSON datasets into a uniform internal format.

| Class | Method | Description |
|---|---|---|
| `DataAdapter` | `__init__(data_bytes, filename_or_ext, column_map)` | Stores raw bytes, detects format, optional column mapping. |
| | `parse() -> dict` | Auto-detects CSV/FITS/JSON, extracts time/flux/flux_err columns, extracts FITS headers as metadata. Returns `{time, flux, flux_err, metadata}`. |
| | `_scan_columns(dataframe)` | Heuristic column detection using pattern matching (e.g., `bjd_tdb` → time, `pdcsap_flux` → flux). |
| | `_parse_fits(data_bytes) -> pd.DataFrame` | Reads FITS binary table into pandas DataFrame. |
| | `_extract_fits_metadata(data_bytes) -> dict` | Extracts FITS header keywords as metadata. |
| | `_standardize_arrays(dataframe) -> dict` | Converts columns to numpy float64 arrays, filters NaN/Inf. |

**Column patterns:** `TIME_PATTERNS = ["time", "bjd_tdb", "bjd", "hjd", "mjd"]`, `FLUX_PATTERNS = ["flux", "pdcsap_flux", ...]`, `ERR_PATTERNS = ["err", "sig", ...]`.

**Test approach:** Parse CSV with known columns. Parse FITS file. Test column mapping overrides. Test NaN/Inf filtering.

---

### 3.2 `discovery.py`

**Purpose:** Remote exoplanet data discovery via `astroquery`.

| Class | Method | Description |
|---|---|---|
| `RemoteDiscoveryEngine` | `query_metadata(target_name) -> dict` | Queries NASA Exoplanet Archive via `astroquery` for `pscomppars` then `ps` tables. Returns `{pl_name, pl_orbper, st_rad, pl_trandep, source_table}`. |

**Test approach:** Mock `astroquery` responses. Test fallback from `pscomppars` to `ps`.

---

### 3.3 `loader.py`

**Purpose:** High-level data loading facade.

| Function / Class | Description |
|---|---|
| `fetch_lightcurve(target_name, mission)` | Downloads and stitches lightkurve data. |
| `clean_lightcurve(lc)` | Removes bad quality flags and NaNs. |
| `extract_lightcurve_arrays(lc)` | Extracts time, flux, flux_err arrays. |
| `load_nasa_lightcurve(target_name, mission)` | Full pipeline: fetch → clean → normalize → extract. |
| `DataFactory` | Factory class with `load(source, ...)` for loading from different sources. |
| `NASAArchiveLoader` | Loader subclass for NASA archive data. |
| `_resolve_columns(df, column_map)` | Resolves column names from mapping or heuristic patterns. |

**Test approach:** Requires mocked lightkurve. Verify array extraction and normalization.

---

### 3.4 `preprocessing.py`

**Purpose:** Preprocessing utilities for light curves.

| Function | Signature | Description |
|---|---|---|
| `inject_gaussian_noise` | `(flux, snr, seed=42) -> np.ndarray` | Adds white Gaussian noise at target SNR. `σ = mean(|flux|) / snr`. |
| `detrend_lightcurve` | `(time, flux, window_length=101) -> np.ndarray` | Savitzky-Golay filter detrending. Divides flux by trend. |
| `standardize_imported_data` | `(time, flux, flux_err) -> dict` | Sorts by time, removes NaN/Inf, ensures baseline = 1.0. |

**Test approach:** Verify noise level matches target SNR. Verify detrending preserves transit depth.

---

## 4. `astraeus/simulation/` — Synthetic Data Generation

### 4.1 `synthetic.py`

**Purpose:** Generates synthetic transit light curves for validation and injection-recovery tests.

| Data Class | Description |
|---|---|---|
| `SyntheticTransitScenario` | Configuration dataclass: `duration`, `period`, `eccentricity`, `radius_ratio`, `snr`, `samples`, `seed`, `stellar_radius`, `semi_major_axis`, `inclination`. Class method `hot_jupiter()` returns default 10-day scenario. |
| `LightCurveSeries` | Container: `time_days`, `theoretical_flux`, `observed_flux`. |

| Function | Description |
|---|---|
| `generate_synthetic_transit_series(scenario) -> LightCurveSeries` | Generates theoretical flux using `generate_model_flux`, then adds Gaussian noise. |
| `run_injection_recovery(scenario, n_injections) -> dict` | Injects a synthetic planet into a light curve and runs BLS to recover it. Reports recovery rate, period error, depth error. |
| `_validate_scenario(scenario)` | Validates scenario parameters. |

**Test approach:** Generate synthetic data; verify transit is visible at known period. Run injection recovery; verify >90% recovery rate at high SNR.

---

## 5. `astraeus/visualization/` — Plotting Utilities

### 5.1 `plots.py`

**Purpose:** Matplotlib-based plotting for validation workflows (non-interactive Agg backend).

| Function | Signature | Description |
|---|---|---|
| `plot_synthetic_validation` | `(time_days, theoretical_flux, observed_flux, output_path) -> Path` | Two-panel plot: top = model vs noisy data, bottom = residuals. Saves to file. |
| `plot_corner` | `(flat_samples, labels, output_path) -> Path` | MCMC corner plot showing posterior distributions and pairwise correlations. |

**Test approach:** Generate plot, verify file exists and is a valid PNG.

---

## 6. `astraeus/workflows/` — Pipeline Orchestration

### 6.1 `pipeline.py`

**Purpose:** End-to-end orchestration pipelines for synthetic validation and real-data retrieval.

| Class | Method | Description |
|---|---|---|
| `SyntheticValidationPipeline` | `run_generation()` | Phase 1: Generates synthetic hot-Jupiter data and saves validation plot. |
| | `run_retrieval(scenario, light_curve)` | Phase 2: Runs `find_best_fit` → `run_mcmc` on synthetic data. |
| | `run_full()` | Executes generation → retrieval → saves outputs. |
| `RealDataPipeline` | `execute_full_workflow(target_name, mission, quarter)` | Downloads real Kepler/TESS data and runs full retrieval. |

**Test approach:** Run `SyntheticValidationPipeline.run_full()` and verify outputs exist.

---

## 7. `astraeus/ui/` — Streamlit UI Pages

### 7.1 `dashboard.py`

**Purpose:** Streamlit production dashboard — unified visualization surface for the BLS discovery pipeline and PDF manuscript generation.

| Function | Description |
|---|---|
| `_check_headless_prerequisites()` | Warns if Kaleido is missing for PDF generation. |
| `_build_phase_folded_figure(cand)` | Generates a synthetic phase-folded scatter Plotly figure from candidate parameters. |
| `_render_inspection_panel(cand, cand_idx)` | Renders per-candidate detail view. |
| `main()` | Streamlit entry point. Renders baseline Kepler-90 discovery payload, candidate cards, PDF export button. |

**Entry point:** `streamlit run astraeus/ui/dashboard.py`

---

### 7.2 `ui/pages/detective.py`

**Purpose:** The "Detective" page — full multi-planet transit detection workflow in the Streamlit UI.

| Function | Description |
|---|---|
| `render()` | Main render function (complexity 69). Handles target name input, mission selection, detection triggers, candidate display, phase-folded plots, discovery bar. |
| `render_discovery_bar(candidates)` | Horizontal bar chart of discovered planet SNRs. |

**Test approach:** Streamlit testing with `streamlit.testing` or manual verification.

---

### 7.3 `ui/pages/lab.py`

**Purpose:** Interactive transit model playground with real-time parameter sliders.

| Description | Uses `sensitivity_engine.get_model_curve` for instant model updates. Sliders for period, radius ratio, semi-major axis ratio, inclination. |
|---|---|

**Test approach:** Verify model updates on slider change. Test performance with large time arrays.

---

### 7.4 `ui/pages/history.py`

**Purpose:** Displays past experiment history from `logs/experiments.json`.

| Description | Loads experiment ledger, renders a table with timestamp, target, period, SNR, and status columns. |
|---|---|

---

### 7.5 `ui/pages/settings.py`

**Purpose:** Configuration page for API keys and model settings.

**Test approach:** Verify settings persist across Streamlit sessions.

---

### 7.6 `ui/pages/simulator.py`

**Purpose:** N-body gravitational stability simulator page.

| Description | Renders planet configuration inputs, runs `check_system_stability`, displays stability verdict, eccentricity drift, energy error. |
|---|---|

**Test approach:** Configure a known stable system; verify "Stable" result. Configure an unstable one; verify collision/ejection detection.

---

## 8. `astraeus/dashboard/` — Streamlit Dashboard (Legacy)

### 8.1 Key Dashboard Modules

| Module | Description |
|---|---|
| `dashboard/ui/layout.py` | `workbench_layout()` — Multi-page navigation layout with left nav bar. `render_left_nav()` — Sidebar navigation component. |
| `dashboard/ui/styles.py` | `inject_page_styles()` — Custom CSS injection for the Streamlit dashboard (dark theme, typography). |
| `dashboard/ui/components.py` | `render_floating_chat()` — Floating LLM chat panel UI. |
| `dashboard/ui/sidebar.py` | Sidebar configuration and navigation links. |
| `dashboard/ui/simulation_panel.py` | N-body simulation controls and visualization. |
| `dashboard/ui/mcmc_panel.py` | MCMC retrieval controls with progress callback. |
| `dashboard/ui/mcmc_form.py` | Form for MCMC parameter configuration. |
| `dashboard/ui/data_ingestion_panel.py` | File upload and data ingestion controls. |
| `dashboard/ui/action_deck.py` | Export controls (PDF, JSON, PNG). |
| `dashboard/ui/settings.py` | Settings page rendering. |
| `dashboard/services/mcmc_retrieval.py` | MCMC execution service. `resolve_transit_epoch()` helper. |
| `dashboard/services/data_ingestion.py` | Data loading service layer. |
| `dashboard/services/action_deck.py` | Export execution service. |
| `dashboard/figures.py` | `make_multi_orbit_figure()`, `make_multi_orbit_animation_html()` — 3D orbit visualization figures. |
| `dashboard/scenario.py` | Scenario dataclass for dashboard simulations. |
| `dashboard/simulation.py` | Dashboard simulation orchestration. |
| `dashboard/validation.py` | `validate_scenario()` — Input validation for scenarios. |

---

## 9. Top-Level Scripts

### 9.1 `app.py`

**Purpose:** Main Streamlit entry point for the unified dashboard.

**Entry point:** `streamlit run app.py`

Renders the detective, lab, history, settings, and simulator pages via `render_route()` from `route.py`. Contains a `BASELINE_PAYLOAD` with Kepler-90 discovery data for demo mode.

---

### 9.2 `route.py`

**Purpose:** Page routing for the Streamlit multi-page app.

| Function | Signature | Description |
|---|---|---|
| `render_route()` | Dispatches to the correct page renderer based on URL query parameter `page`. Supports `detective`, `lab`, `history`, `settings`, `simulator`. |

---

### 9.3 `runs/kepler90_blind_search.py`

**Purpose:** End-to-end blind search pipeline for Kepler-90 — a reference implementation of the full discovery workflow.

**Layers:**
1. `layer1_ingestion` — Downloads data via `RemoteDiscoveryEngine`.
2. `layer4_5_vetting_physics` — Runs detection, geometric validation, physical properties.
3. `layer6_ttv` — TTV analysis.
4. `main()` — Orchestrates all layers, saves outputs to `outputs/kepler90_blind_search/`.

---

### 9.4 `find_cycles.py`

**Purpose:** Utility to detect import cycles in the codebase.

| Function | Description |
|---|---|---|
| `get_imports(filepath)` | Parses a Python file and returns all import statements. |
| `main()` | Builds a dependency graph and detects cycles. |

---

### 9.5 `init_project.py`

**Purpose:** Project scaffolding script. Creates the initial directory structure and configuration files.

---

### 9.6 `extract.py`

**Purpose:** Utility script for extracting data from experiment outputs.

---

### 9.7 Test Scripts

| Script | Description |
|---|---|
| `test_engine.py` | Manual test for the N-body engine. |
| `test_orchestrator.py` | Manual test for the multi-planet orchestrator. |
| `test_ingest.py` | Manual test for data ingestion pipeline. |
| `run_test.py` | Test runner script. |
| `test_fetch.py` | Manual test for NASA archive fetching. |
| `test_nasa.py` | Manual test for NASA data access. |

---

## 10. `tests/` — Test Suite Overview

| Test File | What It Tests |
|---|---|
| `test_physics.py` | Core physics: Kepler solver, limb darkening, orbital positions. |
| `test_transit_model.py` | Geometric transit model accuracy. |
| `test_orbital_models.py` | Orbital position calculations. |
| `test_preprocessing.py` | Noise injection, detrending, standardization. |
| `test_synthetic_simulation.py` | Synthetic data generation. |
| `test_dashboard_simulation.py` | Dashboard simulation module. |
| `test_nbody_solver.py` | N-body stability solver integration. |
| `test_loader.py` | Data loading and column resolution. |
| `test_adapter.py` | DataAdapter CSV/FITS parsing. |
| `test_discovery.py` | Remote discovery module. |
| `test_mcmc.py` | MCMC sampling and convergence. |
| `test_multi_planet_scaling.py` | Multi-planet parameter scaling. |
| `test_bulletproof_detector.py` | Detection pipeline robustness. |
| `test_agent_detective.py` | Detective page panel routing. |
| `test_lab_realtime.py` | Lab page real-time slider sync. |
| `test_experiment_history.py` | Experiment ledger persistence. |
| `test_ui_flow.py` | End-to-end Streamlit UI flow. |
| `test_workbench_navigation.py` | Multi-page navigation persistence. |
| `test_chaos_integration_suite.py` | Comprehensive integration chaos tests. |
| `pipeline_stress_test.py` | Pipeline under heavy load. |
| `global_matrix_stress_test.py` | Full parameter grid stress testing. |
| `solid_matrix_diagnostic.py` | Diagnostic matrix for all modules. |
| `system_flight_bench.py` | System-wide performance benchmark. |
| `debug_metadata_network.py` | Debug tool for metadata fetching. |
| `trace_download_deadlock.py` | Debug tool for download deadlock detection. |

---

## 11. Quick Test Commands

```bash
# Run full pytest suite
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_physics.py -v              # Core physics
python -m pytest tests/test_transit_model.py -v        # Transit model
python -m pytest tests/test_nbody_solver.py -v          # N-body solver
python -m pytest tests/test_mcmc.py -v                  # MCMC fitting
python -m pytest tests/test_adapter.py -v               # Data adapter
python -m pytest tests/test_loader.py -v                # Data loader
python -m pytest tests/test_bulletproof_detector.py -v  # Detection pipeline
python -m pytest tests/test_chaos_integration_suite.py -v  # Integration tests

# Run specific test by function name
python -m pytest tests/test_physics.py::test_limb_darkening_module -v
python -m pytest tests/test_transit_model.py -k "transit" -v

# Manual N-body test
python test_engine.py

# Manual orchestrator test
python test_orchestrator.py

# Manual ingestion test
python test_ingest.py

# Run the dashboard
streamlit run app.py
streamlit run astraeus/ui/dashboard.py
```

---

> **Tip:** After modifying any module, run `codegenome analyze` or `codegenome evolve --live` to keep the architectural knowledge graph updated.
