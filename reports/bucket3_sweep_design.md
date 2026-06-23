# Bucket 3 — Completeness Sweep Discovery Report

**Date:** 2026-06-23
**Branch:** `feature/completeness-sweep`

---

## 1. Existing primitive inventory

### 1.1 `SyntheticTransitScenario`
Frozen dataclass at `astraeus/simulation/synthetic.py:20`. Fields: `duration`,
`period`, `eccentricity`, `radius_ratio`, `snr`, `samples`, `seed`,
`stellar_radius`, `semi_major_axis`, `inclination`. Validation in
`_validate_scenario` requires `radius_ratio in (0, 1]` and `samples >= 2`.

### 1.2 `LightCurveSeries`
Frozen dataclass at `astraeus/simulation/synthetic.py:44`. Fields:
`time_days`, `theoretical_flux`, `observed_flux`. `residuals` is a derived
property.

### 1.3 `run_injection_recovery`
Signature at `astraeus/simulation/synthetic.py:131`:
`run_injection_recovery(time, flux, injected_period, injected_r_ratio, injected_b, injected_epoch, known_planets=None, metadata=None)`.

**Recovery criterion:** `|recovered_period - injected_period| / injected_period <= 0.01`
(1% relative tolerance — line 250). Runs a focused **5%-band raw BLS search** via
`astropy.timeseries.BoxLeastSquares`, **NOT** the full pipeline.

After Task 1 the return dict carries: `signal_recovered`, `period_error_delta`,
`snr_attenuation`, `recovered_period`, `recovered_snr`, **`recovered_depth`** (new),
`injected_snr`.

### 1.4 Existing test coverage
`tests/test_synthetic_simulation.py` (4 tests) covers shape, transit dips,
residuals, and sample-count validation. It does NOT exercise
`run_injection_recovery`. No new test in the sweep layer duplicates that
coverage; the new file `tests/test_completeness_sweep.py` is purely about the
sweep layer.

---

## 2. Critical finding — full pipeline vs raw BLS

`run_injection_recovery` measures "can BLS find the period within 1%". It does
NOT call `detect_transit_candidate`. The full pipeline (`detect_transit_candidate`
in `astraeus/analysis/detection.py:19`) adds: detrending, geometric validation,
statistical vetting (`vet_transit_shape`), physical-property derivation,
secondary-eclipse detection, and TTV calculation — and returns a boolean
`candidate_found` plus `vetting_status`.

**Implication for the sweep:** the bucket's `use_full_pipeline` flag toggles
between two recovery semantics. The default (`False`, BLS-only) is fast and
useful for sensitivity analysis; `True` measures the more interesting
question "did the pipeline correctly classify this as a planet candidate?".
Both metrics are exposed separately in `CompletenessSweepResult`.

**Edge case observed during this measurement:** at SNR=50, radius_ratio=0.05,
period=10 d (90 d baseline), `recovered_period = 9.8904`, just **outside** the
1% tolerance (`|9.8904 − 10.0| / 10.0 = 1.096%`). The recovery rate in the
sweep at this cell will be ~50%, not 100%, even though BLS clearly found the
correct signal — it just landed slightly off-grid. This is a known property
of the existing 1% criterion (see `astraeus/simulation/synthetic.py:250`) and
the sweep faithfully reports it; the user can configure a stricter criterion
in a future bucket if needed.

---

## 3. Per-cell cost measurement

Script: `scratch/bucket3_cell_timer.py` (deleted after run).

Test cell: period=10 d, radius_ratio=0.05, snr=50, samples=4000, duration=90 d,
impact=0.3, epoch=45 d.

```
per-injection: 5.677s
full-cell at n=10: 56.771s
signal_recovered=False ; recovered_period=9.8904 ; recovered_depth=0.028173
```

**Initial spec defaults** (8 × 6 × 5 cells × 10 injections = 2 400 BLS runs):
**~3.8 hours** — over budget per the bucket's "do not ship a default that
takes hours to run" constraint.

**Revised defaults** (commit `0ec3fb6` + later defaults update):
- `period_count`: 8 → **4**
- `radius_ratio_count`: 6 → **3**
- `snr_values`: 5-element tuple → **3-element `(10.0, 30.0, 100.0)`**
- `n_injections`: 10 → **5**

New default grid: **4 × 3 × 3 = 36 cells × 5 injections = 180 BLS runs**
⇒ **~17 minutes** wall-clock at the measured 5.7 s/injection.

This trades a coarser grid for fast iteration. Users wanting higher
resolution can configure a larger sweep explicitly (the `CompletenessSweepConfig`
constructor accepts any combination of values).

---

## 4. Cache-key & ledger pattern

Existing pattern in `astraeus/analysis/logging.py`:
`generate_dataset_hash(metadata) = sha256(json.dumps(metadata, sort_keys=True, default=str))`.

The sweep's `_compute_config_hash` and `_compute_cell_hash` use the same
convention. Atomic write (`temp_path → os.replace`) matches
`ExperimentLedger.log_candidate` at `astraeus/analysis/logging.py:108-117`.

The cell hash includes `seed` so different master seeds produce distinct cache
entries — sharing a cache across master seeds would silently give wrong
answers.

---

## 5. Output location

`outputs/completeness_sweeps/<config_hash>/{config.json, manifest.json,
result.json, cells/<cell_hash>.json, heatmap.png, snr_slope.png}`. Mirrors the
existing `outputs/kepler90_blind_search/` pattern.

---

## 6. Reporting integration

`generate_academic_report` is locked to a `{star_id, candidates: [...]}` schema
by `_validate_schema` (line 88-99 of `astraeus/analysis/reporting.py`).
Completeness data does not fit this schema (it is a grid of metrics, not a
star+candidates report). New function `generate_completeness_report` returns a
JSON `dict` (not a PDF) so a future bucket can add PDF rendering.

---

## 7. Spec updates from this discovery

- `docs/superpowers/specs/2026-06-23-completeness-sweep-design.md` §2.1 — defaults revised as in §3 above.
- No other spec changes.