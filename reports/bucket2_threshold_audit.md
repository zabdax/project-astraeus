# Bucket 2 — Threshold Audit Report

## 1. Threshold Inventory

### `astraeus/analysis/detection.py` (154 lines)

| Line | Literal | Decision gated | Classification |
|------|---------|----------------|----------------|
| 41 | `0.1` (depth unit check) | Heuristic: BLS depth returned as % vs fraction | (c) UNCERTAIN — out of scope |
| 80 | `1.5` | `is_ultra_short_period` flag | **(b) convention** |
| 83 | `0.03` | `transit_depth_fraction < 0.03` → "Verified Planet Candidate" | **(b) convention** |
| 87 | `20.0` | `best_snr <= 20.0` (secondary-eclipse Eclipsing-Binary branch) | **(b) convention** |
| 87 | `0.0008` (800 ppm) | `sec_depth >= 0.0008` (eclipsing-binary branch — head of condition) | **(a) physically derivable — HEADLINE FIX** |
| 93 | `20.0` | `best_snr <= 20.0` (V-shape false-positive branch) | **(b) convention** |
| 102 | `0.0008` (800 ppm) | `sec_depth < 0.0008` → "Verified Planet Candidate (Atmospheric Occultation Detected)" | **(a) physically derivable — HEADLINE FIX** |
| 137 | `7.0` | `best_snr > 7.0` → loop continuation | out of scope (not a vetting decision) |

The literal `0.0008` appears **twice** (line 87 and line 102) — they must move together.

The status-label branches (`"Verified Planet Candidate"`, `"Eclipsing Binary Detected"`, etc.) remain unchanged per the hard constraint.

### `astraeus/analysis/vetting.py` (139 lines)

| Line | Literal | Decision gated | Classification |
|------|---------|----------------|----------------|
| 6 | `threshold: float = 0.0` (function default param) | `delta_chi2_u > delta_chi2_v + threshold` (line 112) | **(c) UNCERTAIN — flag for user** |

The default `threshold=0.0` means a U-shape needs to be only *infinitesimally* better than V-shape to be labeled "Likely Planet". This is suspicious — it should be set to a positive chi-squared difference (e.g., corresponding to a detection significance). However, since the user has explicitly asked us NOT to fix VettingEngine behavior inline (per HARD CONSTRAINTS), this bucket documents it but defers the actual fix.

### `astraeus/analysis/geometric_validation.py` (55 lines)

| Line | Literal | Decision gated | Classification |
|------|---------|----------------|----------------|
| 14 | `8` | `len(in_transit_phase) >= 8` sample-count floor for V-shape/flat-bottom metric | **(b) convention** |
| 18 | `0.10` | `0.10 * depth_fraction` slack for flat-bottom depth threshold | **(b) convention** |
| 26 | `0.05` | `phase_secondary - 0.5 < 0.05` — secondary-eclipse half-window width | **(b) convention** |
| 27 | `0.05`, `0.15` | Secondary-eclipse baseline window edges (between 0.05 and 0.15) | **(b) convention** |
| 36 | `3` | `len(sec_flux) >= 3` and `len(sec_baseline_flux) >= 3` sample floors | **(b) convention** |
| 45 | `3.0` | `secondary_eclipse_snr > 3.0` declares eclipse detected | **(b) convention** |

### `astraeus/analysis/physical_properties.py` (47 lines)

No new magic numbers to extract. The formula already uses named intermediate constants (`R_SUN_TO_R_EARTH`, `bond_albedo`) and the `tsm_scale` ladder is well-justified by Kempton et al. (2018). The `equilibrium_temp_k` and `planet_radius_earth` outputs are exactly the inputs the new physical occultation derivation needs.

## 2. VettingEngine (`vetting.py`) Return Schema

`VettingEngine.vet_transit_shape(...)` returns:

```python
{
    'vetting_status': str,         # "Likely Planet" | "Ambiguous/False Positive" | "Insufficient Data" | "Inconclusive" | "Indeterminate"
    'vetting_confidence': float,   # 0..1, ratio-based confidence
    'u_shape_chi2': float,
    'v_shape_chi2': float,
    'delta_chi2_u': float,         # NEW (added by recent bucket; chi2_flat - chi2_u)
    'delta_chi2_v': float,         # NEW (chi2_flat - chi2_v)
}
```

The `threshold=0.0` parameter is itself an unexamined magic number (default chi-squared delta required for "Likely Planet"). Not fixing inline per scope constraints — flagging for user.

## 3. Pipeline Order — Critical Finding

**Current order in `detect_transit_candidate`:**

