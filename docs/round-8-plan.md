# Round 8 — close the vetting-override bypass on the load-bearing TLS gate

## Status snapshot (read this first)

- Round 7 closed: BLS fix (adaptive frequency_factor + widened p_max + physical-mask + 5% boundary) merged as `2dc574a` on `v.0.0.2`. Validated on the real 1239.81d / 45,853-cadence Kepler-90 stitch via J7c: b (7.0083d) and c (8.7192d) recovered to 0.003% precision with real TLS validation (`tls_valid=True, SDE=23.91` and `SDE=22.87`).
- Round 7 opened (this round, top priority, ahead of any further perf work): the **vetting-override bypass** at `astraeus/analysis/detection.py:328-329` vs `astraeus/core/orchestrator.py:168` (and `:386` — same check in the daemon worker).
- d (59.7d) and h (331.6d) recovery on the real curve is deferred until the round-8 fix lands. A longer run on the broken override would burn more iteration slots on spurious peaks, not reach d/h — interpret that risk.

## The bug, in one paragraph

`detect_transit_candidate` computes `is_valid = (snr > snr_threshold) and (confidence >= floor) and tls_valid` (the production emission gate, `astraeus/analysis/detection.py:164-168`). When the TLS gate fails, `is_valid=False`. The default `vetting_status` is therefore `'rejected'` (`detection.py:198`). The VettingEngine then runs unconditionally on the same peak (`detection.py:280-334` — see the "run the cross-vetting branches UNCONDITIONALLY" comment at line 288-295 explaining why) and at line 328-329 overrides `vetting_status='Verified Planet Candidate'` whenever the geometric vet returns `Likely Planet`, **with no consultation of `tls_valid`**. The orchestrator's GUARDRAIL 1 at `astraeus/core/orchestrator.py:168` (and `:386` in `_subprocess_search_worker`) reads `vetting_status.startswith("Verified Planet Candidate")` to decide whether to accept and continue iterating. When the gate and the string disagree, the orchestrator listens to the string. Round 3's J2c nested-pool fix specifically built the TLS gate to stop confidently-wrong candidates from being accepted; this is a third-layer bypass of the same shape (ingestion → detection classifier → orchestrator's string-based read of the classifier's output). The same family of failure as every major bug in this project so far.

## Round 8 goal

Close the bypass with a one-line fix + a regression test that turns green, and re-run the J7c real-curve gate end-to-end to confirm d (or h) is recovered now that iteration slots aren't being burned on TLS-rejected spurious peaks.

## Scope (in)

1. Pick the fix location (see "Fix options" below) and apply it.
2. Update both orchestrator call sites (`run_multi_planet_search` at `:168` and `_subprocess_search_worker` at `:386`) if the fix is at the orchestrator level.
3. Remove the `@pytest.mark.xfail` decorator from `tests/test_r8_vetting_override_regression.py` and confirm the test goes green.
4. Add one more regression test that locks the *complement*: an "unconditional Verified" path (e.g. `result['vetting_status'] = "Verified Planet Candidate"` at line 300 for `transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION`) must still be accepted when `tls_valid=True` — i.e. the fix should not over-correct and reject legitimate Verified candidates.
5. Re-run the J7c-style real-curve gate on a properly-budgeted environment (CI runner or longer timeout). The reviewer explicitly noted "Option B is not guaranteed to work as described, because if the vetting override lets spurious peaks like the 489d one consume iteration slots and get accepted, a longer run may accept more spurious 'planets' rather than reaching d/h." After the override fix, the longer run's results are interpretable again. Confirm b, c, d are all recovered with real TLS validation. h is the 5th planet and may or may not be reached at `MAX_SIGNALS=5`; if not, log it as a separate round-9 follow-up.

## Scope (out)

- BLS performance, frequency_factor tuning, p_max cap. The round-7 BLS fix is shipped and validated; do not touch `astraeus/analysis/bls_search.py` in this round.
- TTV analysis, n-body, geometric-validator internals. The fix is at the orchestrator/classifier boundary, not in the classifiers.
- Re-baselining the 4 synthetic calibration curves (10d/2000, 50d/1500, 200d/9795, 1500d/3000). The reviewer approved the round-7 BLS code as-is.
- Auditing every prior-round "Verified Planet Candidate" result for actual `tls_valid`. That's a separate audit, not part of this fix; do it as a round-9 prep task only if needed for the longer J7c run.

## Fix options — pick ONE

