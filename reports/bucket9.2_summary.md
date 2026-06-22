# Bucket 9.2 — Polish & Follow-up: Summary

**Branch:** `fix/multi-planet-noise-fp-audit` (stacked on
`fix/bls-noise-false-positive`)
**Date:** 2026-06-23
**Type:** post-bucket-9.1 cleanup: SNR-default revert, comment honesty,
multi-planet audit, test isolation

---

## TL;DR

| Metric | Before (bucket 9.1 tip) | After (bucket 9.2 tip) | Delta |
| --- | --- | --- | --- |
| Fast gate passed | 81 | **81** | 0 |
| Fast gate failed | 0 | **0** | 0 |
| Fast gate skipped | 1 (test_ui_flow) | 1 (test_ui_flow) | 0 |
| Fast gate exit | 0 | **0** | 0 |
| `logs/experiments.json` mutated by test run | yes (75+ lines added per run) | **no (hermetic)** | qualitative fix |
| Multi-planet path FP rate (50 noise runs) | 0% (inherited via delegation) | 0% (unchanged) | 0 |
| Single-planet path FP rate (50 noise runs) | 0% | 0% | 0 |
| `DETECTION_SNR_THRESHOLD_DEFAULT` | 12.0 | **5.0** (reverted) | -7.0 |
| `DETECTION_CONFIDENCE_FLOOR` (load-bearing gate) | 7.0 | 7.0 (unchanged) | 0 |
| Tests added | — | 0 (item 1 picked (a)) | 0 |
| Code modified outside `astraeus/core/constants.py` | — | 0 (item 1) | 0 |

Five items executed:

| Item | Outcome | Commit |
| --- | --- | --- |
| 1 (decision gate) | **(a) no code change** — multi-planet path inherits confidence floor via delegation to detect_transit_candidate; 0% empirical FP rate | 36ff4f3 |
| 2 (with stop-guard) | **reverted** `DETECTION_SNR_THRESHOLD_DEFAULT` from 12.0 to 5.0; stop-guard verified (22 tests pass + 50-noise sweep 0%) | 6625aab |
| 3 (docs + comments) | **softened** literature overclaim in `DETECTION_CONFIDENCE_FLOOR` comment + audit §1.1/§4/§7 + summary §1.3/§3.2 | 2a5dc0f |
| 4 (flag + optional) | added §6.5 "Known limitation" + `scratch/bucket9.2_real_curve_characterization_template.py` stub | 9c73ee0 |
| 5 (test isolation) | added autouse conftest fixture: no-op patch + session backup/restore; hermeticity verified | 47f714e |

---

## Item 1 — does the multi-planet path apply the confidence floor?

**Decision:** (a) No code change.

`run_multi_planet_search` (orchestrator.py:92) **delegates** the emission
decision to `detect_transit_candidate` (orchestrator.py:147), which
applies the unconditional `DETECTION_CONFIDENCE_FLOOR = 7.0` gate added
by bucket 9.1 (detection.py:48-51). The orchestrator also adds its own
native guardrail at orchestrator.py:167.

**Empirical verification:** 50 pure-noise realizations routed through
`run_multi_planet_search` (with default `snr_floor=7.1, max_signals=5`)
produced **0 false-positive candidates** (0% FP rate).

The transitive protection is sufficient; no duplicate gate or test
needed. See `reports/bucket9.2_decisions.md` for full investigation.

**What I did:** document the finding in this summary and in the
decisions doc. **No new code, no new test.**

---

## Item 2 — revert `DETECTION_SNR_THRESHOLD_DEFAULT` to 5.0

**Rationale (per the user prompt):** the bucket-9.1 SNR raise from 5.0
to 12.0 was redundant with the confidence floor, which alone catches
all 50 noise realizations (noise confidence max = 5.96 < 7.0). The
raised SNR only cost real-signal sensitivity at the default threshold
for callers that don't pass an explicit `snr_threshold`.

**Action:**
- `DETECTION_SNR_THRESHOLD_DEFAULT = 5.0` (was 12.0) in
  `astraeus/core/constants.py`.
- Comment rewritten to document 5.0 as the historical default and
  reference this summary for the revert rationale.
- Constant kept **named** (not inlined at the call site) so future
  tuning has one place to edit.
