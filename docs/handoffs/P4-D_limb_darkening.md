BUCKET: P4-D
STATUS: COMPLETE

PROVIDES:
- `astraeus/core/limb_darkening.py`: single source of truth —
  documented defaults (stellar fallback provenance + uniform-disk
  forward defaults), `validate_coefficients`, explicit `resolve()`.
- Forward model (`transit_model.py`) defaults reference the module
  constants (bit-identical 0.0); `constants.py` gains a marked
  re-export section only.
- `tests/test_p4d_limb_darkening.py` (16 tests).
- DEC-LIC honored: subtraction implementation frozen, untouched.

CONSUMED BY:
- P4-E (detrending window + trapezoid provenance)

MEASURED:
- New + transit-model + physics suites: 28 passed fresh.

FILES OF INTEREST:
- astraeus/core/limb_darkening.py
- astraeus/core/transit_model.py (defaults only)
- astraeus/core/constants.py (re-export section)
- tests/test_p4d_limb_darkening.py

KNOWN CONSTRAINTS:
- Zero numeric behavior change by construction + suite proof.
- Executed via subagent; validated on return.

NEXT REQUIRED ACTION:
- P4-E consumes the LD provenance (numbers unchanged).
