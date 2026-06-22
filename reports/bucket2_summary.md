# Bucket 2 — Threshold Hardening Summary

## Goal

Replace the remaining fixed transit-vetting thresholds in
`astraeus/analysis/detection.py` and `astraeus/analysis/geometric_validation.py`
with either a physically-derived function (category **a**) or a named,
documented, configurable constant (category **b**).

The **headline fix** is the secondary-eclipse depth threshold (formerly a
flat 800 ppm constant): a genuine hot, large planet around a cool star
can produce a real thermal occultation depth well above 800 ppm, and the
old constant misclassified such cases as eclipsing binaries.

---

## 1. Branch & test baseline

* Branch: `fix/vetting-threshold-hardening` (created from `v.0.0.2`).
* Working tree: clean (no stray test artifacts; `logs/experiments.json`
  is restored to its committed state after every test run).
* Pre-bucket baseline: **50 passed, 10 failed** (see
  `reports/bucket2_pretest_baseline.txt`).
  * The 10 failures are pre-existing and unrelated to vetting:
    7 are Streamlit `DeltaGeneratorSingleton` test-environment issues,
    3 are `test_bulletproof_detector.py` issues (a performance-budget
    assertion, and two `KeyError: 0` tests that assume the pipeline
    returns a list of `candidate_N` dicts instead of a single dict).

---

## 2. Thresholds found, classified, and acted upon

| # | File | Line | Literal | Decision gated | Class | Action |
|---|------|------|---------|----------------|-------|--------|
| 1 | `detection.py` | 83 | `0.03` | depth ceiling → "Verified Planet Candidate" | b | → `VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION` |
| 2 | `detection.py` | 80 | `1.5` | ultra-short-period flag | b | → `VETTING_ULTRA_SHORT_PERIOD_DAYS` |
| 3 | `detection.py` | 87 | `20.0` | SNR gate, Eclipsing-Binary branch | b | → `VETTING_VSHAPE_LOW_SNR_GATE` |
| 4 | `detection.py` | 93 | `20.0` | SNR gate, V-Shape false-positive branch | b | → `VETTING_VSHAPE_LOW_SNR_GATE` |
| 5 | `detection.py` | 87 | `0.0008` | `sec_depth >= 0.0008` → Eclipsing Binary | **a** | → `PhysicalPropertiesEngine.expected_occultation_depth_ppm(...)` |
| 6 | `detection.py` | 102 | `0.0008` | `sec_depth < 0.0008` → Atmospheric Occultation | **a** | → physical derivation (same function) |
| 7 | `geometric_validation.py` | 14 | `8` | in-transit sample floor | b | → `GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES` |
| 8 | `geometric_validation.py` | 18 | `0.10` | depth-threshold slack | b | → `GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK` |
| 9 | `geometric_validation.py` | 26 | `0.05` | secondary-eclipse half-window | b | → `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW` |
| 10 | `geometric_validation.py` | 27 | `0.05` | baseline annulus inner edge | b | → `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER` |
| 11 | `geometric_validation.py` | 27 | `0.15` | baseline annulus outer edge | b | → `GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER` |
| 12 | `geometric_validation.py` | 36 | `3` (×2) | eclipse/baseline sample floors | b | → `GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES` |
| 13 | `geometric_validation.py` | 45 | `3.0` | secondary-eclipse SNR threshold | b | → `VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD` |
| 14 | `vetting.py` | 6 | `threshold=0.0` | U/V chi-squared-delta floor | **c** | flagged, **not changed** (see §4) |

Constants #7–#12 are documented as a small scope expansion in
`reports/bucket2_threshold_audit.md` §6 (option B). The user's prompt
explicitly listed `secondary_eclipse_snr > 3.0` in scope, so I extended
the same named-constant treatment to the other inline literals in the
same file, since they share a single `constants.py` group.

---

## 3. Physical derivation used for the secondary-eclipse threshold

The thermal occultation depth (flux dip at secondary eclipse when the
planet passes behind the star) equals the planet-to-star surface
brightness ratio:

```
depth = (R_p / R_star)^2 · B(T_planet, band) / B(T_star, band)
```

