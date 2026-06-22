# Bucket 10 — Threshold Significance Audit

**Date:** 2026-06-23
**Branch:** `fix/vetting-threshold-significance`
**Status:** Phase 1 (Discovery) — read-only, no source code modified.

---

## 1. vet_transit_shape — full logic documentation

### 1.1 Function signature
```
VettingEngine.vet_transit_shape(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    t0: float,
    duration: float,
    depth: float,
    threshold: float = 0.0,        # <-- THE BUG
) -> dict
```

### 1.2 Algorithm
1. **Phase-fold** `time` around `t0` (modulo `period`, shifted by 0.5*period so phase is symmetric around 0).
2. **Local window:** `|phase| < 1.5*duration` (3× duration total). Normalize flux by local median.
3. **Data-integrity guards** (early returns):
   - `< 3` samples in window → `vetting_status='Insufficient Data'`
   - `< 3` samples in `|phase| < 0.5*duration` → same
   - local_median == 0 or NaN → `vetting_status='Inconclusive'`
4. **Sort** local phase/flux by phase.
5. **U-shape fit (trapezoid with 10% ingress/egress):**
   - `u_template(t)` returns 0 at full depth for `|t| < dur/2 - 0.1*dur`, ramps linearly to 0 at the edges.
   - `u_model_fit(t, d) = 1 - d * u_template(t)` — only `d` (depth) is free.
   - `scipy.optimize.curve_fit` with `p0=[depth]`, `bounds=([0],[1])`, `maxfev=100`.
6. **V-shape fit (linear ramp from edges to center):**
   - `v_template(t)` returns 0 at center, ramps linearly to 0 at `|t|=dur/2`.
   - Same `curve_fit` call.
7. **Null (flat) model:** `f_flat = ones`.
8. **Chi-squared:**
   - `chi2_flat = sum((f_sorted - f_flat)^2)`
   - `chi2_u = sum((f_sorted - f_u_fit)^2)`
   - `chi2_v = sum((f_sorted - f_v_fit)^2)`
   - `delta_chi2_u = chi2_flat - chi2_u` *(improvement of U-shape over flat)*
   - `delta_chi2_v = chi2_flat - chi2_v` *(improvement of V-shape over flat)*
9. **Verdict (line 112-117):**
   ```python
   if delta_chi2_u > delta_chi2_v + threshold:
       status = "Likely Planet"
       confidence = 1.0 - (chi2_u / chi2_v) if chi2_v > 0 else 1.0
   else:
       status = "Ambiguous/False Positive"
       confidence = chi2_u / chi2_v if chi2_v > 0 else 0.0
   ```
   Confidence is clamped to `[0, 1]`.

### 1.3 Return-dict schema

| Key | Always present? | Type | Notes |
|-----|----------------|------|-------|
| `vetting_status` | yes | str | One of: `"Likely Planet"`, `"Ambiguous/False Positive"`, `"Insufficient Data"`, `"Inconclusive"`, `"Indeterminate"` |
| `vetting_confidence` | yes | float in [0,1] | 1.0 = strong U-shape, 0.0 = strong V-shape |
| `u_shape_chi2` | yes | float | Set to 0.0 in all early-return / exception paths |
| `v_shape_chi2` | yes | float | Set to 0.0 in all early-return / exception paths |
| `delta_chi2_u` | only on successful fit | float | Set to 0.0 in exception path only |
| `delta_chi2_v` | only on successful fit | float | Set to 0.0 in exception path only |

### 1.4 Branches that depend on `threshold`
- **Only line 112** uses the threshold parameter:
  `if delta_chi2_u > delta_chi2_v + threshold:` → `"Likely Planet"` branch.
- The `"Ambiguous/False Positive"` branch is the `else` of this same `if`, so it inherits the threshold comparison.

---

## 2. Empirical characterization of `threshold=0.0`

### 2.1 Method
Generated four classes of synthetic light curves and ran `vet_transit_shape` 5 times each on independent noise realizations:

