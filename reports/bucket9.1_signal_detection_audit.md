# Bucket 9.1 — Signal-Detection Tuning: Audit

**Branch:** `fix/bls-noise-false-positive`
**Date:** 2026-06-22
**Phase:** 1 (discovery, read-only)

This document is the read-only Phase 1 output. It documents:

1. The exact decision path in `astraeus/analysis/detection.py` from BLS output to `candidate_found=True`.
2. The BLS internals in `astraeus/analysis/bls_search.py` — how `search()` builds the periodogram, picks the best peak, and derives SNR and `confidence_score`.
3. The empirical characterization of the false-positive rate on 50 pure-noise realizations.
4. The empirical characterization of the SNR/`confidence_score` distribution on the real-signal guardrail scenarios.
5. Ranked candidate fixes, picked from the data.

Raw JSON for §3 and §4 lives in:
- `scratch/bucket9.1_fp_characterization.json` (50 noise runs)
- `scratch/bucket9.1_real_signal_characterization.json` (5 real-signal scenarios × 5 repeats)

---

## 1. Decision path from BLS output to `candidate_found=True`

File: `astraeus/analysis/detection.py`

```
line 17   def detect_transit_candidate(time, flux, ..., snr_threshold=5.0):
line 21-22 DetrendingEngine.estimate_stellar_rotation / detrend
line 29     for iteration in range(1, 4):
line 33       search_results = BLSSearchEngine.search(active_time, active_flux)
                  -> returns dict with period, duration, t0, snr, depth,
                                       confidence_score, periodogram
line 40       is_valid = best_snr > snr_threshold          ← single boolean gate
line 61-77    result dict built; 'candidate_found' = is_valid
                  result['candidate_found'] = is_valid   ← line 62
                  result['is_candidate']   = is_valid     ← line 63 (alias)
                  result['confidence_score'] = search_results['confidence_score']
line 178      if is_valid and best_snr > 7.0: mask and continue loop
```

**The single gating line is line 40:** `is_valid = best_snr > snr_threshold`
(where `snr_threshold` defaults to `5.0`).

**`candidate_found` is exactly this boolean** (line 62). No additional
gate, no secondary confirmation, no false-alarm probability check.

### 1.1 Where `confidence_score` is computed and what its units are

File: `astraeus/analysis/bls_search.py`, line 80:

```python
confidence_score = float(best_power / np.median(res.power))
```

`best_power` = the BLS periodogram power at the argmax period.
`np.median(res.power)` = the median power across the whole periodogram grid.

**Units:** dimensionless ratio. Interpretation: "how many times the
background noise level does the best peak stand above?" The statistic
itself — peak BLS power divided by the median periodogram power — is
**analogous to** the peak-height statistics discussed in Horne &
Baliunas (1986) and Schwarzenberg-Czerny (1997). However, those
papers describe how to compute a FORMAL false-alarm probability from
the periodogram via chi-squared statistics; they do NOT bless any
specific "peak/median ratio" threshold value. The code does NOT
compute a formal false-alarm probability; it only emits the ratio.
Whether any particular threshold on the ratio is "significant" is an
empirical question, addressed in §3 and §4 below.

### 1.2 The SNR threshold gate

File: `astraeus/analysis/detection.py`, line 17 + line 40:

```python
def detect_transit_candidate(time, flux, ..., snr_threshold=5.0):
    ...
    is_valid = best_snr > snr_threshold
```

`best_snr` (line 35) comes from `search_results['snr']`, which in turn
comes from `BLSSearchEngine.compute_snr_depth` (lines 6-23 of
`bls_search.py`). That function:
- Phase-folds the data at the candidate period and computes an
  in-transit vs out-of-transit flux difference.
- Estimates local noise as `np.std(out_flux)`.
- Returns `snr = (depth / local_noise_std) * sqrt(in_count)`.

