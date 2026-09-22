BUCKET: P4-F
STATUS: COMPLETE

PROVIDES:
- `astraeus/analysis/inference.py`: `kepler_semi_major_axis_au`,
  `candidate_to_mcmc_config` (legacy-dict + attribute candidates,
  alias-tolerant), `run_candidate_inference` (fold + retrieve).
  Period/epoch/depth from the candidate; `a` from Kepler III +
  stellar mass; rp/rs from depth; u1/u2 from the P4-D source;
  circular + edge-on assumptions stated, not hidden.
- `mcmc_retrieval.py`: additive `seed`/`require_converged`/
  `min_effective` config plumbing into `run_mcmc` + `convergence`
  report on the result. Legacy constructions/returns preserved.
- `tests/test_p4f_inference_wiring.py` (7 tests).
- `AnalysisResult.inference` stays null (v1 contract frozen).

CONSUMED BY:
- Any caller ready to run inference on a detected candidate

MEASURED:
- New suite 7 passed fresh (incl. real seeded sampler run).
- No existing test consumes run_retrieval; UI reads fields additively.

FILES OF INTEREST:
- astraeus/analysis/inference.py
- astraeus/dashboard/services/mcmc_retrieval.py
- tests/test_p4f_inference_wiring.py

KNOWN CONSTRAINTS:
- Eccentricity/inclination are assumed (unmeasured by the search);
  assumptions documented at the call site.

NEXT REQUIRED ACTION:
- P4-G (TLS unlock) needs a Linux re-measure; nothing else is code.