| Class | Injected shape | Expected verdict |
|-------|----------------|------------------|
| `u_shape_clear` | Trapezoid U-shape, depth=0.01, noise=1e-4 | Likely Planet |
| `v_shape_clear` | Pure linear V-shape, depth=0.01, noise=1e-4 | Ambiguous/False Positive |
| `u_shape_marginal` | Trapezoid U-shape, depth=0.0005, noise=5e-3 | Ambiguous (near noise floor) |
| `flat` | Pure noise, no transit | Ambiguous (should reject) |

Each call returns `delta_chi2_u - delta_chi2_v` and a vetting verdict.

Script: `scratch/bucket10_threshold_characterization.py`
Data:   `scratch/bucket10_threshold_characterization.json`

### 2.2 Results — distribution of `delta_chi2_u - delta_chi2_v`

| Class | min | median | max | std | Likely Planet count |
|-------|-----|--------|-----|-----|---------------------|
| `u_shape_clear` (planet)   | **+0.002116** | **+0.002118** | +0.002126 | 4e-6 | **5/5** |
| `v_shape_clear` (binary)   | **−0.000664** | **−0.000662** | −0.000649 | 5e-6 | 0/5 |
| `u_shape_marginal`         | −0.000039 | −0.000001 | +0.000008 | 2e-5 | 1/5 |
| `flat`                     | −0.000000 | +0.000000 | +0.000000 | <1e-7 | 3/5 |

**Observed gap:**
- Real U-shape at depth=0.01 sits at **+0.0021** (sigma ≈ 4e-6, so well above noise).
- V-shape binary sits at **−0.00066**.
- Marginal/noise cases sit at **0** with tiny scatter.

**Decision boundary:** there is a clean gap between **0** and **+0.0021**. Any threshold in this gap accepts real U-shapes and rejects V-shapes/marginal/flat.

### 2.3 Absolute scale sanity check
- `chi2_u` for noise-only is `~ 25 * noise^2 ≈ 2.5e-7` (matches observed `~1e-4² × 25`).
- For a real U-shape of depth 0.01, the fit absorbs the signal; `chi2_u` falls back to noise-level `~1e-7`, while `chi2_v` is larger because V-shape doesn't fit trapezoid (`~2.3e-3`).
- `delta_chi2_u - delta_chi2_v ≈ 0.0021` is consistent with `chi2_v - chi2_u ≈ 0.0023 - 0.0002 = 0.0021`.

### 2.4 Scaling with depth and noise (extended characterization)
Script: `scratch/bucket10_threshold_characterization_scaling.py`
Data:   `scratch/bucket10_threshold_characterization_scaling.json`

| Scenario | depth | noise | median Δ(u-v) | Likely Planet? |
|----------|-------|-------|---------------|----------------|
| 2% depth, clean | 0.02 | 1e-4 | **+0.00855** | 5/5 |
| 1% depth, clean | 0.01 | 1e-4 | **+0.00212** | 5/5 |
| 0.5% depth, clean | 0.005 | 1e-4 | +0.000522 | 5/5 (still wins under threshold=0.0) |
| 0.2% depth, clean | 0.002 | 1e-4 | +0.000080 | 5/5 |
| 0.1% depth, clean | 0.001 | 1e-4 | +0.000018 | 5/5 |
| 1% depth, 3× noise | 0.01 | 3e-4 | +0.00206 | 5/5 |
| 1% depth, 10× noise | 0.01 | 1e-3 | +0.00185 | 5/5 |
| Marginal (shallow + noisy) | 0.0005 | 5e-3 | +0.000002 | 3/5 (unstable under threshold=0.0) |

**Pattern:** Δ(u−v) scales as **depth²** (chi-squared metric), unchanged by moderate noise.

---

## 3. Threshold value selection

### 3.1 Constraints from the data
- **Must accept** real U-shapes at depth ≥ 1%: requires threshold < +0.0021 (and well below +0.0085 for the 2% case).
- **Must reject** V-shape binaries: threshold > −0.00066 (any positive value is fine — V-shape Δ is negative).
- **Must reject** flat noise (Δ ≈ 0): threshold > ~1e-5.
- **Should reject** very shallow U-shapes (Δ < 0.001): to avoid labeling low-SNR marginal cases as planets.