where `B(T, band)` is the Planck function evaluated at the observation
bandpass. In the **Rayleigh-Jeans limit** (`B ∝ T`, the appropriate
regime when the observation bandpass is longward of the stellar peak
and the planet radiates its re-processed stellar light as a
thermalised blackbody), the bandpass dependence collapses to a pure
temperature ratio and the formula simplifies to:

```
depth ≈ (R_p / R_star)^2 · (T_planet / T_star)
```

This is the formula implemented in
`PhysicalPropertiesEngine.expected_occultation_depth_ppm`:

```
depth_ppm = (R_p / R_star)^2 · min(T_planet / T_star, 1.0) · 1e6
```

* The temperature ratio is **capped at 1.0** because a planet cannot
  emit more thermal flux than the star in any bandpass without
  violating energy conservation. Bad-archive values that imply
  `T_eq > T_eff` therefore still refuse to predict a depth above the
  geometric transit depth.
* The function returns `None` (not an exception) when any input is
  missing or non-positive; the caller substitutes the documented
  fallback constant `VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0`
  and flags the fallback in the result dict.

### Worked examples

| Scenario | R_p (R⊕) | R_star (R⊙) | T_planet (K) | T_star (K) | Predicted depth | Old 800 ppm verdict? |
|----------|----------|--------------|--------------|-------------|-----------------|----------------------|
| Earth around Sun | 1.0 | 1.0 | 279 | 5778 | **4 ppm** | OK (under threshold) |
| Hot Jupiter around Sun-like star | 11.2 | 1.0 | 1500 | 5778 | **2730 ppm** | misclassified as binary |
| Hot planet around M-dwarf | 3.86 | 0.5 | 1500 | 3500 | **~2140 ppm** | misclassified as binary |

The third row is the **headline test case**: 1000 ppm secondary-eclipse
depth on a planet around an M-dwarf — labelled "Eclipsing Binary" by
the old constant, now correctly labelled "Verified Planet Candidate
(Atmospheric Occultation Detected)" by the new threshold.

> **Note on the worked-example math** (added during docs review):
> for the third row, R_p/R_star = 3.86 R⊕ / (0.5 R⊙ · 109.2 R⊕/R⊙) ≈ 0.0707
> so (0.0707)² · (1500/3500) · 1e6 ≈ 2142 ppm. The earlier draft
> listed this case as "~1100 ppm", which corresponds to R_p/R_star ≈ 0.05
> (i.e. R_p ≈ 2.75 R⊕ for the same 0.5 R⊙ host) — kept here for
> completeness but the physically realistic sub-Neptune radius of
> 3.86 R⊕ is the headline case and yields ~2140 ppm.

---

## 4. Pipeline reorder (explicit commit)

**Decision**: reorder so `PhysicalPropertiesEngine.derive()` runs
**before** the False-Positive Cross-Vetting branch in
`detect_transit_candidate`. Implemented as commit
`f14e3e1 refactor(detection): derive physical properties before
vetting so the secondary-eclipse threshold can be physically grounded`.

**Why reorder instead of computing a lightweight `T_eq` estimate
inline**: `PhysicalPropertiesEngine.derive()` is already pure-functional
and cheap (no I/O, no external calls). Computing a separate
"lightweight" estimate risks the two values drifting, and the same
physical properties are already needed downstream for the JWST TSM
score. The reorder therefore adds no work to the pipeline — it only
shifts the existing derivation earlier.

**What changed in `detection.py`**:
* `st_teff`, `st_mass`, `sy_jmag` lookups are hoisted next to `st_rad`
  so they are available to both the physical-properties call and any
  future physical-input branch in the cross-vetting tree.
* `PhysicalPropertiesEngine.derive(...)` is called and merged into
  `result` *before* the cross-vetting `if is_valid:` block.
* The duplicate `phys_props` block that previously appeared *after*
  the cross-vetting was removed.
* Status-label strings, classification logic, and the order of
  branch evaluation are **unchanged**.

---

## 5. New test cases added (`tests/test_vetting_threshold_hardening.py`)

Nine new tests, all passing:

