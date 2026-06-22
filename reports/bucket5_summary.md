# Bucket 5 Summary — CI Readiness & Test Infra

**Branch:** `chore/ci-readiness` (off `v.0.0.2`)
**Date:** 2026-06-22
**Commits:** 20 (all on the `chore/ci-readiness` branch, ready for review/merge)

---

## 1. Headline: failure count **10 → 4** (fast gate)

| Metric | Before (Phase 0 baseline) | After (Phase 8 verification) |
|---|---|---|
| Tests collected | 69 | 105 (69 original + 36 new parametrised) |
| Fast gate: failed | 10 | **4** |
| Fast gate: passed | 59 | **68** |
| Fast gate: deselected (network + slow) | 0 | **33** |
| Full suite: failed (CI non-blocking) | n/a | network tests blocked by sandbox timeout (expected; non-blocking in CI) |

### The 4 remaining fast-gate failures (expected per user's choices)

| Test | Cause | Action |
|---|---|---|
| `test_agent_detective.py::test_noise_injection` | Real BLS false-positive in seeded pure noise (`confidence_score ≈ 4.09`); user chose "leave red and document" per the anti-silent-fallback rule | Documented here; flagged for a future signal-detection tuning bucket |
| `test_agent_detective.py::test_panel_routing` | Pre-existing test bug: `file_uploader` mock returns a string, not an `UploadedFile`, so the upload branch never executes and the `Analyze Telemetry & Verify Harmonics` button never appears | Out of scope for bucket 5 (test bug, not infra) |
| `test_ui_flow.py::test_ui_flow` | Pre-existing test bug: uses `at.file_uploader` (does not exist) instead of `at.get("file_uploader")` | Out of scope for bucket 5 (test bug, not infra) |
| `test_workbench_navigation.py::test_workbench_navigation_persistence` | Same pre-existing `file_uploader` mock bug as `test_panel_routing` | Out of scope for bucket 5 (test bug, not infra) |

The 3 pre-existing test bugs were always failing in the full suite (just under the DeltaGeneratorSingleton pollution error); bucket 5's conftest fix unmasked them. The user already noted in the test code that the mocks return a path string; the fix requires a real `UploadedFile` mock (out of bucket 5's scope).

### 9 of the original 10 failures turned green

| Original failure | Fix | Result |
|---|---|---|
| 6 × DeltaGeneratorSingleton (test_panel_routing, test_experiment_history_cycle, test_ui_sync_slider_events, test_ui_dynamic_expansion, test_ui_flow, test_workbench_navigation_persistence) | `tests/conftest.py` autouse function-scoped fixture patches `DeltaGeneratorSingleton.__init__` to reset `_instance` before each test | 3 of 6 pass outright; the other 3 now fail on the pre-existing `file_uploader` mock issue (unmasked by the fix) |
| `test_mathematical_aliasing_stress_test` (KeyError: 0) | Update test assertion: `results[0].get('candidate_1', {})` → `results` (single-dict return shape at `detection.py:183`) | Passes |
| `test_state_binding_safety_verification` (KeyError: 0) | Same fix as above | Passes |
| `test_performance_speed_benchmark` (1.5s budget) | Mark `@pytest.mark.slow`; keep 1.5s budget; excluded from fast gate | Excluded from fast gate (per user choice "Mark @slow only, do not relax") |
| `test_noise_injection` (BLS false-positive in seeded noise) | n/a — real signal-detection concern | Left red per user choice "leave red and document" |

---

## 2. The 4 test-side fixes (Phase 2)

### 2a. `tests/conftest.py` — DeltaGeneratorSingleton reset

The original error was `RuntimeError: DeltaGeneratorSingleton instance already exists!` raised when a second `AppTest.from_file("app.py")` ran in the same process. The singleton is instantiated at the bottom of `streamlit/__init__.py:84` when the module is first imported. A naive `_instance = None` reset BEFORE each test broke the script thread's error-display path (which reads the class variable via `DeltaGeneratorSingleton.instance()`). The fix patches `__init__` to reset `_instance` at the moment a new instance is being created:

```python
def _permissive_init(self, *args, **kwargs):
    DeltaGeneratorSingleton._instance = None
    original_init(self, *args, **kwargs)
```