The reviewer's commit message for `9721d3b` (round 8 reproducer) listed two options. Choose between them based on the "defense in depth" argument below.

### Option A — fix at the classifier (`detection.py:328-329`)

```python
elif vetting_metrics['vetting_status'] == "Likely Planet" and tls_valid:
    result['vetting_status'] = "Verified Planet Candidate"
```

The classifier can only upgrade to "Verified Planet Candidate" when TLS is valid. The orchestrator's string-prefix check is unchanged and stays clean. **One-line change.** Also add the same `and tls_valid` guard to line 300 (the `transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION` branch) and to line 325 (the "Atmospheric Occultation Detected" branch) for the same reason — all three override paths currently bypass the TLS gate. Line 300 and 325 are listed in the existing test evidence (`grep -n "vetting_status" detection.py` from the round-8 reproducer) so the fix is mechanical.

**Pro:** preserves the load-bearing TLS gate at the layer it was originally built (round 3 J2c). One source of truth for "is this Verified?".

**Con:** the orchestrator's GUARDRAIL 1 is now structurally fragile — any future override path that forgets the `and tls_valid` clause re-opens the bypass. Easy to regress; needs a careful code review on every future VettingEngine override change.

### Option B — fix at the orchestrator (`orchestrator.py:168` and `:386`)

```python
tls_valid = result.get('tls_valid')
if snr < snr_floor or not vetting_status.startswith("Verified Planet Candidate") or tls_valid is False:
    print(f"[Orchestrator] Signal significance floor reached (SNR={snr:.2f}, status='{vetting_status}', tls_valid={tls_valid}). Halting iterative search.")
    break
```

Apply identically at both `run_multi_planet_search` (line 168) and `_subprocess_search_worker` (line 386). **Two-line change** at two sites.

**Pro:** defense-in-depth at the accept path. The orchestrator's GUARDRAIL 1 now reads both the classifier's string and the gate's boolean, so a future VettingEngine override that forgets the TLS guard can't bypass the orchestrator's accept logic. The TLS gate is the orchestrator's concern, which it always should have been.

**Con:** two sites to keep in sync. If a future path adds a third orchestrator entry (e.g. a new daemon worker variant), it must replicate the same check. Mitigated by extracting to a helper (`_is_accepted(result, snr_floor) -> bool`).

### Recommendation

**Option B.** The reviewer's commit message said "(b) is the safer defense-in-depth because it doesn't depend on every VettingEngine override respecting the TLS gate — only on the orchestrator's accept path." That's the right call: the orchestrator's GUARDRAIL 1 is the only place that decides whether to keep iterating, and the load-bearing gate should be enforced there, not at every classifier override site. Pair it with Option A as belt-and-braces if you want to keep the classifier-side guard too — but Option B alone is sufficient and is the primary fix.

## File-by-file plan

### 1. `astraeus/core/orchestrator.py` (Option B primary fix, two sites)

**Site 1: `run_multi_planet_search` (around line 165-170).** Replace the GUARDRAIL 1 read of `vetting_status` to also read `result.get('tls_valid')`. Add a helper `_candidate_accepted(result, snr_floor) -> bool` near the top of the file and call it from both sites, so the two call sites can't drift.

```python
def _candidate_accepted(result: dict, snr_floor: float) -> bool:
    """Production accept predicate for a single detect_transit_candidate
    result. Combines the legacy string-prefix check (vetting_status) with
    the load-bearing TLS gate (tls_valid). Both signals must agree.
    Round 8 fix: the classifier's VettingEngine can override
    vetting_status to 'Verified Planet Candidate*' regardless of tls_valid
    (detection.py:328-329). Listening to the string alone lets TLS-rejected
    candidates through, burning iteration slots. See
    tests/test_r8_vetting_override_regression.py for the contract.
    """
    snr = float(result.get('snr', 0.0))
    vetting = str(result.get('vetting_status', ''))
    tls_valid = result.get('tls_valid')
    return (
        snr >= snr_floor
        and vetting.startswith("Verified Planet Candidate")
        and tls_valid is True
    )
```

Replace the inline check at line 168 with:
```python
if not _candidate_accepted(result, snr_floor):
    print(f"[Orchestrator] Signal floor or vetting/TLS gate failed (SNR={result.get('snr')}, status={result.get('vetting_status')!r}, tls_valid={result.get('tls_valid')}). Halting.")
    break
```

**Site 2: `_subprocess_search_worker` (around line 386).** Identical replacement. Same helper, same call shape.

