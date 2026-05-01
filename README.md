# Project ASTRAEUS
<pre>
   █████╗ ███████╗████████╗██████╗  █████╗ ███████╗██╗   ██╗███████╗
██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║   ██║██╔════╝
███████║███████╗   ██║   ██████╔╝███████║█████╗  ██║   ██║███████╗
██╔══██║╚════██║   ██║   ██╔══██╗██╔══██║██╔══╝  ██║   ██║╚════██║
██║  ██║███████║   ██║   ██║  ██║██║  ██║███████╗╚██████╔╝███████║
╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝                                                                  
</pre>


### Autonomous Scientific Tool for Research, Analysis, and Experimental Understanding of Space

---

## Overview

Project ASTRAEUS is a computational astrophysics and AI-assisted research initiative focused on modeling, analyzing, and interpreting astronomical data using first-principles physics.

The project aims to bridge the gap between theoretical astrophysics and real observational data by building reproducible, physics-driven computational pipelines.

---

## Mission

To develop a scientifically rigorous system that:
- Models astrophysical phenomena using first principles
- Analyzes real observational datasets (TESS, Kepler)
- Recovers physical parameters from noisy data
- Establishes reproducible workflows for early-stage research

---

## Primary Research Focus

**Exoplanet Transit & Orbital Analysis**

### Core Research Question
> How accurately can exoplanet transit parameters be recovered from noisy photometric data using first-principles modeling?

---

## Objectives

### Scientific
- Simulate exoplanet transits using orbital mechanics
- Analyze photometric light curves
- Recover key parameters such as:
  - Orbital period
  - Transit depth
  - Planet-to-star radius ratio

### Technical
- Build modular, reusable computational components
- Ensure reproducibility of all results
- Maintain clear documentation of assumptions and limitations

---

## Project Structure
astraeus/

- **core/** – Physics models (orbital mechanics, transit models)  
- **data/** – Data loading and preprocessing  
- **analysis/** – Parameter fitting and error analysis  
- **visualization/** – Plotting and result visualization  
- **notebooks/** – Experimental workflows and exploration  
- **logs/** – Research logs and notes  
- **main.py** – Entry point  


## Tech Stack

- Python
- NumPy
- SciPy
- Matplotlib
- Astropy

---

## Methodology

ASTRAEUS follows a physics-first, research-oriented workflow:

1. **Model Development**
   - Derive and implement physical models for orbital motion and transit geometry

2. **Synthetic Simulation**
   - Generate theoretical light curves under controlled conditions

3. **Data Integration**
   - Import and preprocess real observational data (e.g., TESS)

4. **Parameter Estimation**
   - Fit models to observed data using optimization techniques

5. **Validation**
   - Compare recovered parameters with known or reference values

6. **Analysis**
   - Evaluate error sources, noise impact, and model limitations

---

## Current Phase

**Phase 1: Foundational Modeling**

- Orbital mechanics implementation  
- Transit light curve simulation  
- Initial visualization tools  

---

## Roadmap

- [ ] Build orbital and transit simulation engine  
- [ ] Integrate real photometric datasets (TESS)  
- [ ] Implement parameter fitting algorithms  
- [ ] Perform error and sensitivity analysis  
- [ ] Produce research-grade report  

---

## Research Standards

This project adheres to the following principles:

- Physics-first reasoning (no black-box shortcuts)
- Explicit assumptions and limitations
- Reproducible results
- Transparent methodology

---

## Future Directions

- Bayesian parameter estimation (MCMC)
- Stellar variability modeling
- AI-assisted research workflows (RAG-based system)
- Multi-planet system analysis

---

## Author

Independent student researcher focused on:
- Astronomy & Astrophysics  
- Artificial Intelligence  
- Computational Science  

---

## Disclaimer

This is an ongoing research project.  
All models, results, and interpretations are subject to validation and refinement.

---