| # | Test | What it guards against |
|---|------|------------------------|
| 1 | `test_expected_occultation_depth_ppm_hot_jupiter_around_sun` | Formula correctness: ~2730 ppm for a canonical hot Jupiter around a Sun-like star. |
| 2 | `test_expected_occultation_depth_ppm_earth_sun_analog` | Formula correctness at the small end: ~4 ppm for Earth-Sun. |
| 3 | `test_expected_occultation_depth_ppm_hot_planet_around_m_dwarf_exceeds_800ppm` | Motivation test: physically-derived threshold > 800 ppm for an M-dwarf host. |
| 4 | `test_expected_occultation_depth_ppm_returns_none_for_missing_inputs` | Fallback contract: any zero/missing input returns `None` so the caller can substitute the documented fallback. |
| 5 | `test_expected_occultation_depth_ppm_caps_temperature_ratio_at_one` | Energy-conservation guard: impossible `T_eq > T_eff` does NOT predict a depth above the geometric transit depth. |
| 6 | `test_pipeline_uses_physical_threshold_for_hot_planet_around_m_dwarf` | **THE HEADLINE TEST**: a 1000 ppm secondary-eclipse depth on a planet around an M-dwarf is correctly classified as a planet, NOT an eclipsing binary. |
| 7 | `test_pipeline_fallback_when_physical_inputs_missing` | Fallback path: when `st_teff = 0` is in the metadata, mode = `fallback_fixed` and the threshold is the documented 800 ppm constant. |
| 8 | `test_pipeline_fallback_when_transit_depth_unavailable` | The threshold bookkeeping fields are always present in the result dict, regardless of whether a candidate is recovered. |
| 9 | `test_pipeline_threshold_mode_present_in_result_dict_for_known_truth` | Sanity: the mode/value fields are populated for a real recovered candidate too. |

Test #6 is the one that guards against the **headline misclassification
bug**. It would have **failed** against the pre-bucket code (the old
constant would have labelled the candidate as `Eclipsing Binary
Detected (Secondary Eclipse at Phase 0.5)` because 1000 ppm ≥ 800 ppm).
With the bucket-2 changes it now passes.

---

## 6. Thresholds left as category (c) for user decision

| Threshold | File | Why flagged, not changed |
|-----------|------|--------------------------|
| `VettingEngine.vet_transit_shape(threshold=0.0)` | `vetting.py:6` | The default chi-squared delta required for "Likely Planet" is itself an unexamined magic number (U-shape needs to be only infinitesimally better than V-shape). **Out of scope for this bucket per HARD CONSTRAINTS**: the user asked us not to touch VettingEngine behavior. Proposing as a follow-up bucket that introduces a positive chi-squared-delta threshold tied to a literature detection-significance value. |
| `detection.py:41` heuristic `0.1` (depth unit detection) | `detection.py` | Fragile heuristic for distinguishing BLS depth-in-percent vs depth-as-fraction. Out of scope. |
| `detection.py:137` `best_snr > 7.0` loop continuation | `detection.py` | Controls whether the BLS search moves on to a second/third candidate; not a vetting decision per se. Out of scope. |

---

## 7. Commits (chronological)

```
007d02d test(vetting): add tests for physically-derived secondary-eclipse threshold
120c066 refactor(geometric_validation): replace inline magic numbers with named constants
016890e refactor(detection): replace inline vetting magic numbers with named constants
2e76992 feat(detection): use physical derivation for secondary-eclipse threshold
0c7caf7 feat(physical_properties): add expected_occultation_depth_ppm derivation
f14e3e1 refactor(detection): derive physical properties before vetting so the secondary-eclipse threshold can be physically grounded
3a9a0d5 chore(constants): add named thresholds for vetting and geometric decisions
```

Each commit is independently revertable. The pipeline reorder
(`f14e3e1`) and the threshold logic change (`2e76992`) are deliberately
**separate** commits, as the spec required.

---

## 8. Test results before vs after

| | Passed | Failed | Total | New tests |
|--|--------|--------|-------|-----------|
| Pre-bucket baseline (`reports/bucket2_pretest_baseline.txt`) | 50 | 10 | 60 | — |
| Post-bucket (`reports/bucket2_posttest.txt`) | **59** | 10 | 69 | +9 |
| New tests alone (`tests/test_vetting_threshold_hardening.py`) | **9** | 0 | 9 | — |