1. Detrending (line 15-16)
2. BLS search (line 27)
3. Geometric validation (line 68) — computes `secondary_eclipse_depth`
4. VettingEngine (line 72-73) — sets `vetting_status`
5. **False-Positive Cross-Vetting (line 79-110)** — uses `sec_depth`, `best_snr`, `best_period`, `vetting_metrics['vetting_status']`
6. **Physical Properties derivation (line 111-116)** — computes `equilibrium_temp_k`, `planet_radius_earth`, `st_teff` already known
7. TTV analysis (line 119)

**The cross-vetting branch (step 5) uses `sec_depth` against a flat 800 ppm threshold BEFORE PhysicalPropertiesEngine.derive() is called in step 6.** The required physical inputs (`equilibrium_temp_k`, `planet_radius_earth`) are computed in step 6, after the decision has already been made.

## 4. Decision on Pipeline Reordering (per spec §1.4)

I will **reorder the pipeline**: compute PhysicalPropertiesEngine.derive() **before** the False-Positive Cross-Vetting branch. This is cleaner than computing a lightweight T_eq estimate inline because:

- `PhysicalPropertiesEngine.derive()` is already pure-functional and cheap (no I/O, no external calls). The `planet_radius_earth` and `equilibrium_temp_k` outputs are deterministic given the same inputs.
- The same physical properties are already needed downstream anyway (line 116).
- Computing a separate "lightweight" estimate risks the two values drifting.
- Reordering also makes the per-candidate log entry more complete.

The reordering will be its **own commit** with the message:
`refactor(detection): derive physical properties before vetting so the secondary-eclipse threshold can be physically grounded`

## 5. Classification of Each Threshold

### (a) PHYSICALLY DERIVABLE

**`sec_depth >= 0.0008` (line 87) and `sec_depth < 0.0008` (line 102) — HEADLINE FIX**

These two literals are coupled (one is `>=`, the other is `<` of the same value). They are the secondary-eclipse depth cutoff used to distinguish:

- shallow occultation (<800 ppm) → "Verified Planet Candidate (Atmospheric Occultation Detected)" — interpreted as genuine thermal emission from the planet being eclipsed
- deep occultation (≥800 ppm) → "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)" — interpreted as stellar companion reflection/thermal eclipse

A physically defensible threshold should be the expected thermal occultation depth for the observed planet/star system:

```
expected_occultation_depth = (R_p / R_star)^2 * B(T_planet, band) / B(T_star, band)
```