This is **independent** of the BLS periodogram `res.power`. The same
periodogram can produce a small BLS power peak whose in-transit /
out-of-transit split happens to give a high SNR (just by random
phase alignment).

### 1.3 Every constant in the candidate-emission path

| Constant | Value | File:line | Notes |
| --- | --- | --- | --- |
| `snr_threshold` default | `5.0` | detection.py:17 | The ONLY gate. |
| Loop iteration count | `range(1, 4)` | detection.py:29 | Max 3 candidates per call. |
| Mask-iteration SNR floor | `7.0` | detection.py:178 | After a candidate is accepted, only mask and continue if SNR > 7.0. |
| `p_min` | `0.5` | bls_search.py:38 | Lower period bound (days). |
| `p_max` | `min(450.0, T_baseline/2.0)` | bls_search.py:39 | Upper period bound (days). |
| Inner-grid points | `4000` | bls_search.py:47 | 0.5d → 20d zone. |
| Outer-grid points | `10000` | bls_search.py:52 | 20d → 450d zone. |
| Duration grid | `[0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]` | bls_search.py:57 | In days. |
| Anti-alias harmonics | `[0.5, 2.0]` | bls_search.py:72 | The "alias trap" detector. |
| Anti-alias depth ratio | `0.85` | bls_search.py:75 | Promote a harmonic only if it preserves ≥85% of best depth. |
| Anti-alias SNR ratio | `0.85` | bls_search.py:75 | ...and ≥85% of best SNR. |

The 7.0 floor at line 178 is downstream of the emission gate and is
**not** the bug source — it only governs whether to mask-and-iterate,
not whether to emit a candidate in the first place.

---

## 2. BLSSearchEngine.search() — internals

File: `astraeus/analysis/bls_search.py`, lines 25-93.

### 2.1 Periodogram construction

```python
model = BoxLeastSquares(binned_time, binned_flux)   # line 30
T_baseline = float(np.max(time) - np.min(time))     # line 32
# Dual-zone grid:
#   inner 0.5d..20d:  4000 linear nodes
#   outer 20d..p_max: 10000 linear nodes
periods = np.unique(np.concatenate([grid_inner, grid_outer]))
durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
durations = durations[durations < p_min]            # astropy ValueError shield
res = model.power(periods, durations)               # line 59
```

`astropy.timeseries.BoxLeastSquares.power(periods, durations)` is a
vectorized grid search: for every (period, duration) pair, phase-fold
the data and compute the BLS statistic.

### 2.2 Best-peak picking

```python
best_idx = np.argmax(res.power)               # line 61
best_period = res.period[best_idx]            # line 62
best_power = res.power[best_idx]              # line 63
best_depth = float(res.depth[best_idx])       # line 64
transit_time = res.transit_time[best_idx]     # line 65
duration = res.duration[best_idx]             # line 66
```

**The single highest-power peak is taken.** There is no secondary
confirmation, no S/N ratio thresholding at the periodogram level, no
false-alarm probability estimate.

### 2.3 SNR derivation from the periodogram

```python
best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(
    binned_time, binned_flux, best_period, transit_time, duration)   # line 68
```

This is a **post-hoc, independent** SNR: phase-fold, median-subtract
in/out of transit, divide by local `np.std(out_flux)`, multiply by
`sqrt(in_count)`. It is **not** the BLS power.

This is what the emission gate at detection.py:40 uses.

### 2.4 confidence_score / periodogram-derived ratios

```python
confidence_score = float(best_power / np.median(res.power))    # line 80
```

