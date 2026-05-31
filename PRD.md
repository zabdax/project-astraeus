# Project ASTRAEUS - Product Requirements Document (PRD)

<pre>
   █████╗ ███████╗████████╗██████╗  █████╗ ███████╗██╗   ██╗███████╗
██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║   ██║██╔════╝
███████║███████╗   ██║   ██████╔╝███████║█████╗  ██║   ██║███████╗
██╔══██║╚════██║   ██║   ██╔══██╗██╔══██║██╔══╝  ██║   ██║╚════██║
██║  ██║███████║   ██║   ██║  ██║██║  ██║███████╗╚██████╔╝███████║
╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝                                                                  
</pre>

**Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space**

---

## 1. Overview
Project ASTRAEUS is a computational astrophysics and AI-assisted research initiative focused on modeling, analyzing, and interpreting astronomical data using first-principles physics. The core research focus is **Exoplanet Transit & Orbital Analysis**, aiming to accurately recover exoplanet transit parameters from noisy photometric data using first-principles modeling.

This document serves as the PRD capturing the current state of the system, summarizing the features, modules, and workflows that have been implemented to date.

---

## 2. Architecture & Tech Stack

### Tech Stack
- **Language**: Python 3
- **Numerical Processing**: NumPy, SciPy
- **Astronomy Libraries**: Astropy, Lightkurve
- **Optimization & Sampling**: Emcee (for MCMC)
- **Data Visualization**: Matplotlib, Plotly
- **Interactive UI**: Streamlit

### Codebase Structure
The project is modularized within the `astraeus/` package, adhering to clean scientific computing principles:
- `core/`: First-principles physics models.
- `data/`: Ingestion and preprocessing pipelines.
- `analysis/`: Optimization and probabilistic modeling (MCMC).
- `simulation/`: Synthetic light curve generation.
- `visualization/`: Static plotting and reporting tools.
- `workflows/`: Orchestration pipelines binding the modules together.
- `dashboard/`: Interactive Streamlit frontend.

---

## 3. Implemented Features and Modules

### 3.1. Core Physics Engine (`astraeus/core`)
The foundational physics models simulating orbital mechanics and transit geometry.
- **Orbital Mechanics (`orbits.py`, `kepler.py`, `orbital_models.py`)**:
  - Implements `KeplerianOrbit` to manage 3D orbital dynamics in space.
  - Custom `NewtonRaphsonKeplerSolver` and `solve_kepler_equation` for robust resolution of Kepler's equation (eccentric anomaly).
  - Evaluates 3D orbital positions over time arrays.
- **Transit Modeling (`transit_model.py`, `geometry.py`)**:
  - Calculates projected sky separation between star and planet.
  - Analytically computes circle overlap areas to generate geometric transit light curves.
  - Configurable limb darkening parameters ($u_1, u_2$).
- **Validation (`validation.py`)**:
  - Checks parameter bounds and physically viable scenarios for the models.

### 3.2. Synthetic Simulation (`astraeus/simulation`)
Framework for generating synthetic, controlled data to test retrieval algorithms.
- **`synthetic.py`**:
  - Encapsulates `SyntheticTransitScenario` mapping physical parameters.
  - `generate_synthetic_transit_series` outputs `LightCurveSeries` mimicking noisy photometric observations, complete with controllable SNR, depth, and duration.

### 3.3. Data Ingestion & Preprocessing (`astraeus/data`)
Pipeline for acquiring and structuring real photometric data.
- **Data Loader (`loader.py`)**:
  - **Universal Ingestion API**: Capable of querying the NASA Exoplanet Archive (via `lightkurve`) to fetch real Kepler, K2, or TESS data for targets (e.g., WASP-12b, TrES-2b).
  - **Local Ingestion**: File uploader logic capable of parsing custom `.csv` and `.json` files, equipped with dynamic column mapping overrides for Time, Flux, and Flux Error.
- **Preprocessing (`preprocessing.py`)**:
  - **Detrending**: Smoothing out baseline stellar variations to isolate transits.
  - **Phase-Folding**: Aligns repeating transit signals into a single standardized phase space (centered at $t_0$), utilizing orbital period estimation.

### 3.4. Parameter Analysis & Retrieval (`astraeus/analysis`)
The statistical backend mapping observational data back to physical parameters.
- **Optimization (`optimization.py`, `fitting.py`)**:
  - Implements MAP (Maximum A Posteriori) estimation (`find_best_fit`) to locate the optimal initial parameter guess prior to expensive sampling.
- **Error Analysis via MCMC (`error_analysis.py`)**:
  - Orchestrates Markov Chain Monte Carlo (MCMC) sampling using `emcee`.
  - Estimates posterior probability distributions for $R_p/R_s$ (radius ratio), inclination, and limb darkening.
  - Extracts percentiles (medians and standard deviations) for physical parameter confidence intervals.

### 3.5. Data Visualization & Reporting (`astraeus/visualization`)
Static generation of scientific figures.
- **`plots.py`**: 
  - Generates comprehensive multi-panel Matplotlib figures for real data retrieval.
  - Includes phase-folded raw vs. theoretical flux plots, and corner-plot styled confidence visualizations.

### 3.6. Orchestration Workflows (`astraeus/workflows` & `main.py`)
- **`pipeline.py` (RealDataPipeline)**:
  - Binds data ingestion, preprocessing, MAP estimation, and MCMC into a unified pipeline.
- **`main.py`**:
  - Entry-point script orchestrating a complete workflow for known targets (e.g., retrieving parameters for `TrES-2b` from Kepler Quarter 1 data).

### 3.7. Interactive Dashboard (`astraeus/dashboard`)
A full-featured Streamlit-based web application providing an interactive UX for the underlying engine (`streamlit_app.py`).

**Dashboard Capabilities:**
1. **Data Ingestion Tab**:
   - GUI to select data source (NASA API vs Local Upload).
   - Real-time Plotly rendering of raw light curve previews.
2. **Interactive Simulation Tab**:
   - Sidebar sliders for Radius Ratio, Period, Eccentricity, Inclination, and SNR.
   - Reactive KPI metrics: Semi-major Axis, Transit Depth, Noise Sigma.
   - Dynamic Plotly figures:
     - **3D Orbit View**: Visualization of the planetary orbit geometry.
     - **Light Curve**: Simulated transit flux.
     - **Residuals**: Tracking deviations between pure model and noise.
3. **MCMC Execution Panel**:
   - Form-based parameter setup for fixed physics (Stellar Radius, SMA, Eccentricity) and initial guesses.
   - Fully interactive MCMC runner with:
     - Detrending and automated $t_0$ estimation (using Savitzky-Golay filtering).
     - Phase-folding visualization.
     - Live execution progress bar and ETA tracking.
     - Output dashboard presenting median retrieval parameters and an interactive phase-folded best-fit visual.

---

## 4. Current Phase Roadmap Integration

We have successfully achieved Phase 1 objectives and significant portions of advanced features:
- [x] Build orbital and transit simulation engine.
- [x] Integrate real photometric datasets (TESS/Kepler).
- [x] Implement parameter fitting algorithms (Optimization + MCMC).
- [x] Visual and Interactive UI layer (Dashboard).

### Next Steps (Future Scope based on existing foundations):
- **Stellar Variability**: Implement non-constant out-of-transit variations.
- **Multi-planet System**: Extend the `KeplerianOrbit` class and transit models to parse $N$-body systems.
- **Reporting**: Auto-generate research-grade PDF/LaTeX reports from the pipeline outputs.
