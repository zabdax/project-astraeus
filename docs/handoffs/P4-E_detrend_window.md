BUCKET: P4-E
STATUS: COMPLETE

PROVIDES:
- `window_for_duration()` in `detrending.py`: the transit-preserving
  window as a documented function of duration, clamped to the legacy
  0.5/1.5 d bounds — arithmetic identical to the old inline clamp
  (proven bit-for-bit vs legacy oracles across durations).
- `detrend_report()` → exactly `{method, window_days, window_source}`
  with six documented `WINDOW_SOURCE_*` labels; `detrend()` /
  `detrend_with_method()` tuple shapes and method strings frozen.
- `tests/test_p4e_detrend_window.py` (49 tests, ~20 s).
- DEC-LIC honored: subtraction implementation frozen, untouched.

CONSUMED BY:
- Any consumer that needs window provenance (none required yet)

MEASURED:
- New suite 49 passed fresh; preprocessing + observability 15 passed.
- `test_solid_matrix_diagnostic` timeout is network-marked
  (network+slow, excluded from gates) and unrelated.

FILES OF INTEREST:
- astraeus/analysis/detrending.py
- tests/test_p4e_detrend_window.py

KNOWN CONSTRAINTS:
- Zero numeric change by oracle proof, not assertion.
- Executed via subagent; validated on return.

NEXT REQUIRED ACTION:
- P4-F (inference wiring) is the remaining code bucket; P4-G needs Linux.
