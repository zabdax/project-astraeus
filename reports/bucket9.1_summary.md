# Bucket 9.1 — Signal-Detection Tuning: Summary

**Branch:** `fix/bls-noise-false-positive`
**Date:** 2026-06-22
**Type:** science-layer bugfix (BLS emission-gate tightening)

---

## TL;DR

| Metric | Pre-fix | Post-fix | Delta |
| --- | --- | --- | --- |
| Noise FP rate (50 realizations, sigma=0.01, n=500, T=10d) | **68.0%** | **0.0%** | **-68.0 pp** |
| Real-signal guardrail recoveries (5 scenarios) | 5/5 PASS | 5/5 PASS | no regression |
| `test_noise_injection` status | XFAIL (strict) | PASS | xfail removed |
| Multi-seed guardrail (10 seeds) | (didn't exist) | 10/10 PASS | new test |
| Fast gate: passed / skipped / xfailed / failed | 70 / 1 / 1 / 0 | **81 / 1 / 0 / 0** | +11 / 0 / -1 / 0 |
| Fast gate exit code | 0 (green via xfail) | **0 (green, no xfail)** | genuine green |

The fix is **two named constants** + **one boolean conjunction** in
`detect_transit_candidate`:

```python
DETECTION_SNR_THRESHOLD_DEFAULT = 12.0   # was 5.0
DETECTION_CONFIDENCE_FLOOR       = 7.0    # new
is_valid = (best_snr > snr_threshold) and (best_confidence >= DETECTION_CONFIDENCE_FLOOR)
```

Both values are empirically derived from Phase 1.3 (50 pure-noise
realizations) and Phase 1.4 (5 real-signal guardrail scenarios × 5
repeats) — see `reports/bucket9.1_signal_detection_audit.md` §3 and §4.

---

## 1. The bug, the data, the fix

### 1.1 The bug

`detect_transit_candidate` was emitting `candidate_found=True` on pure
white noise at `snr_threshold=5.0`. The Phase 0 confirmation (run with
`--runxfail` to bypass the polish bucket's xfail mask) reproduced the
exact bucket-5 finding:

```python
results = detect_transit_candidate(time, flux, snr_threshold=5.0)
# results['candidate_found']  == True
# results['confidence_score'] == 4.086
```

### 1.2 The data

Phase 1.3 — 50 independent pure-noise realizations at the
test_noise_injection fixture. Output:
`scratch/bucket9.1_fp_characterization.json`.

| Statistic | All 50 runs | FP subset (n=34) |
| --- | --- | --- |
| **SNR** min / median / max / stdev | 2.75 / 5.38 / **10.67** / 1.58 | 5.03 / 6.21 / 10.67 / — |
| **confidence_score** min / median / max | 1.79 / 2.87 / **5.96** / — | 2.15 / 3.39 / 5.96 / — |

**68% of pure-noise runs tripped the detector.** This is not a
seed-specific fluke — it's a systematic gap in the emission gate.

Phase 1.4 — 5 real-signal scenarios from the guardrail tests
(pipeline_smoke, test_signal_recovery, hot_jupiter_clean,
hot_planet_around_m_dwarf, earth_sun_analog), 5 repeats each. Output:
`scratch/bucket9.1_real_signal_characterization.json`.

| Scenario | SNR | confidence_score | vetting_status |
| --- | ---: | ---: | --- |
| pipeline_smoke (3.0d, depth=0.01) | **16.42** | **9.02** | Verified Planet Candidate |
| test_signal_recovery (3.14d, depth=0.02) | 61.59 | 13.32 | Verified Planet Candidate |
| hot_jupiter_clean (3.0d, depth=0.01) | ~1630 | ~21.65 | Verified Planet Candidate |
| hot_planet_around_m_dwarf (1.5d, depth=0.04) | ~2555 | ~29.03 | Verified Planet Candidate (Atmospheric Occultation Detected) |
| earth_sun_analog (2.0d, depth=0.04) | ~5638 | ~23.45 | Verified Planet Candidate |

**Real-signal floors:** SNR = 16.42, confidence_score = 9.02.

### 1.3 The gap (as measured on synthetic fixtures)

Within the synthetic fixtures tested (50 noise realizations + 5
real-signal guardrail scenarios), the two distributions do **not**
overlap. There is a gap on both axes:

| Metric | Noise max | Real min | Gap | Threshold (current) | Headroom (above noise) | Headroom (below real) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **SNR** | 10.67 | 16.42 | ~5.75 | **5.0** (default; reverted in bucket 9.2 Item 2) | — (caller-tunable) | — |
| **confidence_score** | 5.96 | 9.02 | ~3.06 | **7.0** (load-bearing) | **1.04** | **2.02** |

**Important caveat:** these gaps were measured against SYNTHETIC
fixtures only. Real Kepler/TESS marginal detections (shallow transits,
grazing geometries, noisy giant-star photometry) can legitimately land
at lower SNR / confidence_score than the synthetic floor and would be
silently rejected by the 7.0 floor. The real-world rejection rate is
UNCHARACTERIZED — see §6 ("Known limitation") below.

The bucket-9.2 SNR revert (5.0 default) does NOT reintroduce the
single-planet FP problem because the confidence_score floor is
unconditional; on its own it catches all 50 noise realizations from
the Phase 1.3 sweep.

### 1.4 The fix

```diff
 # astraeus/core/constants.py
+DETECTION_SNR_THRESHOLD_DEFAULT = 12.0  # was inline 5.0; noise max=10.67, real floor=16.42
+DETECTION_CONFIDENCE_FLOOR       = 7.0   # new; noise max=5.96, real floor=9.02
```

```diff
 # astraeus/analysis/detection.py
-def detect_transit_candidate(time, flux, ..., snr_threshold=5.0):
+def detect_transit_candidate(time, flux, ..., snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT):
     ...
-    is_valid = best_snr > snr_threshold
+    is_valid = (
+        best_snr > snr_threshold
+        and best_confidence >= DETECTION_CONFIDENCE_FLOOR
+    )
```

The confidence_score floor is **unconditional**: a caller who passes
`snr_threshold=5.0` explicitly (as `test_noise_injection` does) still
gets the confidence_score gate applied. This is the load-bearing
property — without it, raising the default alone wouldn't fix the
targeted test.

---

## 2. Test coverage added

### 2.1 `test_noise_injection` (xfail removed)

- **Before:** `@pytest.mark.xfail(strict=True)` per the polish bucket.
  Test ran, expected to fail, gate exited 0.
- **After:** No marker. Test runs, asserts `is_candidate is False`,
  **genuinely passes** because the new confidence_score floor rejects
  the noise realization (confidence_score = 4.086 < 7.0).
- The strict xfail was doing its job: the moment the underlying bug
  was fixed, the gate turned RED with XPASS, alerting the reviewer.
  Now that the bug is genuinely fixed, the xfail is no longer needed.

### 2.2 `test_noise_injection_rejects_multiple_seeds` (new, parametrized)

- 10 parametrized cases over seeds `[42, 100, 101, 105, 109, 120, 122, 126, 129, 134]`.
- Pre-fix, **9 of 10 were false positives** at `snr_threshold=5.0`
  (confirmed in `scratch/bucket9.1_fp_characterization.json`).
- Post-fix: **all 10 are correctly rejected**.
- The 10 seeds span the SNR distribution from the Phase 1.3 sweep.
- This guards against seed-specific overfit — if a future regression
  makes the fix work for seed=42 only, the gate goes red on at least
  one of the other 9 seeds.

### 2.3 Coverage gap analysis

The 10 seeds are drawn from the Phase 1.3 noise distribution but
sample only `snr_threshold=5.0, sigma=0.01, n=500, T=10d`. Other
parameter combinations are not covered by this parametrized test.
That's acceptable for this bucket (the bug is most acute at these
parameters — they're the test_noise_injection fixture) but a future
bucket could broaden coverage.

---

## 3. Verification

### 3.1 Per-test verification

```bash
python -m pytest tests/test_agent_detective.py::test_noise_injection -v
# Expected: PASSED (was XFAIL pre-fix)
```

```bash
python -m pytest tests/test_agent_detective.py::test_noise_injection_rejects_multiple_seeds -v
# Expected: 10 passed (one per seed)
```

### 3.2 Guardrail tests (must not regress)

```bash
python -m pytest tests/test_pipeline_smoke.py \
                  tests/test_vetting_threshold_hardening.py \
                  tests/test_bulletproof_detector.py::test_mathematical_aliasing_stress_test \
                  tests/test_bulletproof_detector.py::test_state_binding_safety_verification -v
```

**Result:** All guardrail tests pass.

| Test | Pre-fix SNR / conf | Post-fix SNR / conf | Verdict |
| --- | --- | --- | --- |
| test_pipeline_smoke (synthetic, samples=2000) | 16.42 / 9.02 | 16.42 / 9.02 | no regression |
| test_signal_recovery (3.14d, depth=0.02) | 61.59 / 13.32 | 61.59 / 13.32 | no regression |
| hot_jupiter_clean (3.0d, depth=0.01) | ~1630 / ~21.65 | ~1630 / ~21.65 | no regression |
| hot_planet_around_m_dwarf (1.5d, depth=0.04) | ~2555 / ~29.03 | ~2555 / ~29.03 | no regression |
| earth_sun_analog (2.0d, depth=0.04) | ~5638 / ~23.45 | ~5638 / ~23.45 | no regression |
| 9 test_vetting_threshold_hardening cases | — | — | all PASS |

**Headroom for the lowest-real-signal case (`pipeline_smoke`):**

| Gate | Threshold | Real value | Headroom (real - threshold) |
| --- | ---: | ---: | ---: |
| SNR default | 5.0 (default; reverted in bucket 9.2 Item 2 — caller-tunable secondary check) | 16.42 | 11.42 SNR units (not load-bearing) |
| confidence_score floor | 7.0 (load-bearing noise-rejection gate) | 9.02 | **2.02 confidence units** |

The closest-real-signal case still has comfortable headroom above
both new thresholds. Any regression that brings the pipeline_smoke SNR
or confidence_score below the new thresholds will turn the guardrail
red — that's the early-warning signal.

### 3.3 Full fast gate

```bash
python -m pytest tests/ -m "not network and not slow" -v > reports/bucket9.1_posttest.txt 2>&1
echo "exit=$?"
```

**Result:** `81 passed, 1 skipped, 33 deselected, 0 failed, exit=0`

| Metric | Phase 0 baseline | Phase 3 posttest | Delta |
| --- | --- | --- | --- |
| passed | 70 | **81** | +11 (10 multi-seed + 1 noise) |
| skipped | 1 (test_ui_flow) | 1 (test_ui_flow) | 0 |
| xfailed | 1 (test_noise_injection) | **0** | -1 (xfail removed) |
| failed | 0 | 0 | 0 |
| exit | 0 (green via xfail) | **0 (genuine green)** | qualitative improvement |

The skipped test (`test_ui_flow`) is from the polish bucket's Item 1
decision and is unrelated to this work. See
`reports/bucket9_summary.md` §2 for its rationale.

---

## 4. Files touched

| File | Change |
| --- | --- |
| `astraeus/core/constants.py` | Added `DETECTION_SNR_THRESHOLD_DEFAULT = 12.0` and `DETECTION_CONFIDENCE_FLOOR = 7.0` with comments citing the Phase 1.3/1.4 data. |
| `astraeus/analysis/detection.py` | Imported the two new constants. Changed `snr_threshold=5.0` default to `snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT`. Added `confidence_score >= DETECTION_CONFIDENCE_FLOOR` to the emission gate. |
| `tests/test_agent_detective.py` | Removed `@pytest.mark.xfail(strict=True)` from `test_noise_injection`. Added `test_noise_injection_rejects_multiple_seeds` (parametrized over 10 seeds). |
| `reports/bucket9.1_signal_detection_audit.md` | New: Phase 1 discovery audit. |
| `reports/bucket9.1_pretest_baseline.txt` | New: Phase 0 baseline log. |
| `reports/bucket9.1_posttest.txt` | New: Phase 3 posttest log. |
| `scratch/bucket9.1_fp_characterization.py` + `.json` | New: regenerable Phase 1.3 diagnostic. |
| `scratch/bucket9.1_real_signal_characterization.py` + `.json` | New: regenerable Phase 1.4 diagnostic. |
| `logs/experiments.json` | IDs/timestamps auto-updated by `save_experiment_log()` during posttest re-run. |

**No app code outside `astraeus/analysis/detection.py` was modified.**
The VettingEngine, GeometricValidator, and downstream consumers are
unchanged. The deprecated dashboard file was not touched.

---

## 5. Commits (5 small, each independently revertible)

```
b9e68b0  fix(detection): reject BLS false-positives in pure noise via confidence_score floor + raised SNR default
e48a8d9  docs(bucket9.1): add Phase 1 discovery audit + scratch diagnostic scripts
faaf537  docs(bucket9.1): Phase 0 pretest baseline (70 passed, 1 skipped, 33 deselected, 1 xfailed, exit 0)
577bff9  test(noise): remove xfail, add multi-seed guardrail against seed-specific overfit
c555f63  docs(bucket9.1): Phase 3 posttest result (81 passed, 1 skipped, 33 deselected, exit 0)
0f95a96  chore(bucket9.1): update experiments.json IDs and timestamps after posttest re-run
```

---

## 6. What remains uncertain or deferred

- **Formal false-alarm probability (FAP).** The `confidence_score` is
  a peak-to-median ratio. The statistic itself is analogous to the
  peak-height statistics discussed in Horne & Baliunas (1986) and
  Schwarzenberg-Czerny (1997), but those papers describe how to
  compute a FORMAL FAP from the periodogram via chi-squared
  statistics; they do NOT bless "peak/median ratio of 7" as a
  threshold. A future bucket could add chi-squared FAP or MC
  permutation testing for stronger, first-principles noise rejection.
  Out of scope here. See `astraeus/core/constants.py` `DETECTION_CONFIDENCE_FLOOR`
  docstring for the precise framing.
- **Marginal-planet recovery (synthetic-only basis).** Real signals
  with SNR in the [5, 12] band or `confidence_score` in the [6, 9]
  band could be affected. None of the guardrail tests exercise that
  regime — they all produce SNR > 16 and confidence_score > 9. See
  §6.5 ("Known limitation") below for what is NOT measured.
- **Period-domain restriction.** Noise FPs cluster at 0.3d–0.7d. A
  minimum-period gate would also catch them. Not added here — the
  confidence_score floor already catches all 50 noise realizations
  on its own (no SNR-default raised required), so a third check
  would be redundant.
- **Headroom tracking.** The closest real-signal case
  (`pipeline_smoke`) sits at SNR=16.42, confidence=9.02 — 11.42 SNR
  units above the (caller-tunable) 5.0 default and 2.02 confidence
  units above the load-bearing 7.0 floor. A monitoring/alerting
  bucket could track these as regression canaries.

### 6.5 Known limitation — synthetic-only basis for the 7.0 threshold

**Status:** UNCHARACTERIZED. The Phase 1.4 real-signal fixtures are
all SYNTHETIC — they come from `tests/test_pipeline_smoke.py`,
`tests/test_vetting_threshold_hardening.py`, and
`tests/test_agent_detective.py::test_signal_recovery`. Bucket 9.1
explicitly acknowledges this in §3 ("CHARACTERIZE the false positive
empirically") but the audit's noise-vs-signal gap analysis (§4) was
performed against these synthetic fixtures only.

**What this means:** real Kepler/TESS marginal detections (shallow
transits, grazing geometries, noisy giant-star photometry,
non-Gaussian noise, instrument systematics) can legitimately produce
SNR / confidence_score values below the synthetic floor and would be
silently rejected by `DETECTION_CONFIDENCE_FLOOR = 7.0`. The
rejection rate on real marginal detections is unknown.

**Recommended follow-up:** a future bucket should sweep a curated set
of known Kepler/TESS marginal detections (e.g. the Kepler
"Earth-like candidate" working list, or the TESS TOI catalog at
the low-confidence end) and characterize the rejection rate at the
7.0 floor. If the rejection rate is high, the floor may need to be
lowered; if low, the current value is empirically validated for real
data too. Bucket 9.2 Item 4 added
`scratch/bucket9.2_real_curve_characterization_template.py` as a
stub for that work — see its docstring for the planned structure.

**Bucket 9.2 Item 2 SNR revert connection:** because the SNR default
was reverted to 5.0 (the confidence floor is the only load-bearing
gate), lowering the confidence floor in the future to admit more
real marginal detections would be a one-line change with no other
knobs to turn.

---

## 7. Verification commands (reproducible)

```bash
# Switch to the branch
git checkout fix/bls-noise-false-positive

# Confirm clean tree
git status

# Show the diff vs v.0.0.2
git log v.0.0.2..HEAD
git diff v.0.0.2..HEAD -- astraeus/ tests/

# Per-test verification
python -m pytest tests/test_agent_detective.py::test_noise_injection -v
python -m pytest tests/test_agent_detective.py::test_noise_injection_rejects_multiple_seeds -v
python -m pytest tests/test_pipeline_smoke.py -v
python -m pytest tests/test_vetting_threshold_hardening.py -v
python -m pytest tests/test_bulletproof_detector.py::test_mathematical_aliasing_stress_test -v
python -m pytest tests/test_bulletproof_detector.py::test_state_binding_safety_verification -v

# Full fast gate. Expected: 81 passed, 1 skipped, 33 deselected, exit 0.
python -m pytest tests/ -m "not network and not slow" -v > reports/bucket9.1_posttest.txt 2>&1
echo "exit=$?"   # exit 0 (gate is GREEN, no xfail involvement)
tail -3 reports/bucket9.1_posttest.txt

# Optional: re-run the FP characterization script to verify zero FPs post-fix.
python scratch/bucket9.1_fp_characterization.py 2>&1 | tail -10
# Expected: "False positives: 0 (0.0%)"
```

---

## 8. Bucket 5 / polish bucket interaction

- **Bucket 5** confirmed the noise test was a real signal-detection
  concern (not a test artifact) and explicitly forbade silencing it
  with `@pytest.mark.xfail` — per its §1.4 and §7.
- **Polish bucket 9** (separate from this bucket 9.1) revisited that
  position. With Bucket 8 having unmasked the other 3 test failures,
  the noise test was the only remaining red. The polish bucket
  applied `xfail(strict=True)` as a **gate-signal design**: the gate
  would turn RED with XPASS the moment the underlying bug was fixed —
  which is exactly the trigger that brought bucket 9.1 into existence.
- **Bucket 9.1 (this work)** removed the xfail because the underlying
  bug is now genuinely fixed. The gate is green for the right reason,
  not via xfail.

The xfail marker served its purpose as a trigger signal. It is
correctly removed now that the bug is fixed.
