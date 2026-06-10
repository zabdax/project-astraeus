<pre>
   █████╗ ███████╗████████╗██████╗  █████╗ ███████╗██╗   ██╗███████╗
  ██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║   ██║██╔════╝
  ███████║███████╗   ██║   ██████╔╝███████║█████╗  ██║   ██║███████╗
  ██╔══██║╚════██║   ██║   ██╔══██╗██╔══██║██╔══╝  ██║   ██║╚════██║
  ██║  ██║███████║   ██║   ██║  ██║██║  ██║███████╗╚██████╔╝███████║
  ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝
</pre>

<div align="center">

**Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![NumPy](https://img.shields.io/badge/NumPy-2.2-013243?logo=numpy&logoColor=white)](https://numpy.org/)
[![Astropy](https://img.shields.io/badge/Astropy-6.1-blue)](https://www.astropy.org/)
[![Lightkurve](https://img.shields.io/badge/Lightkurve-2.4%2B-orange)](https://lightkurve.github.io/)

*A physics-first computational astrophysics platform for exoplanet transit modeling, MCMC parameter retrieval, and AI-assisted analysis.*

</div>

---

## Overview

**Project ASTRAEUS** is a computational astrophysics research platform that bridges the gap between theoretical orbital mechanics and real space telescope observational data. It implements a complete end-to-end pipeline — from raw photometric light curve ingestion all the way through Bayesian parameter retrieval — packaged inside an interactive Streamlit dashboard with an integrated AI co-pilot.

### Core Research Question
> *How accurately can exoplanet transit parameters be recovered from noisy photometric data using first-principles modeling?*

The answer is computed by building the physics from scratch: Kepler's equation, sky-plane transit geometry, limb-darkened flux integrals, and finally Markov Chain Monte Carlo (MCMC) posterior sampling — with no black-box shortcuts.

---

## Key Features

| Feature | Description |
|---|---|
| 🪐 **First-Principles Physics Engine** | Keplerian orbital mechanics, transit geometry, and limb-darkened flux modeling built from scratch |
| 📡 **Real Mission Data** | Fetch light curves directly from NASA's Kepler, K2, and TESS archives via Lightkurve |
| 📂 **Local Data Ingestion** | Upload custom `.csv` / `.json` photometric files with configurable column mapping |
| 🔬 **Synthetic Simulation** | Generate realistic, noise-controlled synthetic transit series for algorithm validation |
| 📊 **MCMC Parameter Retrieval** | Bayesian posterior sampling with `emcee` — extract Rp/Rs, inclination, and limb darkening with credible intervals |
| 🗺️ **MAP Optimization** | Maximum A Posteriori estimation as a fast warm-start before expensive MCMC runs |
| 🧮 **Interactive Dashboard** | Full-featured Streamlit UI with 3D orbit views, live simulations, and MCMC execution panels |
| 🤖 **AI Co-Pilot** | Pluggable LLM gateway (OpenAI, Anthropic, Google Gemini, or local Ollama) for automated result interpretation |
| 📄 **PDF Reporting** | Auto-generation of research-grade analysis reports via `fpdf2` |
| 🕵️ **Smart Vetting** | SNR-aware false positive vetting (V-shape, secondary eclipse occultation, ultra-short periods) |

---

## Architecture

```
project-astraeus/
│
├── app.py                      # Streamlit entry point
├── route.py                    # Page router
├── config.json                 # LLM provider & API key configuration
├── requirements.txt
│
└── astraeus/                   # Core Python package
    ├── core/                   # First-principles physics engine
    │   ├── orbits.py           # KeplerianOrbit — 3D orbital dynamics
    │   ├── kepler.py           # Newton-Raphson Kepler equation solver
    │   ├── orbital_models.py   # Orbital model abstractions
    │   ├── transit_model.py    # Sky-separation & limb-darkened flux
    │   ├── geometry.py         # Circle overlap & projection geometry
    │   ├── constants.py        # Physical constants (SI units)
    │   ├── validation.py       # Parameter bound & physics checks
    │   ├── sensitivity_engine.py # Sensitivity analysis tools
    │   ├── ingestion.py        # Core ingestion utilities
    │   └── llm_gateway.py      # Unified LLM client (OpenAI/Anthropic/Google/Ollama)
    │
    ├── data/                   # Data ingestion & preprocessing
    │   ├── loader.py           # NASA archive & local file loader
    │   ├── adapter.py          # Data format adapter
    │   ├── discovery.py        # Target discovery helpers
    │   └── preprocessing.py    # Detrending, phase-folding
    │
    ├── simulation/             # Synthetic data generation
    │   └── synthetic.py        # SyntheticTransitScenario & series generator
    │
    ├── analysis/               # Statistical modeling & retrieval
    │   ├── fitting.py          # Model fitting utilities
    │   ├── optimization.py     # MAP (Maximum A Posteriori) estimation
    │   ├── error_analysis.py   # MCMC posterior sampling (emcee)
    │   ├── detection.py        # Main transit detection orchestrator
    │   ├── bls_search.py       # BLS Search Engine
    │   ├── detrending.py       # Detrending Engine
    │   ├── geometric_validation.py # V-shape & secondary eclipse validation
    │   ├── physical_properties.py  # Planet radius & temp derivation
    │   ├── ttv_analysis.py     # Transit Timing Variation Analyzer
    │   ├── explanation.py      # LLM-driven result explanation
    │   ├── reporting.py        # PDF report generation
    │   └── logging.py          # Analysis logging
    │
    ├── visualization/          # Static scientific plotting
    │   └── plots.py            # Multi-panel Matplotlib figures, corner plots
    │
    ├── workflows/              # Orchestration pipelines
    │   └── pipeline.py         # RealDataPipeline — end-to-end orchestrator
    │
    └── dashboard/              # Interactive Streamlit frontend
        ├── figures.py          # Plotly chart builders
        ├── simulation.py       # Simulation state management
        ├── ui/                 # UI layout & components
        │   ├── layout.py       # Workbench layout
        │   ├── components.py   # Reusable UI widgets & floating AI chat
        │   ├── sidebar.py      # Navigation sidebar
        │   ├── action_deck.py  # Action button deck
        │   ├── data_ingestion_panel.py
        │   ├── simulation_panel.py
        │   ├── mcmc_panel.py   # MCMC execution UI
        │   ├── mcmc_form.py
        │   └── settings.py
        └── services/           # Dashboard business logic
            ├── data_ingestion.py
            ├── mcmc_retrieval.py
            └── action_deck.py
```

---

## Physics Pipeline

```
Raw Photometric Data (TESS / Kepler / CSV)
         │
         ▼
  ┌─────────────────────────────────┐
  │  Data Ingestion & Preprocessing │
  │  • Detrending (Savitzky-Golay)  │
  │  • Phase-folding (period est.)  │
  └─────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  First-Principles Transit Model │
  │  • Keplerian orbit (3D)         │
  │  • Sky-plane separation         │
  │  • Circle overlap → flux drop   │
  │  • Quadratic limb darkening     │
  └─────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  MAP Optimization               │
  │  • Fast initial parameter guess │
  │  • scipy.optimize minimization  │
  └─────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  MCMC Posterior Sampling        │
  │  • emcee ensemble sampler       │
  │  • Posteriors: Rp/Rs, i, u1, u2 │
  │  • Median + credible intervals  │
  └─────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  Results & Reporting            │
  │  • Phase-folded best-fit plots  │
  │  • AI-generated interpretation  │
  │  • PDF research report          │
  └─────────────────────────────────┘
```

---

## Installation

### Prerequisites

- Python **3.10+**
- `pip` or `conda`

### 1. Clone the repository

```bash
git clone https://github.com/zabdax/project-astraeus.git
cd project-astraeus
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Configure the AI Co-Pilot

Edit `config.json` to set your preferred LLM provider and supply your API key:

```json
{
    "llm_provider": "google",
    "llm_model": "gemini-1.5-pro-latest",
    "api_keys": {
        "google": "YOUR_GOOGLE_API_KEY",
        "openai": "YOUR_OPENAI_API_KEY",
        "anthropic": "YOUR_ANTHROPIC_API_KEY"
    }
}
```

Alternatively, set environment variables:

```bash
export GOOGLE_API_KEY="..."
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

For local offline inference, install and run [Ollama](https://ollama.ai/) and set `"llm_provider": "ollama"` in `config.json`.

---

## Usage

### Launch the Interactive Dashboard

```bash
streamlit run app.py
```

The dashboard opens at `http://localhost:8501` and provides three main panels:

#### 🔭 Data Ingestion
- Select **NASA Archive** to query TESS / Kepler / K2 by target name (e.g., `WASP-12b`, `TrES-2b`)
- Or upload a local `.csv` / `.json` file with custom column mapping
- Preview the raw light curve with interactive Plotly rendering

#### 🪐 Simulation Workbench
- Tune physical parameters via sidebar sliders: radius ratio, orbital period, eccentricity, inclination, SNR
- Live-updating KPI metrics: semi-major axis, transit depth, noise sigma
- Dynamic Plotly figures:
  - **3D Orbit View** — geometric visualization of the planetary system
  - **Synthetic Light Curve** — simulated transit flux with realistic noise
  - **Residuals** — deviation between pure model and noisy signal

#### 📊 MCMC Retrieval
- Set fixed stellar/orbital parameters and initial parameter guesses
- One-click MCMC execution with live progress bar and ETA
- Output: median recovered parameters, standard deviations, and phase-folded best-fit visualization

### Run the Scripted Pipeline (CLI)

```bash
python astraeus/main.py
```

This orchestrates a complete workflow for a known target (e.g., `TrES-2b` from Kepler Quarter 1 data) and saves outputs to `outputs/`.

---

## Supported Data Sources

| Source | Access Method | Missions |
|---|---|---|
| NASA Exoplanet Archive | `lightkurve` API query | Kepler, K2, TESS |
| Local files | File upload (dashboard) or path | Custom `.csv`, `.json` |
| Synthetic data | Built-in generator | Configurable SNR, depth, duration |

---

## Retrieved Parameters

ASTRAEUS recovers the following physical parameters through Bayesian inference:

| Parameter | Symbol | Description |
|---|---|---|
| Planet-to-star radius ratio | Rp/Rs | Determines transit depth |
| Orbital inclination | i | Transit chord geometry |
| Quadratic limb darkening | u₁, u₂ | Stellar brightness profile |
| Orbital period | P | From phase-folding / prior |
| Mid-transit time | t₀ | Auto-estimated via filtering |

---

## LLM Co-Pilot Integration

The embedded `LLMClient` in `astraeus/core/llm_gateway.py` provides a **provider-agnostic** interface to:

| Provider | Default Model | Requires |
|---|---|---|
| Google Gemini | `gemini-1.5-pro-latest` | `GOOGLE_API_KEY` |
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `claude-3-opus-20240229` | `ANTHROPIC_API_KEY` |
| Ollama (local) | `llama3` | Ollama running locally |

The AI co-pilot automatically contextualises retrieved astrophysical results and generates natural-language explanations, making results accessible without prior expertise.

---

## Roadmap

- [x] Keplerian orbital mechanics & transit geometry engine
- [x] Real photometric dataset integration (TESS / Kepler)
- [x] MAP optimization for fast parameter estimation
- [x] MCMC posterior sampling with credible intervals
- [x] Interactive Streamlit dashboard with 3D orbit viewer
- [x] Pluggable LLM co-pilot (OpenAI / Anthropic / Google / Ollama)
- [x] PDF research report generation
- [ ] Stellar variability modeling (non-constant baseline)
- [ ] Multi-planet N-body system support
- [ ] Auto-generated LaTeX / PDF research papers
- [x] Transit timing variation (TTV) analysis
- [ ] Comparative study across mission datasets (Kepler vs TESS)

---

## Tech Stack

| Library | Version | Purpose |
|---|---|---|
| [NumPy](https://numpy.org/) | 2.2.6 | Numerical computation |
| [SciPy](https://scipy.org/) | 1.15.3 | Optimization & signal processing |
| [Astropy](https://www.astropy.org/) | 6.1.7 | Astronomy units & coordinate systems |
| [Lightkurve](https://lightkurve.github.io/) | ≥ 2.4.0 | NASA mission data access |
| [Matplotlib](https://matplotlib.org/) | 3.10.9 | Static scientific figures |
| [Plotly](https://plotly.com/) | 5.24.1 | Interactive 3D orbit & light curve visualization |
| [Streamlit](https://streamlit.io/) | 1.41.1 | Interactive dashboard framework |
| [emcee](https://emcee.readthedocs.io/) | — | MCMC ensemble sampling |
| [fpdf2](https://pyfpdf.github.io/fpdf2/) | ≥ 2.7.9 | PDF report generation |

---

## Research Principles

This project is built on a strict **physics-first** philosophy:

- ✅ Every model has an explicit physical derivation — no black-box ML shortcuts
- ✅ All assumptions and parameter bounds are documented and validated
- ✅ Results are fully reproducible from raw data to final figures
- ✅ Uncertainties are always propagated (MCMC credible intervals, not just point estimates)

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Author

**Zubayer Hasan Shaad**  
Independent student researcher focused on Astronomy & Astrophysics, Artificial Intelligence, and Computational Science.

---

<div align="center">

*"The cosmos is within us. We are made of star-stuff."* — Carl Sagan

</div>