**Existing "secondary peak ratio"-style statistic:** YES — but it is
NOT used as a gate. It is reported in the result dict and used by
upstream consumers (e.g. the UI's "Detection Report" JSON) for
informational display only. The emission gate at detection.py:40
ignores it.

### 2.5 Existing false-alarm-probability check?

**None.** The search returns the single argmax periodogram peak
(unless the alias-trap check at lines 72-78 promotes a harmonic).
There is no FAL, no Baluev-style p-value, no MC permutation test.

The alias-trap check is *not* a FAP check — it only prevents the
algorithm from being stuck at a half-period of the true period when
both have similar depth/SNR.

---

## 3. Empirical characterization of the false-positive rate

Script: `scratch/bucket9.1_fp_characterization.py`
Output: `scratch/bucket9.1_fp_characterization.json`
Run: 50 pure-noise realizations at the test_noise_injection fixture
(seed=42 first, then seeds 100..148), `np.random.normal(0, 0.01, 500)`
on `np.linspace(0, 10, 500)`, `snr_threshold=5.0`.

### 3.1 Headline numbers

| Metric | Value |
| --- | --- |
| **Total realizations** | 50 |
| **False positives (candidate_found=True)** | **34** |
| **False-positive rate** | **68.0%** |
| Elapsed wall time | 41.2 s |

**This is not a 1-in-20 fluke on seed=42.** Two-thirds of pure-noise
realizations trip the detector at `snr_threshold=5.0`.

### 3.2 SNR distribution

| Statistic | All 50 runs | FP subset (n=34) |
| --- | --- | --- |
| min | 2.754 | 5.029 |
| median | 5.376 | 6.206 |
| mean | 5.717 | 6.456 |
| max | 10.674 | 10.674 |
| stdev | 1.579 | — |

The FP SNR distribution is **entirely above 5.0** (by construction,
since that's the gate), but it reaches as high as **10.674**. The
`compute_snr_depth` phase-folding can produce large SNR values on
noise alone.

### 3.3 confidence_score distribution

| Statistic | All 50 runs | FP subset (n=34) |
| --- | --- | --- |
| min | 1.795 | 2.150 |
| median | 2.874 | 3.385 |
| mean | 3.147 | 3.498 |
| max | 5.956 | 5.956 |

`confidence_score = best_power / median(res.power)` peaks at **5.956**
on noise. This is the periodogram-statistic counterpart to the SNR
distribution — both are bounded, both have well-defined maxima on
noise alone.

### 3.4 Period distribution on FPs

The 34 FPs cluster heavily in short-period noise:

| Period bin | Count |
| --- | --- |
| 0.3d–0.7d | 23 |
| 0.7d–1.0d | 3 |
| 1.0d–2.0d | 5 |
| 2.0d–5.0d | 3 |

68% of FPs are in the 0.3d–0.7d range. This is a known BLS artifact:
short periods have many phase-coherent chances to align with random
noise fluctuations.

### 3.5 Key conclusion

The single gate `snr > 5.0` is **not strict enough** for white noise.
Either the SNR threshold needs to be raised substantially (to >11)
or an independent gate (e.g. `confidence_score` floor) needs to be
added on top.

---

## 4. Real-signal recovery fixtures

Script: `scratch/bucket9.1_real_signal_characterization.py`
Output: `scratch/bucket9.1_real_signal_characterization.json`

Five real-signal scenarios, 5 repeats each. All call
`detect_transit_candidate(metadata=..., snr_threshold=5.0)`.

| Scenario | Period | Depth | SNR | confidence_score | vetting_status |
| --- | ---: | ---: | ---: | ---: | --- |
| `pipeline_smoke` (samples=2000, seed=42) | 3.0d | 0.01 | **16.42** | **9.02** | Verified Planet Candidate |
| `test_signal_recovery` (3.14d, depth=0.02, sigma=0.001) | 3.14d | 0.02 | 61.59 | 13.32 | Verified Planet Candidate |
| `hot_jupiter_clean` (3.0d, depth=0.01, no secondary) | 1.5d | 0.01 | 1630 | 21.65 | Verified Planet Candidate |
| `hot_planet_around_m_dwarf` (1.5d, depth=0.04, secondary=0.001) | 1.5d | 0.04 | 2555 | 29.03 | Verified Planet Candidate (Atmospheric Occultation Detected) |
| `earth_sun_analog` (2.0d, depth=0.04) | 2.0d | 0.04 | 5638 | 23.45 | Verified Planet Candidate |

### 4.1 SNR floor on real signals

The **minimum** SNR across all real-signal runs is **16.42**
(`pipeline_smoke`). Noise SNR maxes at **10.674**. There is a clean
**~6 SNR-unit gap** between noise and real signals **as measured on
this synthetic fixture set**. Whether the same gap holds for real
Kepler/TESS marginal detections (shallow transits, grazing geometries,
noisy giant-star photometry) is **not characterized** in this audit —
see `reports/bucket9.1_summary.md` §6 ("Known limitation").

### 4.2 confidence_score floor on real signals

The **minimum** confidence_score across all real-signal runs is
**9.02** (`pipeline_smoke`). Noise confidence_score maxes at **5.956**.
There is a clean **~3-unit gap** between noise and real signals **on
this synthetic fixture set**. As with §4.1, real-curve generalization
is uncharacterized — see the same "Known limitation" note.

### 4.3 Vetting status on real signals

All real-signal runs produce a planet-candidate label (no eclipsing
binary, no "Ambiguous/False Positive"). The pipeline recovery of the
injected period is accurate to within ~1% in every scenario.

### 4.4 Key conclusion

**Within the synthetic fixtures tested, there IS a clean threshold
that separates noise from real signals.** The bucket protocol's "STOP
if no threshold separates them" condition is NOT met for these
fixtures. A tuning fix is appropriate **with the caveat** that the
gap was measured against synthetic data only; real-curve
generalization is uncharacterized and would be a follow-up bucket.

---

## 5. Ranked candidate fixes

### 5.1 Option (a): Raise `snr_threshold` default from 5.0 → 12.0

**Data support:** noise SNR max = 10.674 < 12 < 16.42 = real-signal SNR
min. **Clean gap of 6 SNR units.**

**Implementation:** change `detection.py:17` default and add named
constant `DETECTION_SNR_THRESHOLD_DEFAULT = 12.0` to
`astraeus/core/constants.py`.

**Pros:**
- Simplest possible fix.
- Data-justified value.
- Defense in depth against marginal callers.

**Cons:**
- test_noise_injection calls `detect_transit_candidate(time, flux, snr_threshold=5.0)`
  explicitly, so a default-only change does NOT affect this test. The
  test would still trip the FP unless we ALSO add an internal gate.

**Verdict:** necessary but not sufficient on its own. Must be paired
with (b) to bypass the test's explicit `snr_threshold=5.0`.

### 5.2 Option (b): Add `confidence_score` floor in detection.py

**Data support:** noise confidence_score max = 5.956 < 7 < 9.02 =
real-signal confidence_score min. **Clean gap of ~3 units.**

**Implementation:** change detection.py:40 from
`is_valid = best_snr > snr_threshold` to
`is_valid = best_snr > snr_threshold and search_results['confidence_score'] >= DETECTION_CONFIDENCE_FLOOR`.
Add named constant `DETECTION_CONFIDENCE_FLOOR = 7.0` to constants.py.

**Pros:**
- Bypass-resistant: caller-provided `snr_threshold=5.0` cannot defeat
  this internal gate.
- Directly motivated by Phase 1.3 data.
- The `confidence_score` statistic IS already in the result dict — we
  are merely using an existing quantity as an additional gate instead
  of purely informational.
- Single-line change in detection.py plus a named constant.

**Cons:**
- The `confidence_score` formula has no formal statistical
  justification in the codebase. We are picking a value empirically
  (data-driven), not from first-principles FAP.

**Verdict:** the necessary core of the fix. Catches the noise test
even when callers pass low `snr_threshold`.

### 5.3 Option (c): Add secondary confirmation (best-peak-to-median ratio)

**Already implicit in `confidence_score`.** Option (b) IS this option.
Listed separately in the prompt but in this codebase they are the
same statistic.

### 5.4 Option (d): Require minimum in-transit data points / coverage

Not motivated by the Phase 1.3 data: noise FPs already pass through
the existing in-transit-count gate in `compute_snr_depth` (it
contributes to the SNR via `sqrt(in_count)`). The noise FPs have
sufficient in-transit counts to reach SNR>5.

**Verdict:** would not help.

### 5.5 Recommended fix

**Combine (a) + (b):**

1. Add `DETECTION_SNR_THRESHOLD_DEFAULT = 12.0` to constants.py
   (raised from 5.0). Justification: noise SNR max=10.674, real-signal
   SNR floor=16.42, gap=~6 units. Comment cites Phase 1.3 data.
2. Add `DETECTION_CONFIDENCE_FLOOR = 7.0` to constants.py. Justification:
   noise confidence_score max=5.956, real-signal confidence_score floor=9.02,
   gap=~3 units. Comment cites Phase 1.3 data.
3. Change detection.py:17 default to use the new constant.
4. Change detection.py:40 to add the `confidence_score` floor to the
   emission gate. This is the load-bearing change — it bypasses any
   caller-supplied `snr_threshold` and applies the new floor uniformly.

The two gates are independent, both data-justified, both leave headroom
above the noise maxima and below the real-signal minima.

---

## 6. Verification commands (read-only preview, post-implementation)

```bash
# The single noise test must now pass.
python -m pytest tests/test_agent_detective.py::test_noise_injection --runxfail -v
# Expected: PASSED

# Guardrail tests must still pass.
python -m pytest tests/test_pipeline_smoke.py tests/test_vetting_threshold_hardening.py tests/test_bulletproof_detector.py -v
# Expected: all PASSED

# Full fast gate.
python -m pytest tests/ -m "not network and not slow" -v
# Expected: 0 failures, 0 xfails (xpass of test_noise_injection if xfail
# marker is still present; will be removed in Phase 3).
```

---

## 7. What remains uncertain or deferred

- **Optimal value of `DETECTION_CONFIDENCE_FLOOR`.** We picked 7.0
  empirically (above noise max 5.956, below real min 9.02). The
  statistic itself is analogous to peak-height FAP discussions in
  Horne & Baliunas (1986) / Schwarzenberg-Czerny (1997), but those
  papers describe a formal chi-squared FAP calculation, not a
  peak/median-ratio threshold. Bucket 9.2 explicitly softened the
  constant's comment to make this clear. A principled value would
  come from a chi-squared FAP calculation on the periodogram, but
  that is out of scope for this bucket (a redesign-level change).
- **Real-planet recovery at very low SNR.** We have not tested real
  signals with SNR < 12 in this audit. Bucket 9.2 reverted the
  SNR default to 5.0 (because the confidence floor alone catches all
  50 noise realizations), so this concern is now less acute — but
  real-curve characterization is still uncharacterized, see
  `reports/bucket9.1_summary.md` §6 ("Known limitation") and the
  optional stub at `scratch/bucket9.2_real_curve_characterization_template.py`.
- **The 68% FP rate implies the algorithm has very little
  noise-rejection beyond the single SNR gate.** A future bucket
  could pursue formal false-alarm probability estimation or MC
  permutation testing for stronger noise rejection.
- **Synthetic-only basis for the 7.0 threshold.** The Phase 1.4
  real-signal fixtures are all synthetic (test_pipeline_smoke.py,
  test_vetting_threshold_hardening.py, test_agent_detective.py::test_signal_recovery).
  Bucket 9.2 Item 4 added a "Known limitation" subsection to the
  summary documenting that the 7.0 threshold's real-world rejection
  rate on marginal Kepler/TESS detections is uncharacterized. A
  follow-up bucket with real-curve ingestion would characterize it.