This is restored to the original `__init__` after each test. **Verified: 3 of 6 DeltaGeneratorSingleton tests now pass outright** (test_experiment_history_cycle, test_ui_sync_slider_events, test_ui_dynamic_expansion). The other 3 fail on the unmasked pre-existing `file_uploader` mock bug.

### 2b. test_bulletproof_detector KeyError:0

Updated two assertion lines (`results[0].get('candidate_1', {})` → `results`) to match the single-dict return shape of `detect_transit_candidate` (confirmed at `astraeus/analysis/detection.py:183`). **Verified: both tests now pass.**

### 2c. test_performance_speed_benchmark → `@pytest.mark.slow`

Added `@pytest.mark.slow` decorator + a comment explaining the hardware-dependent 1.5s budget. Kept the 1.5s budget per user choice. **Verified: test is selected by `pytest -m slow`, deselected by `pytest -m "not network and not slow"`.**

### 2d. Button-label drift

The app's button label is `Analyze Telemetry & Verify Harmonics` (at `ui/pages/detective.py:327` and `:464`; the bucket5 prompt's claim of `:441` was wrong — that line is `if "active_metadata" not in st.session_state:`). Updated the test assertions in `tests/test_agent_detective.py:87,91` and `tests/test_workbench_navigation.py:52,56`. **Verified: the label fix is correct; the underlying `file_uploader` mock bug is a pre-existing issue out of bucket 5's scope.**

---

## 3. Script conversion (Phases 5-6)

### 3a. tests/ diagnostic scripts (6 files)

| File | Disposition | New file | Network? | Marker |
|---|---|---|---|---|
| `tests/system_flight_bench.py` | converted in place (rewrite as 2 tests, one @smoke + one @slow) | `tests/test_system_flight_bench.py` | no | @smoke + @slow (split) |
| `tests/global_matrix_stress_test.py` | converted (parametrize 11 tracks) | `tests/test_global_matrix_stress_test.py` | yes | @network + @slow |
| `tests/solid_matrix_diagnostic.py` | converted (parametrize 12 tracks) | `tests/test_solid_matrix_diagnostic.py` | yes | @network + @slow |
| `tests/pipeline_stress_test.py` | converted (parametrize 2 profiles) | `tests/test_pipeline_stress_test.py` | yes | @network + @slow |
| `tests/debug_metadata_network.py` | converted (single test, lift thresholds to asserts) | `tests/test_debug_metadata_network.py` | yes | @network |
| `tests/trace_download_deadlock.py` | **NOT converted** — diagnostic only (module-level `os._exit(1)` + at-import network call). Moved to `deprecated/trace_download_deadlock.py` per global "never delete, only deprecate" rule. | n/a | n/a | n/a |

### 3b. scripts/manual_tests/ scripts (6 files)

Per the user's "consolidate where overlap exists" choice:

| File | Disposition | New location | Marker |
|---|---|---|---|
| `scripts/manual_tests/test_engine.py` | **consolidated** into `tests/test_nbody_solver.py` (3 new tests for Kepler-90b scenarios via raw `run_stability_integration` state vectors) | bottom of `tests/test_nbody_solver.py` | none (matches file style) |
| `scripts/manual_tests/test_orchestrator.py` | new file (1 test, multi-planet search via `universal_load_lightcurve`) | `tests/test_multi_planet_search_real_data.py` | @network + @slow |
| `scripts/manual_tests/run_test.py` | new file (1 test, same orchestrator + pairwise period-uniqueness check) | `tests/test_multi_planet_search_real_data.py` (same file as test_orchestrator) | @network + @slow |
| `scripts/manual_tests/test_ingest.py` | new file (HAT-P-11 b metadata round-trip) | `tests/test_remote_ingest.py` | @network |
| `scripts/manual_tests/test_fetch.py` | new file (Kepler-90 archive metadata) | `tests/test_remote_fetch.py` | @network |
| `scripts/manual_tests/test_nasa.py` | new file (direct NASA TAP query) | `tests/test_nasa_tap.py` | @network |

**Not consolidated with `tests/test_pipeline_smoke.py`** (test_orchestrator + run_test): that file is synthetic + single-planet + @smoke + no-network; these are real-data + multi-planet + @network/@slow + different code path (detector entry point vs orchestrator). Genuine parallel coverage, not overlap.