- `detection.py` emission-gate comment updated to reflect that the
  confidence floor is load-bearing and the SNR threshold is a
  caller-tunable secondary check.

### Stop-guard verification

| Test | Result |
| --- | --- |
| `test_noise_injection` | PASSED |
| `test_noise_injection_rejects_multiple_seeds` (10 seeds) | 10/10 PASSED |
| `test_pipeline_smoke.py` | PASSED |
| `test_vetting_threshold_hardening.py` (9 tests) | 9/9 PASSED |
| 50-noise sweep via `scratch/bucket9.1_fp_characterization.py` | **0/50 FPs (0%)** |

All guardrails green; noise still rejected. Revert is safe.

---

## Item 3 — soften literature overclaim for `DETECTION_CONFIDENCE_FLOOR`

**Problem:** the bucket-9.1 constant comment framed the 7.0 value as a
"false-alarm probability analogue" justified by Horne & Baliunas
(1986) and Schwarzenberg-Czerny (1997). Those papers describe how to
compute a FORMAL FAP from the periodogram via chi-squared statistics;
they do NOT bless "peak/median ratio of 7" as a threshold. A future
maintainer could read the citations as implying 7.0 is
literature-grounded. It is not — it is empirically fit to 5 synthetic
scenarios.

**Action (doc + comment only, no behavior change):**

1. **Constant comment** (`astraeus/core/constants.py`):
   - Rewritten to say plainly: "EMPIRICALLY DERIVED, not a formal
     false-alarm probability."
   - Explicit warning: "The literature references are framed as 'the
     statistic is analogous to' rather than 'the value is justified
     by.'"
   - Names the bucket 9.1 Phase 1.3/1.4 sweeps as the empirical basis.
   - Flags the synthetic-only basis explicitly.

2. **Audit document** (`reports/bucket9.1_signal_detection_audit.md`):
   - §1.1: reframes literature references as "analogous to" peak-height
     statistics, NOT as FAP-value justifications.
   - §4.1, §4.2: add "as measured on this synthetic fixture set"
     caveat to the SNR and confidence_score gap claims.
   - §4.4: changes "There IS a clean threshold" → "Within the synthetic
     fixtures tested, there IS a clean threshold... real-curve
     generalization is uncharacterized."
   - §7: explicitly notes the synthetic-only basis, the SNR revert in
     9.2, and the follow-up bucket for real-curve characterization.

3. **Summary document** (`reports/bucket9.1_summary.md`):
   - §1.3: reframed as "The gap (as measured on synthetic fixtures)".
     Notes the 9.2 SNR revert and adds an "Important caveat" about
     real-world rejection rate being UNCHARACTERIZED.
   - §3.2: SNR-default headroom table reflects 5.0 (caller-tunable
     secondary), not 12.0 (was dead weight).
   - §6.5: NEW "Known limitation — synthetic-only basis for the 7.0
     threshold" subsection.

No code change. No test change.

---

## Item 4 — Known limitation + optional real-curve template