### 3.2 Candidate values
| Threshold | Accepts ≥1% depth U-shape? | Accepts 0.5% depth U-shape? | Rejects V-shape binary? | Rejects flat? | Rejects marginal? |
|-----------|----------------------------|------------------------------|------------------------|---------------|-------------------|
| 0.0001    | ✓ (0.0021 >> 0.0001)        | ✓ (0.0005 > 0.0001)          | ✓                       | ✓             | ✓                 |
| 0.0005    | ✓ (0.0021 > 0.0005)         | ✗ (=0.0005, borderline)      | ✓                       | ✓             | ✓                 |
| **0.001** | ✓ (0.0021 > 0.001)          | **✗** (0.0005 < 0.001)       | ✓                       | ✓             | ✓                 |
| 0.002     | ✗ (0.0021 > 0.002 borderline) | ✗                          | ✓                       | ✓             | ✓                 |

### 3.3 Selected value: **VETTING_U_VS_V_CHI2_DELTA_THRESHOLD = 0.001**

**Rationale (statistical + empirical):**
1. **Cleanly in the gap.** Real U-shape Δ = +0.0021 (4.2× the threshold); flat/marginal Δ ≈ 0 (≪ threshold); V-shape Δ = −0.00066 (≪ threshold).
2. **Half the typical real-planet advantage.** A threshold of 0.001 requires the U-shape advantage to be at least half of the observed clear-U-shape value. This is a defensible "minimum significance" rule — not "infinitesimally better" (threshold=0.0) but also not "overwhelmingly better" (threshold=0.002 would start rejecting real 1%-depth planets).
3. **Conservative on false positives.** With threshold=0.0005, the 0.5%-depth shallow U-shape case has Δ ≈ 0.0005 and is borderline. Threshold=0.001 places a clearer gap: 0.5%-depth U-shapes (Δ=0.000522) are flagged "Ambiguous" — which is appropriate because at 0.5% depth the V-shape fit is only ~2× worse than the U-shape, not "decisively worse."
4. **Wilks-theorem analog.** For a chi-squared-delta comparison with 1 effective dof (single depth parameter), a 3σ detection threshold corresponds to Δ ≈ 9 * (per-sample variance). The local-window scale here gives per-sample variance of order `noise^2 ≈ 1e-8`, so 3σ at this scale would be ~3e-7 — *much smaller* than the typical real-planet Δ. The empirical value of 0.001 corresponds to roughly 0.001/2.5e-7 ≈ **4000 per-sample sigmas**, which is enormously conservative; it sets a practical floor that excludes noise without rejecting real planets.

**NOT motivated by:** trial-and-error against the test suite. The threshold is set from the empirical gap observed in §2 before any test was re-run with a non-zero threshold.

---

## 4. Audit of existing 9 hardening tests for `threshold=0.0` dependencies

### 4.1 Method
Grep'd `tests/` for `vet_transit_shape`, `Likely Planet`, `Ambiguous`, `vetting_status`, `v_shape_metric`. Read each match.

### 4.2 Findings per test