### 3c. Assertion criteria inferred from print output (flagged for user confirmation)

Per the bucket5 hard constraint "Never invent a passing assertion for a script whose correct expected behavior is genuinely unclear from reading it":

- `tests/pipeline_stress_test.py` Layer 2-6 asserts (`period > 0`, `depth > 0`, `snr > 0`, `radius > 0`, `vetting_status` non-empty) are **inferred from the original script's success-banners** (e.g. `P={period:.5f} d | depth={depth:.6f} | SNR={snr:.2f}`). The criteria are conservative and reflect what the original script reported as success.

- `tests/test_global_matrix_stress_test.py` Phase 1 `assert st_rad in meta and pl_orbper in meta` is **verbatim from the original assert** (line 113-114 of the original).

- `tests/test_solid_matrix_diagnostic.py` per-layer invariants are **verbatim from the original `ValueError` messages** (e.g. `"Layer 5 planet radius too small: {model_radius:.4f} R_Earth"` → `assert model_radius > 0.1`).

---

## 4. Deps & CI (Phases 3, 4, 7)

### 4a. pytest.ini extension

Added `network:` and `slow:` markers alongside the existing `smoke:` marker. Preserved `addopts = --ignore=deprecated` (Bucket 1's contract).

### 4b. requirements.txt + requirements-dev.txt split

**requirements.txt** now pins 12 runtime deps (was 9). The 3 additions per the import audit:
- `pandas==2.2.3` (used by `astraeus/data/adapter.py`, `astraeus/data/loader.py`, `ui/`, `app.py`)
- `requests==2.32.3` (used by `astraeus/core/lightkurve_client.py:9`, `astraeus/core/nasa_archive.py:3`)
- `emcee==3.1.6` (used by `astraeus/analysis/error_analysis.py` for MCMC)

**requirements-dev.txt** (new file) holds test-only deps:
- `pytest>=8.0,<10`

**The bucket5 prompt's claim that astroquery / batman-package / statsmodels / pytest-mock are also missing is INCORRECT for live code.** Verified via import audit: those imports appear only in `deprecated/` (excluded by `--ignore=deprecated`) or `scratch/` (not collected). They are NOT added.

**Verification caveat:** cannot verify install on a clean venv from this sandbox (no network in restricted env). User should run locally:
```bash
python -m venv .venv-bucket5
.venv-bucket5\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not network and not slow" -v
```

### 4c. .github/workflows/tests.yml

Two-job workflow on `ubuntu-latest` + Python 3.12:

- **`fast-gate`** (default, blocking): runs on every push (all branches) + every PR. Installs runtime + test deps with pip wheel cache. Runs `pytest tests/ -m "not network and not slow" -v --tb=short`. The fast-gate filter preserves the smoke marker (smoke is NOT excluded by `not network and not slow`).

- **`full-suite`** (non-blocking, `continue-on-error: true`): runs on push to main + nightly cron `0 3 * * *`. Same setup. Runs `pytest tests/ -v --tb=short` (no marker filter; may hit network).

YAML validated locally via `import yaml; yaml.safe_load(...)`. No `actionlint` available in this sandbox (state this in summary).

---

## 5. Cross-platform and cross-bucket compatibility

- **Zero hardcoded Windows paths** in live code (per the import audit).
- **Two `sys.platform == 'win32'` branches**: `runs/kepler90_blind_search.py:25` (out of pytest collection scope) and `tests/test_chaos_integration_suite.py:326` (properly guarded with `if sys.platform.startswith("win")` — skips `ctypes.wintypes` on Linux; CI-safe).
- **Zero `subprocess shell=True`** in live code.
- **`pytest.ini`'s `--ignore=deprecated`** is preserved verbatim. The 12 new files in `tests/` (test_engine.py merged into test_nbody_solver.py + test_system_flight_bench.py + test_global_matrix_stress_test.py + test_solid_matrix_diagnostic.py + test_pipeline_stress_test.py + test_debug_metadata_network.py + test_multi_planet_search_real_data.py + test_remote_ingest.py + test_remote_fetch.py + test_nasa_tap.py + conftest.py) are all OUTSIDE the `deprecated/` tree, so collection includes them. The 6 diagnostic scripts in `tests/` + 6 manual_tests scripts + 1 deadlock diagnostic are all INSIDE `deprecated/`, so they're excluded from collection.
- **`.github/` is gitignored** in this repo (verified by `git add` failing without `-f`). The workflow file was added with `git add -f .github/workflows/tests.yml` and committed. This is intentional — we want CI workflows to be tracked.

---

## 6. Risk register

| Risk | Status |
|---|---|
| `pytest.ini` clobbered | Mitigated — extended markers block only, preserved `--ignore=deprecated` |
| Test-side fixes change app behavior | Mitigated — only test files + pytest.ini + requirements*.txt modified |
| Network tests cause flakiness in CI | Mitigated — fast-gate excludes them; full-suite is non-blocking |
| CI fails on first run | Expected for first run (env provisioning); subsequent runs use pip cache |
| 12 new test files in `tests/` overload collection | Verified — collection is clean; no hang (Bucket 0's 2-minute hang is fixed by the conftest) |
| Deprecation moves could lose data | Mitigated — all originals preserved under `deprecated/`, never deleted |

---

## 7. Out of scope (flagged for future buckets)

- **Fixing the BLS false-positive in pure noise** (`test_noise_injection`). This is a real signal-detection concern (BLS finds a peak with `confidence_score ≈ 4.09` in seeded white noise). Tracked for a future signal-detection tuning bucket.
- **Tightening or relaxing the 1.5s budget** for `test_performance_speed_benchmark` and `test_synthetic_pipeline_runtime_budget`. Per user choice, kept as-is; tests are marked @slow and excluded from the fast gate.
- **Fixing the pre-existing `file_uploader` mock bug** in 3 AppTest tests (`test_panel_routing`, `test_ui_flow`, `test_workbench_navigation_persistence`). The mocks return a string instead of an `UploadedFile`; the fix requires real `UploadedFile` mocks. Out of bucket 5's scope.
- **Verifying pip install on a clean venv** — cannot from this sandbox (no network in restricted env). User to run locally per the command in §4b.

---

## 8. Verification commands

```bash
# Fast gate (matches CI default job; ~2 min on this dev box)
python -m pytest tests/ -m "not network and not slow" -v

# Full suite (requires network; ~10+ min; CI runs this non-blockingly)
python -m pytest tests/ -v

# Just smoke tests
python -m pytest tests/ -m smoke -v

# Just network tests
python -m pytest tests/ -m network -v

# Just slow tests (incl. perf budget)
python -m pytest tests/ -m slow -v

# Confirm dep install (recommended first run)
python -m venv .venv-bucket5
.venv-bucket5\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not network and not slow" -v
```

---

## 9. Commit log (20 commits, all on `chore/ci-readiness`)

```
Phase 0:
  chore(ci): add bucket5 pretest baseline

Phase 1:
  docs(ci): add bucket5 discovery and audit report

Phase 2:
  test(infra): add conftest.py to reset Streamlit DeltaGeneratorSingleton
  fix(test): align test_bulletproof_detector with single-dict return shape of detect_transit_candidate
  test(infra): mark performance benchmark as slow and register markers
  fix(test): update button-label assertions to match current app label

Phase 3 (bundled with Phase 2c): see above

Phase 4:
  chore(deps): add missing runtime deps and split into requirements-dev.txt

Phase 5:
  test(bench): convert system_flight_bench.py to pytest with @smoke + @slow split
  test(stress): convert global_matrix_stress_test.py to parametrized pytest
  test(diagnostic): convert solid_matrix_diagnostic.py to parametrized pytest
  test(stress): convert pipeline_stress_test.py to pytest
  test(net): convert debug_metadata_network.py to pytest with timing asserts
  chore(tests): move trace_download_deadlock.py to deprecated/ (diagnostic only)

Phase 6:
  test(nbody): merge test_engine.py Kepler-90b scenarios into test_nbody_solver.py
  test(pipeline): add test_multi_planet_search_real_data.py
  test(net): add test_remote_ingest.py from manual_tests/test_ingest.py
  test(net): add test_remote_fetch.py from manual_tests/test_fetch.py
  test(net): add test_nasa_tap.py from manual_tests/test_nasa.py

Phase 7:
  ci: add GitHub Actions workflow (fast-gate + non-blocking full-suite)

Phase 8 (this report):
  docs(ci): add bucket5 summary report
```