### 2. `astraeus/analysis/detection.py` (defense-in-depth, optional)

If you also want the classifier-side guard, add `and tls_valid` to the three override sites:
- Line 300: `if transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION:`
- Line 325: `if vetting_metrics['vetting_status'] == "Atmospheric Occultation Detected":` (the inner branch at 325)
- Line 328-329: `elif vetting_metrics['vetting_status'] == "Likely Planet":`

Recommended to **skip this** for the primary round-8 fix (Option B is sufficient and is the reviewer's recommended path). If you do add it, do it in a separate commit so the orchestrator fix is the load-bearing one and the classifier fix is defense-in-depth.

### 3. `tests/test_r8_vetting_override_regression.py` (lock the fix)

Currently `@pytest.mark.xfail(strict=False)` (commit `9721d3b`). After the fix:
- Remove the `pytestmark = pytest.mark.xfail(...)` line at the top of the file.
- Remove the `KNOWN FAILURE` paragraph from the test docstring.
- Run the test in isolation: `python -m pytest tests/test_r8_vetting_override_regression.py -v`. Expect 1 passed in ~20s (TLS-mock path, no real curve).

Add a second test in the same file that locks the complement — the over-correction guard:

```python
def test_tls_valid_candidate_with_verified_string_is_accepted() -> None:
    """The over-correction guard: a real, TLS-validated candidate must
    still come back with vetting_status starting with 'Verified Planet
    Candidate'. The round-8 fix at the orchestrator must not over-correct
    by also rejecting legitimate candidates.
    """
    # Build a synthetic curve with a real planet (same shape as the
    # regression test). Do NOT mock TLS this time — let it run for real
    # so the tls_valid=True path is exercised. The curve is small (200d,
    # 5000 cadences) so TLS finishes in a few seconds.
    rng = np.random.default_rng(seed=20260708)
    t = np.linspace(0, 200.0, 5000)
    flux = 1.0 + 1e-4 * rng.standard_normal(5000)
    period = 10.0
    dur = 0.1
    depth = 1e-3
    t0 = 5.0
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    flux[np.abs(phase) < dur / 2.0] -= depth

    from astraeus.analysis.detection import detect_transit_candidate
    result = detect_transit_candidate(
        time=t, flux=flux, target_name="R8-complement-guard",
        data_source="synthetic", snr_threshold=7.1,
    )
    assert result.get("tls_valid") is True, (
        f"Test setup error: TLS should have validated the strong synthetic "
        f"transit signal. Got tls_valid={result.get('tls_valid')!r}  "
        f"SDE={result.get('tls_sde')}"
    )
    vetting = result.get("vetting_status", "")
    assert isinstance(vetting, str) and vetting.startswith("Verified Planet Candidate"), (
        f"REGRESSION: legitimate TLS-validated candidate tagged as "
        f"vetting_status={vetting!r}. The round-8 orchestrator fix over-"
        f"corrected and is now rejecting real planets."
    )
```

Mark this test `@pytest.mark.slow` only if the TLS run is slow on the synthetic curve; expect ~5–15s, so the default `slow` marker probably doesn't apply. The round-3 `test_j3_orchestrator_e2e_verified.py` uses `@pytest.mark.slow` for a similar TLS-on-synthetic path; mirror that pattern if the runtime exceeds 30s.

### 4. Re-run the J7c gate end-to-end (the deferred d/h check)

The J7c scratch script (`scratch/j7c_real_curve_full_pipeline.py`) is already on disk from round 7. After the fix:

1. Bump `MAX_SIGNALS` from 3 back to 5 (the harness-10-min cap is the only reason it was 3).
2. Re-run on a properly-budgeted environment. CI runner or a session without the 10-min harness limit. Expected wall: 5 iters × ~150s/iter ≈ 12–15 min.
3. The expected outcome with the fix in place:
   - Iter 1: 489.13d spurious peak, `tls_sde=4.22` — the orchestrator's GUARDRAIL 1 now halts (Option B fix: `tls_valid is False` blocks accept). `is_valid=False` confirms the gate fired. No iteration slot burned. No subtract.
   - Iter 1 (re-bumped, search restarts): b at 7.0083d, SDE=23.91, accepted and subtracted.
   - Iter 2: c at 8.7192d, SDE=22.87, accepted and subtracted.
   - Iter 3: d at 59.7d, expected SNR > 10, SDE > 5, accepted.
   - Iter 4: e at 91.9d or f at 124.9d, depending on which wins the post-subtract periodogram. Accept and subtract.
   - Iter 5: h at 331.6d if reached, else next planet. May not reach h in 5 iters; if so, log as round-9 follow-up.
4. Update the verdict text in J7c's output and the result JSON to reflect d-recovered.

## Evidence trail to keep on disk

- `scratch/r8_repro_vetting_override.py` + `scratch/r8_repro_vetting_override_result.json` — the minimal repro. Kept from round 7 (`9721d3b`). Confirmed bug on disk; do not delete.
- `scratch/j7c_real_curve_full_pipeline.py` + `scratch/j7c_real_curve_full_pipeline_result.json` — the orchestrator-style real-curve gate. Kept from round 7 (`2203bc6`). Re-run after the fix; the new result JSON overwrites the old one.
- `tests/test_r8_vetting_override_regression.py` — already on disk (`9721d3b`). Remove the xfail marker after the fix; add the over-correction-guard test in the same file.
- `logs/j7c_run.log` — full stdout from the original J7c run, gitignored. After re-running J7c, write the new log to `logs/j7c_run_r8.log` (also gitignored) so the round-7 and round-8 outputs don't clobber each other.

## Execution order (one suggested order; not strict)

1. Apply Option B to `astraeus/core/orchestrator.py` (one helper + two call sites). Diff should be ~10 lines.
2. Remove `pytest.mark.xfail` from `tests/test_r8_vetting_override_regression.py`. Run the test; expect green.
3. Add the over-correction-guard test in the same file. Run both tests; expect both green.
4. Run the existing BLS regression tests to make sure the orchestrator fix didn't break anything:
   - `python -m pytest tests/test_j1_alias_rejection.py tests/test_j3_bls_single_signal_regression.py tests/test_j3_syn5p_small_recovery.py -v`
   - All should still pass. (None of them exercise the orchestrator loop, so the fix should be transparent to them. If any fail, stop and investigate before continuing.)
5. Bump `MAX_SIGNALS` in `scratch/j7c_real_curve_full_pipeline.py` to 5. Re-run on a properly-budgeted environment. Capture `logs/j7c_run_r8.log` and overwrite `scratch/j7c_real_curve_full_pipeline_result.json` with the new result.
6. If d (and/or h) is recovered with real TLS validation: round 8 is done. Commit with the message template at the end of this plan.
7. If d is not recovered: investigate. The most likely cause is that the post-subtract periodogram after iter 2 (c removed) doesn't surface d's signal cleanly; check whether the orchestrator's "max_signals" budget was actually exhausted (i.e. iter 5 emitted something) or whether the SNR floor triggered an early halt. Do not treat a no-d result as a regression in the fix without evidence.

## Commit message template (for the round-8 fix commit)

```
Fix orchestrator's GUARDRAIL 1: read tls_valid, not just vetting_status

Round 8. Closes the structural bypass of the load-bearing TLS gate
that the round-3 J2c nested-pool fix specifically built to stop
confidently-wrong candidates from being accepted:

  - astraeus/analysis/detection.py:328-329 VettingEngine override sets
    vetting_status='Verified Planet Candidate' for geometric-vet-
    cleared candidates regardless of tls_valid
  - astraeus/core/orchestrator.py:168 (and :386 in the daemon
    worker) GUARDRAIL 1 read
    vetting_status.startswith('Verified Planet Candidate') to decide
    whether to accept and continue iterating
  - When TLS rejects (tls_valid=False) but VettingEngine overrides
    the string, the orchestrator accepted the candidate and subtracted
    it anyway, burning an iteration slot

Round 7 J7c iter 1 was the live real-curve evidence: P=489.13d,
SNR=16.37, TLS correctly said SDE=4.22 < 5.0 (tls_valid=False), but
vetting_status='Verified Planet Candidate (Likely Planet)' and the
orchestrator accepted and subtracted.

The fix introduces a _candidate_accepted(result, snr_floor) helper
that reads both vetting_status.startswith('Verified Planet
Candidate') AND result.get('tls_valid') is True, and uses it at both
GUARDRAIL 1 sites (run_multi_planet_search and the daemon worker
_subprocess_search_worker). One source of truth, two call sites
that can't drift.

Regression test: tests/test_r8_vetting_override_regression.py had a
@pytest.mark.xfail decorator from commit 9721d3b locking the bypass.
Removed the xfail; test goes green. Also added a complement test that
locks the over-correction guard: a real TLS-validated synthetic
candidate must still come back as 'Verified Planet Candidate*' so
the fix doesn't reject legitimate planets.

Re-ran the J7c real-curve gate on the 1239.81d/45,853-cadence
Kepler-90 stitch with MAX_SIGNALS=5. b, c, d [list] recovered with
real TLS validation. d was previously deferred pending this fix.
```

## What the receiving session should NOT do

- Do not touch `astraeus/analysis/bls_search.py` (the round-7 BLS fix). Approved and merged; any change here needs a fresh review cycle.
- Do not change the 4 synthetic calibration curves used to fit the frequency_factor formula. Approved as-is.
- Do not implement Option A as the primary fix. The reviewer's recommendation is Option B; Option A as the primary would re-introduce the structural fragility the review explicitly called out ("doesn't depend on every VettingEngine override respecting the TLS gate — only on the orchestrator's accept path"). If you want belt-and-braces, add Option A as a *secondary* commit, clearly labeled.
- Do not skip the over-correction-guard test. The fix is at the orchestrator's accept path; without the guard, a future refactor that drops the `tls_valid` clause from the helper would silently re-open the bypass.
- Do not treat "d not recovered in the re-run" as a fix failure without evidence. The fix is about the bypass, not about d specifically. d not being reached can also be a real-curve-specific periodogram issue (e.g. d's signal is being masked by something the synthetic stand-in didn't reproduce). Investigate first.

## Where to look in the codebase (line numbers, verified at plan time)

- `astraeus/analysis/detection.py:164-168` — emission gate `is_valid = (snr > snr_threshold) and (confidence >= floor) and tls_valid`
- `astraeus/analysis/detection.py:198` — default `vetting_status = 'candidate' if is_valid else 'rejected'`
- `astraeus/analysis/detection.py:280-334` — unconditional cross-vetting block (the comment at 288-295 explains why it runs unconditionally)
- `astraeus/analysis/detection.py:300` — first Verified override (transit depth < max)
- `astraeus/analysis/detection.py:325` — second Verified override (Atmospheric Occultation Detected)
- `astraeus/analysis/detection.py:328-329` — the bypass: `elif vetting_metrics['vetting_status'] == "Likely Planet": result['vetting_status'] = "Verified Planet Candidate"`
- `astraeus/core/orchestrator.py:159-170` — `run_multi_planet_search` GUARDRAIL 1 (the bypass consumer in the in-process path)
- `astraeus/core/orchestrator.py:379-386` — `_subprocess_search_worker` GUARDRAIL 1 (the bypass consumer in the daemon-worker path; identical check)
- `tests/test_r8_vetting_override_regression.py` — the contract test, currently `@pytest.mark.xfail(strict=False)`
- `scratch/r8_repro_vetting_override.py` + result JSON — the minimal repro, on disk from `9721d3b`
- `scratch/j7c_real_curve_full_pipeline.py` + result JSON — the real-curve gate, on disk from `2203bc6`

## Round-7 commits you'll see when you `git log --oneline -8`

```
9721d3b Add R8 vetting-override bypass reproducer + xfail regression test
e2ee0e8 Add J3 e2e regression tests for orchestrator + BLS single-signal + SYN-5P
2dc574a Fix BLS: adaptive frequency_factor + widened p_max, with physical-mask and 5% boundary check
2203bc6 Add J7 real-curve gate: Kepler-90 (KIC 011442793) measurement evidence
59f171d Add J3 perf-decomposition scratch scripts
a4a1d83 Add e2e test results & profiling for Kepler-90d detection
```

## Round-7 reviewer's three points (in case you don't have the source review)

1. "Approved: commit astraeus/analysis/bls_search.py and tests/test_j1_alias_rejection.py as proposed." — done in `2dc574a`.
2. "Do not close this out as 'fully passed, minor follow-up' though — one finding in this report needs to be escalated, not filed as a separate round-8 nice-to-have." — this is the round-8 plan.
3. "Open the vetting-override bug (detection.py:328-329 vs orchestrator's string-prefix check) as the top-priority round-8 item, ahead of further perf work." — this plan.

Plus, separately, the reviewer's call-out: "Practical implication: every 'Verified Planet Candidate' result from any prior round needs its actual tls_valid value checked directly, not just its status string, before being trusted as fully TLS-corroborated. b and c from this round are fine — you have tls_valid=True and real SDE values in hand. Anything accepted purely by reading the status string in earlier rounds should be spot-checked." This is a round-9 audit, not part of this round's fix.
