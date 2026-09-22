---
title: 'ASTRAEUS: A physics-first platform for exoplanet transit discovery, vetting, and retrieval'
tags:
  - Python
  - exoplanets
  - transits
  - photometry
  - astronomy
authors:
  - name: Zubayer Hasan Shaad
    affiliation: Independent researcher
date: 22 September 2026
bibliography: paper.bib
---

# Summary

`ASTRAEUS` bridges theoretical orbital mechanics and space-telescope
photometry: raw light curves (Kepler, K2, TESS, or CSV upload) flow
through detrending, Box Least Squares search cross-validated by
Transit Least Squares, geometric and U/V-shape vetting, physical
property derivation, transit-timing-variation analysis, and MCMC
posterior sampling with convergence gates — behind a FastAPI service
and a Next.js interface, with every result carrying machine-readable
provenance.

# Statement of need

Transit pipelines commonly fail open: missing optional dependencies
silently substitute estimators, vetting overrides bypass validation
gates, and "no candidates" is indistinguishable from a broken run.
ASTRAEUS is built fail-closed — a missing backend is a `FAILED` job
with a reason, verdicts carry epistemic labels (measured / derived /
inferred / AI-interpreted), and no quantity the engine does not
compute (e.g. "planet probability") is ever displayed.

# State of the field

Existing tools (`lightkurve`, `transitleastsquares`, `wotan`,
`emcee`) supply excellent primitives; ASTRAEUS composes them into a
reproducible end-to-end system with durable jobs, content-addressed
datasets, and honest uncertainty propagation.

# References

See `paper.bib`. JOSS review checklist started; submission follows a
public release with the validation corpus (Phase 5) green.