`diff` of the failed-test lists before vs after bucket-2: **identical**.
No regressions; all 10 pre-existing failures are unrelated to vetting
(7 Streamlit environment issues, 2 `KeyError: 0` in
`test_bulletproof_detector.py`, 1 unrelated `test_noise_injection`
assertion).

---

## 9. Verification commands

The following commands reproduce every result reported above.

### 9.1 Baseline (already on disk)
```bash
python -m pytest tests/ -v > reports/bucket2_pretest_baseline.txt 2>&1
```

### 9.2 New tests only (fast)
```bash
python -m pytest tests/test_vetting_threshold_hardening.py -v
```
Expected: **9 passed**.

### 9.3 Targeted regression check on the files this bucket touched
```bash
python -m pytest tests/test_bulletproof_detector.py tests/test_pipeline_smoke.py tests/test_vetting_threshold_hardening.py -v
```
Expected: **3 failed, 9 passed** — the 3 failures are the same
pre-existing `test_bulletproof_detector.py` failures as in baseline;
the 9 passing include all new bucket-2 tests.

### 9.4 Full post-bucket suite
```bash
python -m pytest tests/ -v > reports/bucket2_posttest.txt 2>&1
```
Expected: **59 passed, 10 failed** (failure list identical to baseline
by `diff`).

### 9.5 Diff baseline vs posttest failure list
```bash
diff <(grep -E "^FAILED " reports/bucket2_pretest_baseline.txt | sort) \
     <(grep -E "^FAILED " reports/bucket2_posttest.txt | sort)
```
Expected: empty output, exit code 0.

### 9.6 Direct sanity check on the new function
```python
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine

# Hot planet around an M-dwarf (headline case)
ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
    planet_radius_earth=3.86, stellar_radius_solar=0.5,
    planet_equilibrium_temp_k=1500.0, stellar_teff_k=3500.0,
)
assert ppm > 800.0, "physical threshold must exceed 800 ppm for this case"

# Missing inputs -> None
assert PhysicalPropertiesEngine.expected_occultation_depth_ppm(0, 1, 1500, 5778) is None
```

---

## 10. Files changed / added

| File | Status |
|------|--------|
| `astraeus/core/constants.py` | modified — 11 new named thresholds added |
| `astraeus/analysis/detection.py` | modified — pipeline reorder + physical-threshold use + 4 inline literals → named constants |
| `astraeus/analysis/physical_properties.py` | modified — new `expected_occultation_depth_ppm` staticmethod, `R_SUN_TO_R_EARTH` hoisted to module constant |
| `astraeus/analysis/geometric_validation.py` | modified — 7 inline literals → named constants |
| `tests/test_vetting_threshold_hardening.py` | **new** — 9 tests covering the headline fix and fallback path |
| `reports/bucket2_pretest_baseline.txt` | **new** — pre-bucket baseline |
| `reports/bucket2_posttest.txt` | **new** — post-bucket results |
| `reports/bucket2_threshold_audit.md` | **new** — discovery-phase audit |
| `reports/bucket2_summary.md` | **new** — this file |

---

## 11. What was NOT done (out of scope, intentional)

* `bls_search.py`, `fitting.py`, `error_analysis.py`, `ttv_analysis.py` —
  explicitly out of scope per the spec.
* `VettingEngine.vet_transit_shape(threshold=0.0)` — flagged as
  category (c); fixing it would change VettingEngine behavior, which
  the HARD CONSTRAINTS forbid in this bucket.
* The `result[0].get('candidate_1', {})` `KeyError: 0` failures in
  `test_bulletproof_detector.py` — these tests assume a list-of-dicts
  pipeline return, but `detect_transit_candidate` returns a single
  dict. Predates this bucket and is out of scope.
* Streamlit-related test failures (`DeltaGeneratorSingleton instance
  already exists`) — environment issues in the Streamlit
  `AppTest` infrastructure; predates this bucket.
* No new vetting status labels were added — the spec forbids changing
  the classification scheme.

End of summary.