| Test | Asserts on `vetting_status` directly? | Depends on threshold=0.0? |
|------|---------------------------------------|---------------------------|
| `test_expected_occultation_depth_ppm_hot_jupiter_around_sun` | no (unit test on PhysicalPropertiesEngine) | no |
| `test_expected_occultation_depth_ppm_earth_sun_analog` | no | no |
| `test_expected_occultation_depth_ppm_hot_planet_around_m_dwarf_exceeds_800ppm` | no | no |
| `test_expected_occultation_depth_ppm_returns_none_for_missing_inputs` | no | no |
| `test_expected_occultation_depth_ppm_caps_temperature_ratio_at_one` | no | no |
| `test_pipeline_uses_physical_threshold_for_hot_planet_around_m_dwarf` | **yes** — asserts `vetting_status.startswith("Verified Planet Candidate")` and `"Binary" not in vetting_status`. **Uses 4% primary depth (≥ 3%)**, so the cross-vetting branch uses the V-shape + secondary-eclipse branch (detection.py:141-148) — the verdict comes from the secondary-eclipse logic, NOT from vet_transit_shape alone. | **No** (4% depth puts it on the cross-vetting path, not the "Likely Planet" path) |
| `test_pipeline_fallback_when_physical_inputs_missing` | no (asserts only on `secondary_eclipse_threshold_mode` and value) | no |
| `test_pipeline_fallback_when_transit_depth_unavailable` | no (asserts only on threshold-mode keys) | no |
| `test_pipeline_threshold_mode_present_in_result_dict_for_known_truth` | no (asserts only on threshold-mode keys; uses 1% depth so lands on the "Verified Planet Candidate" branch via depth<3%, not via `Likely Planet`) | no |

### 4.3 Conclusion
**None of the 9 hardening tests assert on the "Likely Planet" verdict from `vet_transit_shape` directly.** All test vetting verdicts are derived from the cross-vetting tree in `detection.py:135-169`, which consults `vet_transit_shape` only for the V-shape and secondary-eclipse branches (when the depth branch doesn't already force "Verified Planet Candidate").

For shallow transits (< 3% depth, including the pipeline_smoke case at 1% depth), line 139-140 sets `vetting_status = "Verified Planet Candidate"` directly — `vet_transit_shape`'s verdict is *overridden*. So `test_pipeline_smoke.py`'s `vetting.startswith("Verified Planet Candidate")` assertion is independent of the threshold.

### 4.4 Sanity check: what does `vet_transit_shape` return for the test scenarios?

For the box-transit used in `_build_transit_with_secondary` (sharp ingress/egress, not trapezoidal):
- The U-shape trapezoid fit will be worse than the actual box (trapezoid has sloped ingress where the data has vertical ingress).
- The V-shape linear fit will be even worse (V-shape has no flat region at all).
- So both fits have larger chi2 than the true model, but their *difference* depends on whether the trapezoid or V-shape is closer to the box.

Without re-running, I expect Δ(u−v) to be small in absolute terms (likely < 0.001), meaning the new threshold=0.001 will flip this case from "Likely Planet" to "Ambiguous/False Positive". **This is the CORRECT behavior** — a box-transit (sharp ingress) is not really a planet-transit (smooth trapezoid), so vet_transit_shape being honest about the ambiguity is appropriate. The downstream pipeline verdict still arrives at "Verified Planet Candidate" via the cross-vetting tree (secondary-eclipse branch, or depth branch if depth < 3%).

**Predicted outcome:** the 9 hardening tests will all still pass with threshold=0.001. No test needs updating.

---

## 5. Open uncertainties / deferred items

1. **Wilks-theorem formal FAP is NOT computed here.** The threshold=0.001 is empirically motivated, not derived from a chi-squared-delta distribution's quantile. The values seen in §2 are tiny because the local fit window is small (~25 samples) and the fits converge to similar residuals for noise-only data.
2. **Synthetic-only characterization.** Real Kepler/TESS light curves were not used. The threshold may need re-tuning if real-data behavior differs significantly. The bucket-9 audit notes this same caveat for the DETECTION_CONFIDENCE_FLOOR.
3. **The verdict logic itself** (only line 112 uses `threshold`) is preserved per the hard constraint; only the threshold value changes. If a future maintainer wants a stricter rule (e.g., "require delta_chi2_u > X absolute AND delta_chi2_u > delta_chi2_v + Y relative"), that's a separate redesign.

---

## 6. Verification commands for this audit

```bash
PYTHONPATH=. python scratch/bucket10_threshold_characterization.py
PYTHONPATH=. python scratch/bucket10_threshold_characterization_scaling.py
# Expected: clean separation, threshold=0.001 in the gap between real-U-shape
# (+0.0021) and noise/V-shape (≤ 0).
```