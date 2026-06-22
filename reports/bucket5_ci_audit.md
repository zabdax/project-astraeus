# Bucket 5 CI Audit — Discovery Findings

**Branch:** `chore/ci-readiness` (off `v.0.0.2`)
**Date:** 2026-06-22
**Baseline:** `reports/bucket5_pretest_baseline.txt` — **10 failed, 59 passed** (matches expected set)

This document consolidates the three Phase-1 discovery passes (script audit, test-failure audit, dep/CI audit) and is the basis for the Phase 2-7 execution plan. It is a read-only artifact: no code changes follow from it directly.

---

## 1. Test failure inventory (10 / 59 → target 1)

### 1.1 DeltaGeneratorSingleton pollution (6 tests)

`RuntimeError: DeltaGeneratorSingleton instance already exists!` raised at `streamlit/delta_generator_singletons.py:74` when `AppTest.from_file("app.py").run()` is called more than once in the same process. Each `AppTest` session instantiates a `DeltaGeneratorSingleton` that is not torn down at process exit; a second `AppTest` in the same process trips the singleton guard.

**Affected tests** (the prompt's per-test file names were wrong; the actual locations are below):

| Test | File:line | AppTest timeout |
|---|---|---|
| `test_panel_routing` | `tests/test_agent_detective.py:53` | 60 s |
| `test_experiment_history_cycle` | `tests/test_experiment_history.py:9` | 60 s |
| `test_ui_sync_slider_events` | `tests/test_lab_realtime.py:40` | 120 s |
| `test_ui_dynamic_expansion` | `tests/test_multi_planet_scaling.py:10` | 120 s |
| `test_ui_flow` | `tests/test_ui_flow.py:5` | 60 s |
| `test_workbench_navigation_persistence` | `tests/test_workbench_navigation.py:6` | 60 s |

All 6 tests construct `AppTest.from_file("app.py", ...)` directly inside the test body (not in a fixture). Cross-referenced with `reports/bucket0_diagnostic_findings.md §4 RC-2`: confirmed cross-test pollution, not app code. **Fix: function-scoped autouse fixture in `tests/conftest.py` that resets `DeltaGeneratorSingleton._instance = None` before AND after each test.**

### 1.2 test_bulletproof_detector failures (3 tests)

`tests/test_bulletproof_detector.py` (96 lines). Two classes of failure:

- **`test_mathematical_aliasing_stress_test` and `test_state_binding_safety_verification`** fail with `KeyError: 0` at lines 64 and 84:
  ```python
  result = results[0].get('candidate_1', {}) if results else {}
  ```
  This was written against a stale multi-iteration-list contract. `detect_transit_candidate` actually returns a **flat dict** (confirmed at `astraeus/analysis/detection.py:183`: `return candidates[0]['candidate_1'] if candidates else {}`). **Fix: change to `result = results if results else {}`. Do NOT change the function's return shape — the orchestrator, the detective page handler, and ~6 other test files depend on it (see callers table below).**

- **`test_performance_speed_benchmark`** fails with a 1.5s budget; actual runtime 2.6-4.4s on this hardware. Per the user's "Mark @slow only" choice: add `@pytest.mark.slow` decorator and a comment; keep the 1.5s budget. Test stays red on full-suite runs; fast gate (which excludes `@slow`) skips it.

#### detect_transit_candidate return-shape callers (do not change)

| File:line | Usage |
|---|---|
| `astraeus/core/orchestrator.py:147` | `result.get('snr', 0.0)`, `result.get('vetting_status', '')`, etc. — dict access |
| `ui/pages/detective.py:299,305-309` | Defensive `isinstance(results, list) and len(results) > 0` check; falls back to dict |
| `tests/test_pipeline_smoke.py:49` | Dict access (passes) |
| `tests/test_vetting_threshold_hardening.py:220,264,287,320` | Dict access (passes) |
| `tests/test_agent_detective.py:18,47` | `results.get('is_candidate', ...)` — dict access |
| `tests/global_matrix_stress_test.py:127,178,222` | Dict access |
| `tests/pipeline_stress_test.py:190,216` | Dict access; comment on line 216 explicitly says "detect_transit_candidate returns a flat dict for the best candidate" |
| `tests/system_flight_bench.py:44` | Dict access |
| `tools/diagnostics/ultimate_stress_test.py:952` | Dict access |

### 1.3 Button-label drift (2 tests)

Tests look for button `"Run Detection"`. The app's actual button label is `"Analyze Telemetry & Verify Harmonics"`, present at `ui/pages/detective.py:327` (uploaded-data path) and `:464` (target-fetch path). **The prompt's claim of `detective.py:441` is wrong**; line 441 is `if "active_metadata" not in st.session_state:`.

| File:line | Current code |
|---|---|
| `tests/test_agent_detective.py:87` | `if "Run Detection" in btn.label:` |
| `tests/test_agent_detective.py:91` | `assert run_btn is not None, "Run Detection button not found"` |
| `tests/test_workbench_navigation.py:49` | Comment: `# 3. Run Detection (file is already 'uploaded' via mock)` |
| `tests/test_workbench_navigation.py:52` | `if "Run Detection" in btn.label:` |
| `tests/test_workbench_navigation.py:56` | `assert run_btn is not None, "Run Detection button not found."` |
| `tests/test_ui_flow.py:42` | `if "Simulate" in btn.label or "Load Uploaded" in btn.label or "Run Detection" in btn.label:` (fallback only; test does not block on this) |

**Fix:** update `tests/test_agent_detective.py:87,91` and `tests/test_workbench_navigation.py:52,56` to the new label. (These tests will only pass once the conftest fixture is in place; order the button-label commit AFTER 2a.)

### 1.4 test_noise_injection (1 test) — honest investigation, do NOT silence

`tests/test_agent_detective.py:8-22`:
```python
def test_noise_injection():
    time = np.linspace(0, 10, 500)
    np.random.seed(42)
    flux = 1.0 + np.random.normal(0, 0.01, 500)
    results = detect_transit_candidate(time, flux, snr_threshold=5.0)
    assert results.get('is_candidate', results.get('candidate_found')) is False, "Expected no candidate to be found for pure noise"
```

**What actually happens** (per `reports/bucket7_pretest_baseline.txt:86-92`):
```
E       AssertionError: Expected no candidate to be found for pure noise
E       assert True is False
E        +  where True = {'candidate_found': True, 'confidence_score': 4.086090680685773, 'delta_chi2_u': 0.0002665166585847159, 'delta_chi2_v': 4.811314653365567e-05, ...}.get('is_candidate', True)
```

`detect_transit_candidate` returns `candidate_found: True` with `confidence_score: 4.086`. The BLS search finds a spurious peak in white noise that crosses the `snr_threshold=5.0` gate. **This is a real signal-detection concern, not a test artifact.** Per the prompt's hard-constraint rule "no silent fallbacks" and the user's "leave red and document" choice, do NOT mark `@pytest.mark.xfail` and do NOT relax the noise floor. Leave red; document the root cause in `reports/bucket5_summary.md` and flag for a future signal-detection tuning bucket.

---

## 2. Diagnostic + manual script inventory (12 files)

### 2.1 `tests/` diagnostic scripts (6 files)

| File | Asserts? | Network? | Module-level network? | Convert? | Notes |
|---|---|---|---|---|---|
| `tests/pipeline_stress_test.py` (315 lines) | partial (L1 only) | yes | no | yes | needs Layer 2-6 asserts added (criteria inferred from printed output) |
| `tests/global_matrix_stress_test.py` (289 lines) | yes | yes | no | yes | drop Phase 1 < 1.5s timing flake rule (flagged in source) |
| `tests/solid_matrix_diagnostic.py` (440 lines) | via `ValueError` | yes | no | yes (best) | 12 tracks (3×4), pre-written assertion text in the ValueError messages |
| `tests/system_flight_bench.py` (119 lines) | yes | no | no | yes (best) | self-contained, deterministic, no network — strongest candidate |
| `tests/debug_metadata_network.py` (167 lines) | no | yes | no | partial | lift 4s/milestone + 1MB payload thresholds to asserts |
| `tests/trace_download_deadlock.py` (70 lines) | no | yes | **YES** | **NO** | module-level body; `os._exit(1)` on timeout; diagnostic only — move to `deprecated/` |

### 2.2 `scripts/manual_tests/` scripts (6 files, Bucket 7 handoff)

| File | Asserts? | Network? | Module-level network? | Convert? | Notes |
|---|---|---|---|---|---|
| `run_test.py` (71 lines) | no (manual dup check) | yes | **YES** | yes | wrap module-level body; add `if __name__ == "__main__":` guard; uniqueness check is a real testable invariant |
| `test_engine.py` (226 lines) | via `sys.exit` | no | no | yes (best) | N-body core engine scenarios (Earth-Sun, Kepler-90b hi-res, forced blowup); strip `sys.exit`; **merge into `tests/test_nbody_solver.py`** per consolidation choice |
| `test_orchestrator.py` (51 lines) | no | yes | no | yes | already has `if __name__ == "__main__":`; consolidate into new `tests/test_multi_planet_search_real_data.py` |
| `test_ingest.py` (14 lines) | no | yes | **YES** | yes | wrap module-level body; add `if __name__ == "__main__":` guard |
| `test_fetch.py` (8 lines) | no | yes | **YES** | yes | wrap module-level body; add `if __name__ == "__main__":` guard |
| `test_nasa.py` (13 lines) | no | yes | **YES** | yes | wrap module-level body; add `if __name__ == "__main__":` guard |

### 2.3 Files with module-level network I/O (require wrapping before pytest can import them)

1. `tests/trace_download_deadlock.py` — entire body is module-level; **importing = triggering the network**. Cannot be imported by pytest without restructuring.
2. `scripts/manual_tests/run_test.py` — entire body is module-level.
3. `scripts/manual_tests/test_ingest.py` — entire body is module-level.
4. `scripts/manual_tests/test_fetch.py` — entire body is module-level.
5. `scripts/manual_tests/test_nasa.py` — entire body is module-level.

---

## 3. Dependency gap analysis

### 3.1 Current `requirements.txt` (9 lines, hard-pinned except lightkurve/reportlab)

```
numpy==2.2.6
scipy==1.15.3
matplotlib==3.10.9
astropy==6.1.7
plotly==5.24.1
streamlit==1.41.1
lightkurve>=2.4.0
reportlab>=4.1.0, <4.2.0
kaleido==0.2.1
```

### 3.2 Import inventory (third-party only, live code)

Scanned: `astraeus/`, `ui/`, `app.py`, `route.py`, `tests/`, `scripts/`, `tools/`. Excluded stdlib. Excluded `deprecated/` (already excluded by `--ignore=deprecated`) and `scratch/` (not collected).

**Runtime (imported by `astraeus/`, `ui/`, or `app.py`):**

| Module | Status | Action |
|---|---|---|
| `numpy`, `scipy`, `matplotlib`, `astropy`, `plotly`, `streamlit`, `lightkurve` | pinned | keep |
| `pandas` | **MISSING** | **add to requirements.txt** (used by `astraeus/data/adapter.py`, `astraeus/data/loader.py`, `ui/`, `app.py`) |
| `requests` | **MISSING** | **add to requirements.txt** (used by `astraeus/core/lightkurve_client.py:9`, `astraeus/core/nasa_archive.py:3`) |
| `emcee` | **MISSING** | **add to requirements.txt** (used by `astraeus/analysis/error_analysis.py`) |
| `reportlab` | pinned | keep (already optional; `astraeus/analysis/reporting.py` has `try/except` guard) |
| `kaleido` | pinned | keep (already optional; `app.py:140-147` and `astraeus/analysis/reporting.py` have guards) |

**Optional (guarded `try/except` in live code; intentionally NOT in requirements.txt):**

- `wotan` — `astraeus/analysis/detrending.py:3-7`
- `corner` — `astraeus/workflows/pipeline.py:247-257`
- `python-dotenv`, `openai`, `anthropic`, `google-generativeai` — `astraeus/core/llm_gateway.py`

**Test-only (imported ONLY by `tests/`):**

| Module | Status | Action |
|---|---|---|
| `pytest` | **MISSING** | **add to new `requirements-dev.txt`** |
| `pytest-mock` | not used in live code (NOT actually imported) | **do NOT add** |

### 3.3 The prompt's claim correction

The bucket5 prompt at finding #8 claims: "astroquery, batman-package, statsmodels, pytest, pytest-mock, kaleido (pinned but as runtime)" are missing.

**Verification:**
- `astroquery` appears ONLY in `deprecated/astraeus_data_discovery/discovery.py` — already excluded by `pytest.ini`'s `--ignore=deprecated`.
- `batman-package` appears ONLY in `scratch/scratch_batman.py` — not collected.
- `statsmodels` appears NOWHERE in the live code (grep for `^import statsmodels` and `^from statsmodels` returns zero matches).
- `pytest-mock` appears NOWHERE (no `from pytest_mock` or `import pytest_mock` in the live tree).
- `kaleido` IS already pinned (line 9 of `requirements.txt`).

**Net:** the prompt's claim is **incorrect** for live code. Real missing runtime deps are `pandas`, `requests`, `emcee`. Real test-only dep is `pytest`. The corrected plan adds only those four.

---

## 4. pytest.ini current state and extension plan

### 4.1 Current contents (`pytest.ini` lines 1-7, before this bucket)

```ini
[pytest]
markers =
    smoke: fast end-to-end pipeline smoke tests (sub-minute CI gate)
# Exclude the deprecated/ tree from collection. Dead code moved under
# deprecated/ (Bucket 1 onward) is preserved for history but must never run
# as part of the live test suite. See reports/bucket1_orphan_investigation.md.
addopts = --ignore=deprecated
```

### 4.2 Plan: EXTEND, do not replace

Add `network:` and `slow:` markers alongside `smoke:`. Preserve `--ignore=deprecated` in addopts. After this bucket:

```ini
[pytest]
markers =
    smoke: fast end-to-end pipeline smoke tests (sub-minute CI gate)
    network: tests requiring live network access (NASA Exoplanet Archive, MAST)
    slow: long-running tests (stress, bench, multi-minute)
# Exclude the deprecated/ tree from collection. Dead code moved under
# deprecated/ (Bucket 1 onward) is preserved for history but must never run
# as part of the live test suite. See reports/bucket1_orphan_investigation.md.
addopts = --ignore=deprecated
```

### 4.3 conftest.py situation

**No conftest.py exists anywhere in the repo** (verified by globbing `**/conftest.py` — zero matches). We are creating `tests/conftest.py` from scratch.

---

## 5. CI plan

### 5.1 Current state

`.github/` contains only `copilot-instructions.md` (CodeGenome MCP instructions; not CI). No `.github/workflows/`, no `.gitlab-ci.yml`, no `Jenkinsfile`, no `azure-pipelines.yml`, no `.circleci/`, no `.travis.yml`. We are creating CI from scratch.

### 5.2 Python version

README declares `Python 3.10+` minimum. Developer's local environment is `Python 3.12.10`. CI will use `python-version: "3.12"` for consistency with the dev environment (still satisfies the 3.10+ floor).

### 5.3 Platform note

Test suite is **safe to run on ubuntu-latest** with no code changes:
- Zero hardcoded Windows paths (`C:\`, `C:/Users`, etc.) in live code.
- Two `sys.platform == 'win32'` branches: `runs/kepler90_blind_search.py:25` (out of pytest collection scope) and `tests/test_chaos_integration_suite.py:326` (properly guarded with `if sys.platform.startswith("win")` — skips ctypes.wintypes on Linux).
- Zero `subprocess` calls with `shell=True`.
- All `os.path.join` / `pathlib.Path` calls use portable construction (relative paths, `tempfile.gettempdir()`, `os.path.expanduser("~")`).
- All `open()` calls use plain paths.

### 5.4 Two-job workflow design

| Job | Triggers | Markers | Blocking? | Purpose |
|---|---|---|---|---|
| `fast-gate` | every push + every PR | `-m "not network and not slow"` (smoke is NOT excluded) | **YES** (blocks merge) | Default CI gate; offline-friendly; sub-minute |
| `full-suite` | push to `main` + nightly cron 03:00 UTC | (none) | NO (`continue-on-error: true`) | Catches regressions in network/slow tests without blocking PRs |

Both jobs use `ubuntu-latest` + `python-version: "3.12"`. Pip wheel cache via `actions/setup-python@v5` with `cache: pip` keyed off `requirements.txt` + `requirements-dev.txt`.

---

## 6. Cross-platform and cross-bucket compatibility

- `--ignore=deprecated` MUST keep working. Bucket 5 will be moving 6 diagnostic/manual scripts INTO `deprecated/`, but the flag stays as-is. The added tests' file paths in `tests/` do not conflict with anything.
- `pytest.ini` is extended (markers block only); the `addopts = --ignore=deprecated` line is preserved verbatim.
- No app code, physics code, or analysis pipeline behavior is modified. This bucket only changes test infrastructure and CI/deps plumbing.

---

## 7. What the prompt got wrong (corrections applied)

| Prompt claim | Reality | Source |
|---|---|---|
| 5 of 6 DeltaGeneratorSingleton tests are in per-test files like `tests/test_panel_routing.py` | They live in `tests/test_agent_detective.py`, `tests/test_experiment_history.py`, `tests/test_lab_realtime.py`, `tests/test_multi_planet_scaling.py`, `tests/test_ui_flow.py`, `tests/test_workbench_navigation.py` | Live code |
| Button label is at `ui/pages/detective.py:441` | It's at `:327` and `:464`; line 441 is `if "active_metadata" not in st.session_state:` | Live code |
| `detect_transit_candidate` returns a list | It returns a flat dict (line 183: `return candidates[0]['candidate_1'] if candidates else {}`) | Live code |
| Missing deps include `astroquery`, `batman-package`, `statsmodels`, `pytest-mock` | These are NOT imported in live code. The real missing runtime deps are `pandas`, `requests`, `emcee`; the only test-only dep is `pytest` | Import audit |
| `kaleido` is "pinned but as runtime" | It IS pinned, but the codebase uses it as optional via `try/except` guard. It is correctly left in `requirements.txt` (or could be moved; not blocking) | Live code |

---

## 8. Risk register

| Risk | Mitigation |
|---|---|
| Adding `conftest.py` autouse fixture breaks a previously-passing test | Function-scoped; resets a streamlit internal singleton; cannot affect non-AppTest tests. Verified by running `pytest tests/` after adding the fixture. |
| Test noise injection is a real signal-detection issue that we are leaving red | Documented in §1.4 and the bucket5 summary. Will be tracked in the next signal-detection tuning bucket. |
| requirements.txt additions (pandas/requests/emcee) cause version conflicts in CI | Pinned to versions known to be compatible with the existing pins (numpy==2.2.6, scipy==1.15.3, astropy==6.1.7, streamlit==1.41.1). User is asked to run `pip install -r requirements.txt -r requirements-dev.txt` in a clean venv to verify. |
| CI fails on the very first run | The fast-gate job is intentionally scoped (`-m "not network and not slow"`) to be sub-minute and offline. Smoke tests will be the heaviest item. |
| Moving 6 scripts to `deprecated/` makes them undiscoverable | They are still on disk; per the global rule, never delete. Each moves AFTER its new pytest version is verified passing (port → verify → deprecate, as two separate commits). |
| A converted test's assertion criteria are inferred from printed output (not explicit) | Flagged in the bucket5 summary for user confirmation. The hard-constraint rule is "never invent a passing assertion"; the inferred criteria are conservative and may need tuning. |
