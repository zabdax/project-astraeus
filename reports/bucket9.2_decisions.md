# Bucket 9.2 — Decision Gates (Phase 1)

**Branch:** `fix/multi-planet-noise-fp-audit`
**Date:** 2026-06-23
**Phase:** 1 (decision gate — Item 1 only)
**Phase 0 pretest baseline:** (recorded below in §3 before any code change)

This document presents the Item 1 decision-gate finding for Bucket 9.2:
whether the unconditional `DETECTION_CONFIDENCE_FLOOR = 7.0` added in
Bucket 9.1 to `astraeus/analysis/detection.py:48-51` ALSO protects the
multi-planet emission path (`astraeus/core/orchestrator.py:92
run_multi_planet_search`) that the Detective page's "Multi-Planet
Search Deep-Dive" mode takes via `ui/pages/detective.py:284-292`.

**STOP and wait for user approval before executing Items 2-5.**

---

## 1. Where `run_multi_planet_search` lives and what it does

File: `astraeus/core/orchestrator.py:92-261`

```python
def run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1):
    ...
    discovered_planetary_properties = []
    ...
    while len(discovered_planetary_properties) < max_signals:
        ...
        result = detect_transit_candidate(
            time=active_time,
            flux=current_working_flux,
            target_name=target_name,
            data_source=data_source,
            metadata=metadata,
            snr_threshold=snr_floor,         # <-- 7.1 by default
        )
        snr = result.get('snr', 0.0)
        vetting_status = result.get('vetting_status', '')
        ...
        # GUARDRAIL 1 (orchestrator.py:166-169)
        if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate"):
            print("[Orchestrator] Signal significance floor reached ...")
            break
        ...
```

### 1.1 The emission path is delegated to `detect_transit_candidate`

`run_multi_planet_search` does **NOT** do its own BLS search — it calls
`detect_transit_candidate` at line 147 and adds only:

1. A double-guard at line 167 (`snr < snr_floor OR not vetting_status.startswith("Verified Planet Candidate")`).
2. A subtract-and-iterate loop (lines 195-225) so it can find additional planets.
3. A duplicate-period detector (lines 172-187) that re-subtracts signals matching prior periods.
4. A JSON-consolidation step at the end (lines 240-259).

**The actual candidate-emission decision is `is_valid` in `detection.py:48-51`**:

```python
is_valid = (
    best_snr > snr_threshold
    and best_confidence >= DETECTION_CONFIDENCE_FLOOR
)
```

### 1.2 The orchestrator's own guardrail at line 167

The orchestrator adds a SECOND guard after calling detect_transit_candidate:

```python
if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate"):
    break
```

This requires:
- `snr >= snr_floor` (default `snr_floor=7.1`), AND
- `vetting_status.startswith("Verified Planet Candidate")` (a label
  only set inside the `if is_valid:` block at detection.py:122-157
  when `transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION`).

Both conditions require `is_valid=True` upstream.

---

## 2. Item 1 question + answer

> Does `run_multi_planet_search` apply `DETECTION_CONFIDENCE_FLOOR`?

### **YES — transitively, via delegation.**

The `DETECTION_CONFIDENCE_FLOOR` gate is **unconditional** in
`detection.py:48-51` (it does not depend on `snr_threshold`). Every
call to `detect_transit_candidate` from any caller — including
`run_multi_planet_search` at orchestrator.py:147 — applies it.