**Required (done in Item 3's commit):** new §6.5 in
`reports/bucket9.1_summary.md` explicitly states the 7.0 threshold's
real-world rejection rate on marginal Kepler/TESS detections is
**UNCHARACTERIZED**, and recommends a follow-up bucket.

**Optional (done in separate commit):** added
`scratch/bucket9.2_real_curve_characterization_template.py` — a stub
that mirrors `scratch/bucket9.1_real_signal_characterization.py` but
with a `NotImplementedError` for the real-curve loader. Running it
prints a help message pointing to §6.5. The future bucket can populate
`_CURATED_TARGETS` (Kepler Earth-like candidates, low-confidence TOIs,
grazing eclipsing binaries) and implement `_load_real_curve()` to
fetch from the relevant archives.

**No real-curve fetching done in this bucket.**

---

## Item 5 — stop `logs/experiments.json` churn during tests

**Problem:** `save_experiment_log()` mutates `logs/experiments.json` on
every `detect_transit_candidate` invocation, including during the full
fast gate. Bucket 9.1 normalized this by committing the churn as
`chore(...)` commits. This dirties the repo on every CI run and makes
test results non-hermetic.

**Action (test isolation only, no production behavior change):**

`tests/conftest.py` — added two fixtures:

1. **Function-scoped autouse** that patches
   `astraeus.analysis.detection.save_experiment_log` to a no-op for
   every test. Stops the dominant source of churn (every
   `detect_transit_candidate` call writes a record). Patched at the
   `detection.py` call site (where the symbol is bound by name) — not
   at the defining module — because detection imports the symbol by
   name: `from astraeus.analysis.logging import save_experiment_log`.

2. **Session-scoped autouse** that backs up `logs/experiments.json`
   at session start and restores it at session end. Handles the
   residual writes from
   `tests/test_experiment_history.py::test_experiment_history_cycle`
   which legitimately exercises the production save/load cycle
   (writes via direct `save_experiment_log` call, removes the file at
   cleanup).

### Hermeticity verification

```bash
git checkout -- logs/experiments.json
python -m pytest tests/ -m "not network and not slow" 2>&1 | tail -3
git status --porcelain logs/experiments.json   # MUST be empty
# Expected: empty (file restored from session backup)

# Run TWICE in succession to confirm idempotency.
python -m pytest tests/ -m "not network and not slow" 2>&1 | tail -3
git status --porcelain logs/experiments.json   # MUST be empty
```

**Verified clean across two consecutive runs.** 81 passed, 1 skipped,
33 deselected in both runs. No `chore(...)` commits needed.

The bucket 9.1 `chore(...)` commits remain in git history (reverting
them would be unrelated churn); future runs no longer produce churn.

---

## Verification (Phase 3)

| Test / Command | Result |
| --- | --- |
| `python -m pytest tests/test_agent_detective.py::test_noise_injection -v` | **PASSED** |
| `python -m pytest tests/test_agent_detective.py::test_noise_injection_rejects_multiple_seeds -v` | **10 passed** |
| `python -m pytest tests/test_pipeline_smoke.py tests/test_vetting_threshold_hardening.py tests/test_bulletproof_detector.py -v` | **all PASSED** (guardrails) |
| `python scratch/bucket9.1_fp_characterization.py` | **0/50 FPs (0%)** after Item 2 revert |
| Full fast gate (`-m "not network and not slow"`) | **81 passed, 1 skipped, 33 deselected, 0 failed, exit 0** |
| Hermeticity check (`git status --porcelain logs/experiments.json` after fast gate) | **empty** (verified across two consecutive runs) |

---

## Files touched

| File | Change |
| --- | --- |
| `astraeus/core/constants.py` | `DETECTION_SNR_THRESHOLD_DEFAULT = 5.0` (was 12.0); comment rewritten. `DETECTION_CONFIDENCE_FLOOR` comment reframed (empirical, not literature-grounded). |
| `astraeus/analysis/detection.py` | Emission-gate comment updated to reflect confidence-floor-is-load-bearing framing. |
| `tests/conftest.py` | Added `_suppress_save_experiment_log_during_tests` (function-scoped autouse no-op patch) + `_backup_and_restore_experiments_json` (session-scoped autouse backup/restore). |
| `reports/bucket9.1_signal_detection_audit.md` | §1.1 literature framing softened; §4.1/§4.2/§4.4 synthetic-only caveat added; §7 follow-up bucket recommendations expanded. |
| `reports/bucket9.1_summary.md` | §1.3 reframed with synthetic-only caveat + 9.2 SNR-revert note; §3.2 SNR-default table reflects 5.0; new §6.5 "Known limitation" subsection. |
| `reports/bucket9.2_decisions.md` | **NEW** — Item 1 decision-gate investigation + recommendation. |
| `reports/bucket9.2_pretest_baseline.txt` | **NEW** — pretest log (bucket 9.1 tip state). |
| `reports/bucket9.2_posttest.txt` | **NEW** — posttest log (bucket 9.2 tip state). |
| `scratch/bucket9.2_multiplanet_fp_characterization.py` | **NEW** — 50-noise sweep through `run_multi_planet_search`. |
| `scratch/bucket9.2_multiplanet_fp_characterization.json` | **NEW** — output (0% FP rate). |
| `scratch/bucket9.2_real_curve_characterization_template.py` | **NEW** — Item 4 OPTIONAL stub for future real-curve bucket. |
| `scratch/reconstruct_bucket9.2_pretest.py` | **NEW** — regenerator for `bucket9.2_pretest_baseline.txt`. |

**No code change to `astraeus/core/orchestrator.py`** (Item 1 picked
(a) — multi-planet path inherits the floor transitively).
**No code change to `astraeus/analysis/bls_search.py`** (out of scope).
**No change to `ui/`, `app.py`, `route.py`, or the deprecated dashboard.**

---

## Commits (5 small, each independently revertible)

```
36ff4f3  docs(bucket9.2): Item 1 decision-gate finding — multi-planet path inherits confidence floor via delegation
6625aab  fix(detection): revert SNR default to 5.0 (Item 2)
2a5dc0f  docs(detection): soften DETECTION_CONFIDENCE_FLOOR comment + audit/summary framing (Items 3 + 4 required)
9c73ee0  scratch(bucket9.2): add real-curve characterization template stub (Item 4 OPTIONAL)
47f714e  test(isolation): suppress save_experiment_log + backup/restore experiments.json during tests (Item 5)
```

---

## Out-of-scope findings (flagged, not fixed)

- **Real Kepler/TESS curve characterization.** The 7.0
  `DETECTION_CONFIDENCE_FLOOR`'s real-world rejection rate is
  UNCHARACTERIZED (see §6.5 of `reports/bucket9.1_summary.md`). The
  template at `scratch/bucket9.2_real_curve_characterization_template.py`
  is a stub for a future bucket to populate and run.
- **Formal FAP estimation.** Still deferred. The current `confidence_score`
  is a peak/median ratio (analogous to peak-height FAP discussions in
  Horne & Baliunas 1986 / Schwarzenberg-Czerny 1997) but is not a
  formal FAP. A future bucket could add chi-squared FAP or MC
  permutation testing for first-principles noise rejection.
- **The bucket 9.1 `chore(...)` commits in git history.** They remain
  in the log; reverting them is unrelated churn and not in scope.

---

## Stacking / merge-order note

This branch (`fix/multi-planet-noise-fp-audit`) is stacked on
`fix/bls-noise-false-positive` (bucket 9.1). Both must land on
`v.0.0.2` together, in order:

1. `fix/bls-noise-false-positive` (bucket 9.1) → `v.0.0.2` first.
2. `fix/multi-planet-noise-fp-audit` (bucket 9.2) → `v.0.0.2` second.

Do NOT open a 9.2 PR that targets `v.0.0.2` directly while bucket 9.1
is still open — target bucket 9.1's branch or wait for it to land.

---

## Verification commands (reproducible)

```bash
git checkout fix/multi-planet-noise-fp-audit

# Pretest baseline (regenerable from bucket 9.1 posttest result).
python scratch/reconstruct_bucket9.2_pretest.py

# Pretest: confirm fast gate is at the bucket 9.1 tip state.
python -m pytest tests/ -m "not network and not slow" 2>&1 | tail -3
# Expected: 81 passed, 1 skipped, 33 deselected, exit 0

# Per-test verification.
python -m pytest tests/test_agent_detective.py::test_noise_injection -v
python -m pytest tests/test_agent_detective.py::test_noise_injection_rejects_multiple_seeds -v
python -m pytest tests/test_pipeline_smoke.py \
                  tests/test_vetting_threshold_hardening.py \
                  tests/test_bulletproof_detector.py -v

# 50-noise sweep (Item 2 stop-guard).
python scratch/bucket9.1_fp_characterization.py 2>&1 | grep "False positives"
# Expected: "False positives:    0 (0.0%)"

# Multi-planet 50-noise sweep (Item 1 evidence).
python scratch/bucket9.2_multiplanet_fp_characterization.py 2>&1 | grep "Runs with any FP"
# Expected: "Runs with any FP:   0 (0.0%)"

# Final posttest.
python -m pytest tests/ -m "not network and not slow" -v > reports/bucket9.2_posttest.txt 2>&1
echo "exit=$?"
tail -3 reports/bucket9.2_posttest.txt
# Expected: 81 passed, 1 skipped, 33 deselected, 0 failed, exit 0

# Hermeticity check (Item 5 verification).
git status --porcelain logs/experiments.json
# Expected: empty

# Idempotency: run the fast gate a second time.
python -m pytest tests/ -m "not network and not slow" 2>&1 | tail -3
git status --porcelain logs/experiments.json
# Expected: empty
```