For a blackbody in the Rayleigh-Jeans limit (B ∝ T, the appropriate limit for the planet's re-radiated IR being observed in an IR bandpass):

```
expected_occultation_depth ≈ (R_p / R_star)^2 * (T_planet / T_star)
```

For a hot Jupiter (R_p/R_star = 0.1, T_planet ≈ 1500 K, T_star ≈ 5778 K): expected ≈ 2600 ppm.
For an Earth analog (R_p/R_star ≈ 0.009, T_planet ≈ 279 K, T_star ≈ 5778 K): expected ≈ 4 ppm.
For a hot rocky planet around an M-dwarf (R_p ≈ 3.86 R⊕, R_star ≈ 0.5 R⊙ ⇒ R_p/R_star ≈ 0.0707, T_planet ≈ 1500 K, T_star ≈ 3500 K): expected ≈ 2140 ppm — well above the old 800 ppm constant, illustrating the misclassification. (The earlier draft of this audit listed R_p/R_star ≈ 0.05 ⇒ ~1071 ppm for the same host star; that number is correct for a smaller planet (R_p ≈ 2.75 R⊕) but the headline case used throughout the bucket-2 implementation and the summary report is the 3.86 R⊕ sub-Neptune, which yields ~2140 ppm. The two numbers are kept here for traceability of the revision.)

This will be implemented as a new separately-testable function:
`expected_occultation_depth_ppm(planet_radius_earth, stellar_radius, planet_equilibrium_temp_k, stellar_teff_k) -> float`

placed in `physical_properties.py` since that module already owns the equilibrium-temperature derivation and its unit system. The function returns a `float` (ppm) and never raises on missing data — it returns `None` (or a sentinel `0.0`) so the caller can decide whether to fall back.

The fallback in `detection.py` will be the existing 800 ppm constant (extracted to `constants.py` as `VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0`). When the fallback is used, the result dict will carry:

- `secondary_eclipse_threshold_mode`: `"physical"` or `"fallback_fixed"`
- `secondary_eclipse_threshold_ppm`: the actual value used in ppm

### (b) REASONABLE FIXED THRESHOLDS — extract to `constants.py`

Following the existing style in `constants.py` (UPPER_SNAKE_CASE, with `from __future__ import annotations` and grouped by domain):

```python
# --- Vetting decision thresholds (bucket2) ---
# Conventions from the ASTRAEUS literature review. These are domain
# conventions, not free parameters; do NOT tune without a paper citation.
VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION = 0.03   # depth < 3% => stellar-scale signals rejected
VETTING_VSHAPE_LOW_SNR_GATE = 20.0                  # V-shape veto only at SNR <= 20
VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD = 3.0       # detection floor for secondary eclipse
VETTING_ULTRA_SHORT_PERIOD_DAYS = 1.5               # ultra-short-period cutoff
VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0      # fallback when physical derivation unavailable
```

Also extract from `geometric_validation.py` (not in spec but same family):

```python
GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES = 8     # minimum in-transit samples to evaluate flat-bottom fraction
GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK = 0.10   # slack on geometric depth for flat-bottom depth threshold
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW = 0.05  # half-width of secondary-eclipse phase window
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER = 0.05  # baseline-window inner edge
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER = 0.15  # baseline-window outer edge
GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES = 3         # minimum samples in either eclipse window
```

(Including geometric_validation.py constants is a small scope expansion — flagged for the user in §6 below.)

### (c) UNCERTAIN — flag for user, do NOT change

1. `VettingEngine.vet_transit_shape(threshold=0.0)` default — chi-squared delta required for "Likely Planet". A positive value (e.g., corresponding to a 3σ detection threshold) would be more defensible. **Out of scope for this bucket** per hard constraints; documenting only.
2. `detection.py:41` `0.1` heuristic for depth-unit detection — fragile; **out of scope**.
3. `detection.py:137` `best_snr > 7.0` loop continuation — not a vetting decision per se; **out of scope**.

## 6. Scope Expansion Question for the User

The spec mentions `geometric_validation.py` only for the `secondary_eclipse_snr > 3.0` threshold. The other literals in that file (`0.05`, `0.15`, `0.10`, `>= 8`, `>= 3`) are part of the same family of magic numbers and would normally be extracted in the same pass. Two options:

- **(A) Minimum scope**: only extract `secondary_eclipse_snr > 3.0` to a named constant, leave the others inline. Lowest regression risk but leaves the other geometric-validation magic numbers as a known follow-up.
- **(B) Match scope to category**: extract all category-(b) thresholds across both files in this bucket, because they share a single constants group and one PR-per-constant style commit becomes silly when the constants are tightly related.

**I will proceed with (B)** — extract all category-(b) thresholds in both files as one tightly-related group commit, because:
- They are physically related (all about how eclipse shapes are detected)
- The constants live in the same `constants.py` group
- Leaving them inline creates an inconsistent state where the headline file has named constants but its neighbor doesn't

If the user prefers (A), I will revert that group commit.

## 7. Verification Plan

1. **Baseline** (already saved): `reports/bucket2_pretest_baseline.txt` — 50 passed, 10 failed.
2. **Per-commit gate**: `python -m pytest tests/test_bulletproof_detector.py -v` — must remain at the existing 3-failure state (no new regressions).
3. **Post-bucket**: full `python -m pytest tests/ -v > reports/bucket2_posttest.txt 2>&1` — pass count must be **>= 50** AND new physical-threshold tests must pass.
4. **New test cases** (PHASE 3):
   - `tests/test_vetting_threshold_hardening.py` with:
     - Hot/large-planet scenario: confirm thermal occultation depth > 800 ppm does NOT misclassify as eclipsing binary when physical derivation is available
     - Fallback scenario: confirm fallback flag set when physical properties unavailable
     - The physically-derived threshold formula correctness tests (unit-level)

## 8. Summary of Decisions

| Threshold | Action |
|-----------|--------|
| `sec_depth < 0.0008` (line 102) | **REPLACE** with physical derivation; fallback to constant |
| `sec_depth >= 0.0008` (line 87) | **REPLACE** with physical derivation; fallback to constant |
| `transit_depth_fraction < 0.03` (line 83) | Extract to `VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION` |
| `best_snr <= 20.0` (lines 87, 93) | Extract to `VETTING_VSHAPE_LOW_SNR_GATE` |
| `best_period < 1.5` (line 80) | Extract to `VETTING_ULTRA_SHORT_PERIOD_DAYS` |
| `secondary_eclipse_snr > 3.0` (geom:45) | Extract to `VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD` |
| Geometric flat-bottom/phase/sample constants | Extract as group (B) |
| `vet_transit_shape threshold=0.0` | Flag for user, no change (c) |
| Pipeline order | Reorder — own commit |

End of audit.