The orchestrator's own guardrail at line 167 (`snr < snr_floor or
not vetting_status.startswith("Verified Planet Candidate")`) adds a
**second**, stricter check on top:
- It demands `snr >= 7.1` (orchestrator's own default floor), and
- It demands the vetting pipeline has set status to a "Verified
  Planet Candidate" label — which only happens inside the `if
  is_valid:` block, which is itself gated by the confidence floor.

So the multi-planet path has TWO independent guards against noise:
1. **Inherited** (via delegation): `is_valid = (best_snr > snr_threshold) and (best_confidence >= 7.0)`
2. **Native** (orchestrator.py:167): `snr >= 7.1` AND `vetting_status.startswith("Verified Planet Candidate")`

---

## 3. Empirical confirmation — 50-noise FP sweep through `run_multi_planet_search`

Script: `scratch/bucket9.2_multiplanet_fp_characterization.py`
Output: `scratch/bucket9.2_multiplanet_fp_characterization.json`
Run: same noise fixture as the bucket 9.1 single-planet sweep (seed=42
first, then seeds 100..148), but routed through `run_multi_planet_search`
with its default `snr_floor=7.1` and `max_signals=5`.

### 3.1 Headline

| Metric | Value |
| --- | --- |
| **Total realizations** | 50 |
| **Runs producing ≥ 1 candidate** | **0** |
| **False-positive rate (any candidate)** | **0.0%** |
| **Total false candidates emitted** | **0** |
| Elapsed wall time | 61.4 s |

The multi-planet path emits zero false candidates across all 50 noise
realizations — the same realizations that produced a 68% FP rate on the
single-planet path pre-9.1 and 0% post-9.1.

### 3.2 What the orchestrator saw on each run

For every noise realization, the orchestrator iterated exactly ONCE
then broke. The single iteration reported a BLS peak (period
~0.3d-1.4d, SNR ~3-10, vetting_status "Likely Planet" or "Ambiguous/
False Positive"), then the GUARDRAIL 1 at line 167 broke the loop:

- **Either** `snr < 7.1` (the orchestrator's own floor caught it).
- **Or** `vetting_status` did not start with "Verified Planet Candidate"
  (because `is_valid=False` upstream, so the
  `if transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION`
  branch never fired to set that label).

In every one of the 50 runs, at least one of the two conditions held,
so the loop broke and `discovered_planetary_properties` stayed empty.

### 3.3 Pre-9.1 baseline (for comparison, not run in this bucket)

Pre-9.1, `detect_transit_candidate`'s emission gate was just
`is_valid = best_snr > snr_threshold`. The orchestrator's
`snr_floor=7.1` is HIGHER than the original default `snr_threshold=5.0`,
so the orchestrator's own floor alone was borderline protective — but
not unconditional. A noise realization with `snr > 7.1` AND a depth
below the 3% planet-candidate ceiling would have leaked through and
been accepted as a "Verified Planet Candidate" by the orchestrator.

Bucket 9.1's confidence floor plugs that leak.

### 3.4 Key conclusion

The multi-planet path is **already protected** by Bucket 9.1's fix
via delegation. No additional code change is required to defend
this emission path.

---

## 4. Recommendation

### **Option (a): no code change; document the finding.**

Reasoning:

1. **Empirical evidence:** 0/50 FPs on the multi-planet path. Same
   confidence-floor protection that fixed the single-planet path
   transitively applies.
2. **Architectural evidence:** the orchestrator delegates the
   emission decision to `detect_transit_candidate`. The fix lives at
   the right architectural layer (the candidate-emission gate), not
   at the consumer layer (the orchestrator). Adding a redundant gate
   in the orchestrator would be belt-and-suspenders without data
   support.
3. **Bucket protocol constraint:** "Keep the fix minimal and
   well-justified by data. Do not add multiple unrelated checks 'for
   robustness' — each check must be motivated by specific Phase 1.3
   evidence." Adding a duplicate gate here would violate this rule.
4. **Defense-in-depth is already in place:** even WITHOUT the
   inherited confidence floor, the orchestrator's native guardrail
   at line 167 (`snr_floor=7.1` + vetting_status label check) catches
   a large fraction of noise. The inherited floor + the native
   guardrail = two independent gates, not one.

### 4.1 What I will do

1. Update `reports/bucket9.1_summary.md` (or write a new
   `reports/bucket9.2_summary.md`) to document that the multi-planet
   path inherits the floor.
2. **No new code in `astraeus/`.**
3. **No new test file.** The empirical sweep lives in `scratch/`
   (regenerable, matches bucket 9.1's pattern) and the JSON output
   is the primary artifact.

### 4.2 What I will NOT do (per Option (a))

- No code edit to `orchestrator.py`.
- No new test under `tests/` for the multi-planet path. (The
  `test_multi_planet_search_real_data.py` test exists but is
  network-dependent; the unit-level "rejects noise" invariant is
  sufficiently covered by the bucket 9.1 single-planet tests + the
  orchestrator's own existing test suite.)

---

## 5. Files touched in Phase 1

- `reports/bucket9.2_decisions.md` — this document (new)
- `scratch/bucket9.2_multiplanet_fp_characterization.py` — new diagnostic
- `scratch/bucket9.2_multiplanet_fp_characterization.json` — new diagnostic output

No other files modified. No code touched. Items 2-5 wait for approval.

---

## 6. Verification commands (reproducible)

```bash
# Confirm clean tree (only Phase 1 docs and scratch outputs should be present).
git status

# Inspect the diagnostic JSON.
cat scratch/bucket9.2_multiplanet_fp_characterization.json | python -m json.tool | head -20

# Re-run the sweep.
python scratch/bucket9.2_multiplanet_fp_characterization.py 2>&1 | tail -10
# Expected last line: "Runs with any FP:   0 (0.0%)"
```
