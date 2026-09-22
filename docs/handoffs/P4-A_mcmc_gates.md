BUCKET: P4-A
STATUS: COMPLETE

PROVIDES:
- MCMC convergence gates (`astraeus/analysis/error_analysis.py`):
  `_assess_convergence` (acceptance band + autocorr effective size →
  `converged` + `reasons`) and opt-in `run_mcmc` surface
  (`return_convergence` appends the report; `require_converged`
  raises `MCMCConvergenceError` instead of returning silently).
  Legacy tuples byte-identical when flags are off.
- Named thresholds in `core/constants.py` (`MCMC_ACCEPTANCE_MIN/MAX`,
  `MCMC_MIN_EFFECTIVE_SAMPLES`, `MCMC_BURNIN_FRACTION`).
- `tests/test_p4a_mcmc_gates.py`: seeded report-shape, fail-closed
  enforcement, legacy-shape, and pure-logic tests.
- Versioned scientific change: package `0.0.2 → 0.0.3`.

CONSUMED BY:
- P4-F (inference wiring gates on these verdicts)

MEASURED:
- Seeded mock config: acc 0.545 (outside band), tau ~[51,54] over
  400 post-burnin steps → effective ~7 < 50. Unconverged on both
  gates — the warning the suite carried for months is now a verdict.

FILES OF INTEREST:
- astraeus/analysis/error_analysis.py
- astraeus/core/constants.py (MCMC section)
- astraeus/__init__.py (version)
- tests/test_p4a_mcmc_gates.py

KNOWN CONSTRAINTS:
- Enforcement is opt-in per call (`require_converged`); default path
  preserves legacy behavior for one release (Phase 4 flag rule).
- `test_mcmc.py` untouched and green (old path available).

NEXT REQUIRED ACTION:
- P4-F may gate Candidate→MCMC on these verdicts.
