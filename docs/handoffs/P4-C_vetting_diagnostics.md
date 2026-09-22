BUCKET: P4-C
STATUS: COMPLETE

PROVIDES:
- Weighted χ² branch in `VettingEngine.vet_transit_shape` (optional
  `flux_err`; None → byte-identical legacy path). Bad sigmas fall back
  to the window median; shape mismatch raises ValueError.
- `odd_even_depth_test` (epoch-parity median depths, ratio, consistent
  flag at 0.30 rel-tol; degenerate inputs → consistent=False, never a
  silent pass) + `ephemeris_match` (harmonic-aware 1/2/0.5/3/1/3/4/0.25,
  empty list → match=None explicitly). Both also as staticmethod
  aliases; tolerances as module constants.
- `tests/test_p4c_vetting_diagnostics.py` (13 tests, ~5 s).

CONSUMED BY:
- Future wiring that threads `flux_err` from detection (not this bucket)

MEASURED:
- New + hardening suites together: 26 passed fresh.
- No existing default, threshold, verdict, or return shape changed
  (legacy χ² lines intact; `snr > 10.0` literal preserved).

FILES OF INTEREST:
- astraeus/analysis/vetting.py
- tests/test_p4c_vetting_diagnostics.py

KNOWN CONSTRAINTS:
- Diagnostics are available, not yet wired into the pipeline path —
  wiring is a separate gated change.
- Executed via subagent; validated on return per orchestrator gate.

NEXT REQUIRED ACTION:
- A wiring bucket may pass `flux_err` and consume the new diagnostics.
