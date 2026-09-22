BUCKET: P4-B
STATUS: COMPLETE

PROVIDES:
- `astraeus/analysis/fap_calibration.py`: seeded noise/signal BLS
  confidence runners, empirical FAP mapping, efficiency-vs-threshold,
  `recommend_floor()` → (value, rationale). Measurement only — the
  operational floor is untouched and nothing is wired into the gate.
- `tests/test_p4b_fap_calibration.py`: determinism, monotonicity,
  floor-in-gap (3 passed, ~30 s).
- `reports/fap_calibration.md` (force-added: `reports/` is otherwise
  ignored): method, FAP/efficiency table, Kepler_4d real-slice
  cross-check, synthetic-only limitations stated.

MEASURED (20 noise seed 71001, 8 signals seed 72001):
- noise max 2.895 / signal min 9.042 / recommended 5.969.
- Operational 7.0 lies in the same gap: unchanged, now evidenced.
- Kepler_4d slice: conf 80.2, period 3.212 d vs archive 3.2136 d.

FILES OF INTEREST:
- astraeus/analysis/fap_calibration.py
- tests/test_p4b_fap_calibration.py
- reports/fap_calibration.md

KNOWN CONSTRAINTS:
- Calibration fixtures are synthetic (30 d / 1200 cadence); the
  real-curve cross-check is one slice, not a survey.
- Any floor change is a separate gated decision, not this bucket.

NEXT REQUIRED ACTION:
- A future bucket may adopt the calibrated floor behind a flag.
