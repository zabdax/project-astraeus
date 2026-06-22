# Bucket 6 — End-to-End Pipeline Smoke Test

**Branch:** `test/e2e-smoke` (created from `v.0.0.2`)
**Date:** 2026-06-22
**Status:** ✅ Complete — no regressions, smoke gate runs in ~26 s.

---

## 1. Goal

Add one fast (< 60 s) end-to-end smoke test that runs a **known** synthetic
transit through the real pipeline entry point
(`detect_transit_candidate`), so any future regression in the *pipeline as a
whole* — not just in an individual module — is caught quickly in CI.

---

## 2. What was found (discovery, read-only)

| Item | Finding |
|---|---|
| Pipeline entry point | `astraeus/analysis/detection.py:11` `detect_transit_candidate(time, flux, ...)` → returns a **flat dict** (first candidate), not a list |
| Synthetic ground truth | `astraeus/simulation/synthetic.py` `SyntheticTransitScenario` + `generate_synthetic_transit_series`. Defaults: period **3.0 d**, `radius_ratio=0.1` (→ depth ≈ 0.01), `snr=200`, `samples=4000`, `seed=42`. Exact & reproducible. |
| Reporting | `astraeus/analysis/reporting.py:392` `generate_academic_report(metrics_payload, figures=None)`. Requires `metrics_payload["star_id"]` + `metrics_payload["candidates"]` (list of dicts with `candidate_id/period/snr/depth/epoch`). `reportlab` is installed. |
| Result dict keys | `period_days`, `period`, `orbital_period`, `transit_depth`, `depth`, `vetting_status`, `snr`, `t0`, `duration`, `ttv_data` (a `list`), `periodogram` (`{periods, powers}`), `is_candidate`, physical props, … |
| Pytest config | **None** (`pytest.ini` / `pyproject.toml` / `setup.cfg` / `conftest.py` all absent) → Bucket 5 not done; the `smoke` marker had to be registered here. |
| Baseline suite | `python -m pytest tests/ -v` → **51 passed, 10 failed** (46 s). All 10 failures are pre-existing and unrelated to the analysis pipeline (Streamlit `DeltaGeneratorSingleton` UI errors, performance benchmarks, detective assertions). See `reports/bucket6_pretest_baseline.txt`. |
| Pipeline code touched? | **No.** Hard constraint respected. |
| Network needed? | **No.** Fully offline on synthetic data. |

### Side note (no action taken)
An untracked ~2 GB junk file named `nul` exists in the repo root. It is **not**
part of this bucket, was not created here, and was deliberately left untouched
(not staged, not deleted). Mentioning it so it isn't mistaken for bucket output.

---

## 3. What was changed

Three new files, no existing files modified:

1. **`pytest.ini`** (new) — registers the `smoke` marker only. No `testpaths`,
   no `addopts`, no discovery changes; cannot affect other tests.
   ```ini
   [pytest]
   markers =
       smoke: fast end-to-end pipeline smoke tests (sub-minute CI gate)
   ```

2. **`tests/test_pipeline_smoke.py`** (new) — two `@pytest.mark.smoke` tests
   sharing one cached pipeline run via `functools.lru_cache`:
   - `test_full_pipeline_recovers_synthetic_planet` — period / depth /
     vetting / contract assertions.
   - `test_reporting_does_not_crash_on_minimal_payload` — builds a minimal
     valid `metrics_payload` from the detection result and asserts
     `generate_academic_report` returns a real PDF (`%PDF` magic). Called with
     **no figures**, so no Plotly/Kaleido path is exercised — fully offline.

3. **`reports/bucket6_summary.md`** (this file).

Nothing under `astraeus/` was modified.

---

## 4. Injected truth vs. recovered values

Scenario: `SyntheticTransitScenario(samples=2000)` (samples reduced from the
default 4000 for speed; every other field at default, so `seed=42` keeps the
injected signal exact and reproducible).

| Quantity | Injected | Recovered | Tolerance asserted | Margin |
|---|---|---|---|---|
| Period (days) | 3.0 | **2.99890** | within 1% | 0.037% ✅ |
| Depth (fraction) | 0.01 (= 0.1²) | **0.009265** | factor of 2 (0.005–0.02) | ratio 0.927 ✅ |
| Vetting status | — | **`"Verified Planet Candidate"`** | `startswith("Verified Planet Candidate")` and not `"Binary"` | ✅ |
| Candidate flagged | — | `is_candidate = True` | truthy | ✅ |
| TTV output | — | `list` | `isinstance(..., list)` | ✅ |
| PDF report | — | `b"%PDF-..."` | starts with `%PDF` | ✅ |

### Why these tolerances
- **Period ≤ 1%**: matches the spec's instruction; the empirical error is two
  orders of magnitude tighter (0.037%), so the 1% ceiling is a generous
  regression net, not an over-fit to this machine.
- **Depth within factor of 2**: synthetic noise + the pipeline's detrender make
  a tighter bound fragile (per the spec's own rationale). Factor-of-2 still
  catches a depth-estimator regression (e.g. a 10× or sign-flipped depth).
- **Vetting label**: asserts a planet-candidate outcome and explicitly rejects
  any `"Binary"` label, so a false-positive regression flips the test red.

---

## 5. How it was tested

| Step | Command | Result |
|---|---|---|
| Pre-change baseline | `python -m pytest tests/ -v` | 51 passed, 10 failed (46 s) → `reports/bucket6_pretest_baseline.txt` |
| Smoke gate in isolation (timed) | `pytest tests/test_pipeline_smoke.py -m smoke -v` | **2 passed in 25.5 s** (pytest) / ~29 s real wall incl. interpreter startup |
| Full suite after change | `python -m pytest tests/ -v` | **53 passed, 10 failed** (43 s) → `reports/bucket6_posttest_run.txt` |

### Regression check
The 10 failures after the change are **byte-for-byte the same test IDs** as the
10 pre-existing baseline failures (all UI/benchmark, none in the analysis
pipeline). **+2 new passes, 0 new failures.** No previously-passing test broke.

### Timing breakdown (single run)
- `detect_transit_candidate` on 2000 samples: **~1.53 s**
- `generate_academic_report` (no figures): **~0.13 s**
- The 25.5 s smoke-gate wall time is dominated by pytest collection + the
  `reportlab`/`astropy` imports, not by the pipeline.

---

## 6. Exact command to run just this gate

```bash
pytest tests/test_pipeline_smoke.py -m smoke -v
```

(Or, to run only the detection-core assertion and skip the report check:
`pytest tests/test_pipeline_smoke.py::test_full_pipeline_recovers_synthetic_planet -v`.)

---

## 7. Uncertain / deferred

- **No real bug found** in the pipeline — the smoke test passed first try with
  comfortable margins, so there is nothing to propose as a follow-up fix.
- `samples` was lowered 4000 → 2000 purely for speed (spec step 4). If a future
  maintainer wants even tighter recovery margins at the cost of a few extra
  seconds, restoring `samples=4000` is a one-line change in
  `tests/test_pipeline_smoke.py::_SAMPLES`. Not done here to keep the gate fast.
- The `lru_cache` on `_run_pipeline` means both tests share one detection call;
  if the tests are ever run in parallel-forked mode the cache won't be shared,
  but correctness is unaffected (each worker just re-runs the ~1.5 s pipeline).
- Pre-existing baseline failures (UI/benchmark) are out of scope for this
  bucket and were not investigated.
