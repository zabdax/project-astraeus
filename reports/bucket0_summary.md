# Bucket 0 — Summary Report

**Branch:** `fix/streamlit-state-diagnostic` (off `v.0.0.2`)
**Date:** 2026-06-22
**Status:** ✅ Complete. Branch left ready for user review/merge. **Not merged to main.**

---

## Root cause confirmed

**RC-1 — Detective target/oute-switch session-state reset was incomplete.**
`ui/pages/detective.py:331-345` (pre-fix) cleared only five keys
(`detective_plot_data, detective_results, fetched_target_data, active_time,
active_flux`) when the user changed the search target. It omitted four keys
that this same module writes on fetch / analysis / stability-check:
`detective_results_list`, `active_metadata`,
`stability_detective_results`, and `stability_detective_config_hash`.

Consequence: after running detection on target **A**, switching the search box
to target **B** left A's metrics (period / stellar radius / transit depth in
the "Target Discovery Confirmation" card, plus the multi-planet candidate
ledger) visible for B until B's own fetch + analysis completed. Because the
physics functions (`detect_transit_candidate`,
`run_multi_planet_search`, `run_stability_integration`) are **fully stateless**
(verified — all accumulators are local; no module-level mutable state), the
UI-layer key omission was the *only* path by which stale results could appear
through the UI. This matched the reported symptom ("physics correct
standalone, wrong/stale through the UI").

A secondary variant: the reset fired only on *target* text change, never on
*data route* change, so switching Kepler → TESS for the same target left a
display/data mismatch.

---

## Exact changes made (commits on this branch)

| Commit | Subject | Files |
|--------|---------|-------|
| `4e1bafd` | docs(bucket0): add pretest baseline and Phase 1 diagnostic findings | `reports/bucket0_pretest_baseline.txt`, `reports/bucket0_baseline_note.txt`, `reports/bucket0_diagnostic_findings.md` |
| `8ba445b` | fix(detective): invalidate all result session keys on target/route switch | `ui/pages/detective.py` |

**Total application-code change:** one file, one site
(`ui/pages/detective.py`, the target/route invalidation block). The fix:
- Reset now fires when **either** the target text **or** the `data_route`
  changes (previously target-only).
- The reset key list now covers every key the module writes, including the
  four previously-omitted keys.
- Tracks `last_route` alongside `last_target`.
- Uses `st.session_state.pop(key, None)` (idiomatic, no KeyError risk).

**No file was deleted, renamed, or moved.** **No file under `astraeus/core/`
or `astraeus/analysis/` was modified** (verified: `git diff --name-only
v.0.0.2..HEAD` lists only `reports/*` and `ui/pages/detective.py`).

---

## What was tested and how

1. **Phase 0 baseline** — `python -m pytest tests/ -v` → **10 failed, 51
   passed** (saved to `reports/bucket0_pretest_baseline.txt`).
2. **Phase 2 standalone physics verification** — ran the stateless-engine
   test set (`test_physics`, `test_transit_model`, `test_orbital_models`,
   `test_nbody_solver`, `test_mcmc`, `test_synthetic_simulation`,
   `test_preprocessing`) after the fix → **31/31 passed**. Confirms the fix
   did not touch any physics behavior.
3. **Phase 3 full suite** — `python -m pytest tests/ -v` → **10 failed, 51
   passed** (saved to `reports/bucket0_posttest.txt`). **Failing set is
   byte-for-byte identical to baseline** (`diff` of the `FAILED` lines shows
   no differences). Zero regression.
4. **App load check (headless)** — `AppTest.from_file("app.py").run()`
   loads with no exception (`at.exception` is an empty `ElementList`), both
   before and after the fix.

### Runtime caveat (stated per "no silent fallbacks" rule)
**`streamlit run app.py` was NOT exercised in an interactive browser.** This
is a headless sandbox with no display server. The reproduction of the
stale-result *mechanism* is therefore **static + session-state-trace
confirmed** (line-precise proof in
`reports/bucket0_diagnostic_findings.md` §2 RC-1), and the app's ability to
*load and route* was confirmed via `streamlit.testing.v1.AppTest`. The actual
fix is **applied per static analysis; the interactive click-through is
runtime-unverified** and should be confirmed by the user with the manual steps
below.

### Collection
`pytest tests/` collection completes cleanly (61 tests collected). No hang.

---

## Why 6 baseline tests still fail (on-topic context, NOT fixed by this bucket)

These were failing **before** this bucket and are failing identically **after**.
They are documented root causes RC-2 and RC-3, both **out of scope** for this
bucket:

- **RC-2 (`RuntimeError: DeltaGeneratorSingleton instance already exists!`):**
  affects `test_panel_routing`, `test_experiment_history_cycle`,
  `test_ui_sync_slider_events`, `test_ui_dynamic_expansion`, `test_ui_flow`,
  `test_workbench_navigation_persistence`. Proven to be **cross-test
  singleton pollution inside Streamlit's `AppTest`** (not app code):
  `test_experiment_history_cycle` PASSES in isolation and in small groups but
  FAILS with this error only in the full suite. A correct fix is a dedicated
  test-infra change (e.g. a `conftest.py` session fixture resetting the
  singleton) and belongs in a separate test-hygiene bucket — **`tests/` is
  out of scope here.**
- **RC-3 (button label drift):** `test_agent_detective.py`,
  `test_workbench_navigation.py` look for a "Run Detection" button; the app
  labels it "Analyze Telemetry & Verify Harmonics". Test-side fix, out of
  scope.
- The 3 `test_bulletproof_detector` failures (timing 4.8 s vs 1.5 s target;
  aliasing; state-binding) and `test_noise_injection` (BLS finds a candidate
  in seeded pure noise) are **physics/benchmark** issues, also out of scope
  for this UI/state bucket.

---

## Needs further investigation (flagged, NOT fixed)

- **RC-2 / RC-3:** recommend a follow-up **test-hygiene bucket** to (a) add a
  `conftest.py` fixture that resets the Streamlit DeltaGenerator singleton
  between `AppTest` runs, and (b) reconcile the "Run Detection" vs
  "Analyze Telemetry & Verify Harmonics" button label in the affected tests.
  Do NOT attempt either from this bucket — both touch `tests/`, which is
  explicitly out of scope here.
- **`astraeus/core/ingestion.py:219`** — the `@st.cache_data` decorator is
  re-applied to a freshly-defined inner function on every call. Behaviour is
  correct and the cache key (`target_name, mission`) fully captures the true
  inputs, so this is a fragility/idiom nit, not a bug. Out of scope
  (`astraeus/core/`). Worth tidying in a core-layer bucket.

---

## Exact commands to verify this yourself

```bash
# 1. Get on the branch
git checkout fix/streamlit-state-diagnostic

# 2. Confirm no physics regression + full suite matches baseline (10 failed / 51 passed)
python -m pytest tests/ -v

# 3. Standalone engine tests (should be all-pass)
python -m pytest tests/test_physics.py tests/test_transit_model.py tests/test_orbital_models.py tests/test_nbody_solver.py tests/test_mcmc.py tests/test_synthetic_simulation.py tests/test_preprocessing.py -v

# 4. Launch the app
streamlit run app.py
```

### Manual reproduction to confirm the RC-1 fix (interactive browser):
1. Open the app → sidebar → **Detective**.
2. Type a target (e.g. `Kepler-90`) → click **Fetch Target Metadata** →
   click **Analyze Telemetry & Verify Harmonics**. Note the period / stellar
   radius / transit depth shown in the "Target Discovery Confirmation" card
   and any multi-planet candidates.
3. Change the search box to a **different** target (e.g. `TRAPPIST-1`) — do
   **not** re-run analysis yet.
4. **Expected (post-fix):** the previous target's metrics/candidate ledger are
   cleared (the card and ledger area reset to the "awaiting fetch" state).
   **Pre-fix:** A's numbers would still be shown for B.
5. Fetch + analyze B; switch the **Data Route** dropdown (Kepler → TESS) for
   the same B without re-running. **Expected (post-fix):** the stale route's
   fetched data is invalidated rather than lingering under the new route label.

> If step 4/5 do not behave as described in your environment, that is the
> runtime-unverified portion — report it and the static proof in
> `reports/bucket0_diagnostic_findings.md` §2 should be re-examined.
