# Bucket 3 — Completeness Sweep Summary

**Date:** 2026-06-23
**Branch:** `feature/completeness-sweep`
**Status:** Complete. All phases (0–4) executed; Phase 3 fast-gate green.

---

## 1. What was found (Phase 1)

### 1.1 Existing primitive inventory
- `SyntheticTransitScenario` (frozen dataclass, `astraeus/simulation/synthetic.py:20`) — fields `duration`, `period`, `eccentricity`, `radius_ratio`, `snr`, `samples`, `seed`, `stellar_radius`, `semi_major_axis`, `inclination`.
- `LightCurveSeries` (frozen dataclass, `astraeus/simulation/synthetic.py:44`) — `time_days`, `theoretical_flux`, `observed_flux`, plus a `residuals` property.
- `run_injection_recovery` (`astraeus/simulation/synthetic.py:131`) — takes raw `time`/`flux` arrays plus injected parameters; runs a focused **5%-band raw BLS search** via `astropy.timeseries.BoxLeastSquares`. Recovery criterion: `|recovered_period − injected_period| / injected_period ≤ 0.01` (1% relative tolerance, line 250).
- `tests/test_synthetic_simulation.py` (4 tests) covers shape, transit dips, residuals, sample-count validation. Does NOT exercise `run_injection_recovery`.

### 1.2 Critical: BLS-only vs full-pipeline
`run_injection_recovery` measures "can BLS find the period within 1%". It does **not** call `detect_transit_candidate` (`astraeus/analysis/detection.py:19`). The full pipeline adds: detrending, geometric validation, statistical vetting (`vet_transit_shape`), physical-property derivation, secondary-eclipse detection, TTV calculation, and returns `candidate_found: bool` + `vetting_status: str`.

**Bucket decision:** the sweep exposes `use_full_pipeline: bool` on `CompletenessSweepConfig` and surfaces BOTH recovery semantics as separate, clearly-labeled quantities. Default is `False` (BLS-only). Full-pipeline recovery criterion = strict verdict:
`candidate_found AND |Δperiod|/period ≤ 0.01 AND vetting_status ∈ {"Verified Planet Candidate", "Verified Planet Candidate (Atmospheric Occultation Detected)"}`.

### 1.3 Per-cell cost measurement
Test cell: period=10 d, radius_ratio=0.05, SNR=50, samples=4000, duration=90 d.
- **per-injection:** 5.68 s
- **full-cell at n_injections=10:** 56.77 s
- signal_recovered=False (recovered_period=9.8904, 1.1% off injected 10.0 — just outside the 1% tolerance; faithful behavior of the existing criterion)

**Implication:** the original draft defaults (8 × 6 × 5 × 10 = 2 400 BLS runs) would take ~3.8 hours. Per the bucket's hard constraint "do not ship a default that takes hours to run", defaults were revised.

---

## 2. What was changed (Phase 2)

### 2.1 Source changes
| File | Change |
|------|--------|
| `astraeus/simulation/synthetic.py` | **Additive (1 dict key)** — `run_injection_recovery` return dict gains `recovered_depth: float`. No signature change. |
| `astraeus/simulation/completeness.py` | **New** — `CompletenessSweepConfig`, `CompletenessSweepResult`, `run_completeness_sweep`, private helpers (`_enumerate_cells`, `_run_one_cell`, `_compute_*_hash`, `_atomic_write_json`, `_is_valid_cache_hit`, `_load_cell_data`, `_load_or_init_manifest`, `_atomic_write_manifest`). |
| `astraeus/simulation/__init__.py` | Additive — defensively re-exports the three new symbols. |
| `astraeus/visualization/plots.py` | Additive — `plot_completeness_map(result, output_dir) -> (heatmap_path, snr_slope_path)`. |
| `astraeus/analysis/reporting.py` | Additive — `generate_completeness_report(result, config, fig_paths) -> dict`. |

### 2.2 Test additions (`tests/test_completeness_sweep.py`, 6 tests)
1. `test_small_sweep_returns_expected_shape` — shape (3, 1, 1), recovery_rate in [0, 1].
2. `test_caching_skips_completed_cells` — first run misses=N; second run hits=N.
3. `test_resumability_after_interruption` — monkeypatched crash after cell 4; re-run picks up with cache_hits=4.
4. `test_use_full_pipeline_changes_recovery_semantics` — different `config_hash` per mode; recovery_rate_full ≤ recovery_rate_bls_only.
5. `test_result_to_dict_load_roundtrip` — `save` / `load` preserves all numeric arrays.
6. `test_progress_callback_invoked_per_cell` — callback invoked `total_cells` times with monotonically increasing current.

### 2.3 Scope respected
- `run_injection_recovery`'s signature is **unchanged**; only one additive dict key.
- No Streamlit UI wiring (out of scope per spec §6).
- `generate_academic_report` and `_validate_schema` untouched (completeness data uses a sibling `generate_completeness_report` returning a JSON dict, not a PDF).

---

## 3. Final grid design (revised after cost measurement)

| Field | Default | Rationale |
|-------|---------|-----------|
| `period_count` | **4** | Down from initial draft 8 (cost). |
| `radius_ratio_count` | **3** | Down from initial draft 6 (cost). |
| `snr_values` | **(10.0, 30.0, 100.0)** | Down from initial draft 5-value tuple. |
| `n_injections` | **5** | Down from initial draft 10. |
| `duration_days` | **90.0** | Required `≥ 2 × period_max_days` (validated in `__post_init__`) so every cell has ≥ 2 transits for BLS. |

**Total default grid:** 4 × 3 × 3 = 36 cells × 5 injections = **180 BLS runs** ⇒ **~17 minutes** wall-clock at the measured 5.7 s/injection.

Users wanting higher resolution can configure larger values explicitly:
```python
CompletenessSweepConfig(period_count=8, radius_ratio_count=6, snr_values=(5.0, 10.0, 20.0, 50.0, 100.0), n_injections=10)
```
yields the original 2 400-run grid (~3.8 hours).

---

## 4. Caching & resumability behavior (confirmed)

The integration demo (Task 11) exercised caching across three sequential runs:

| Run | Wall-clock | cache_hits | cache_misses | Notes |
|-----|-----------|-----------|--------------|-------|
| 1 (cold) | 339.3 s | 0 | 18 | Wrote 18 cell JSONs + manifest incrementally. |
| 2 (partial) | 152.0 s | 10 | 8 | Run was interrupted in an earlier attempt, so 10 cells were valid cache hits; 8 were recomputed. |
| 3 (warm) | **0.19 s** | **18** | **0** | **~1750× speedup** over the cold run. |

**Resumability confirmed:** the per-cell JSON writes are atomic (`temp + os.replace`). A crash mid-cell leaves a `.tmp` orphan that the next run ignores (it does not match the valid-cache-hit contract). The next run redoes the cell from scratch and atomically overwrites the orphan.

**Non-destructive invalidation:** if `config_hash` differs between runs (e.g. the user changes a grid dimension), a new `<config_hash>/` subdir is created; old cells are NOT touched.

---

## 5. Sample output (integration_demo, Task 11)

**Sweep config:** 3 × 3 × 2 grid, n_injections=3, seed=42, duration=90 d.
**Artifacts under** `outputs/completeness_sweeps/integration_demo/ea3113c108f210e6156069506fea3ebecbc1554b22fdfa3286709be68d0b5cff/`:

| Artifact | Purpose |
|----------|---------|
| `heatmap.png` | 1×N small-multiples heatmap row (one panel per SNR), period×depth color-coded by recovery rate. |
| `snr_slope.png` | Recovery-vs-SNR line plot at reference period/depth cells; 0.5 reference line. |
| `result.json` | Full `CompletenessSweepResult.to_dict()`. |
| `manifest.json` | Bookkeeping for resumability (`completed_cells`, `last_updated_iso`). |
| `config.json` | Canonical config snapshot (idempotent). |
| `cells/<hash>.json` × 18 | Per-cell results + per-injection records. |

**Summary stats from the demo run:**
```json
{
  "total_cells": 18,
  "overall_recovery_rate": 0.315,
  "mean_period_err_median_across_recovered_cells": 0.0355,
  "worst_performing_cell": {
    "period_days": 0.5, "radius_ratio": 0.0224, "snr": 10.0,
    "recovery_rate": 0.0
  },
  "best_performing_cell": {
    "period_days": 0.5, "radius_ratio": 0.1, "snr": 50.0,
    "recovery_rate": 1.0
  },
  "total_runtime_seconds": 339.26,
  "cache_hits": 0,
  "cache_misses": 18
}
```

The best-performing cell (largest planet at highest SNR, short period) recovers 100% of injections. The worst (smallest planet at lowest SNR) recovers 0%. The grid span is informative.

---

## 6. Reporting integration

- New function: `generate_completeness_report(result, config, fig_paths) -> dict` (`astraeus/analysis/reporting.py`).
- Returns a **JSON dict**, not a PDF — intentionally a sibling to `generate_academic_report` (which is locked to the `{star_id, candidates: [...]}` schema by `_validate_schema`).
- Payload keys: `schema_version`, `generated_at_iso`, `mode`, `config_summary`, `summary_stats`, `per_cell_table`, `figure_paths`.
- Future bucket can build `completeness_report_to_pdf(payload) -> BytesIO` if PDF rendering is needed.

---

## 7. Future UI hook (deferred per spec §6)

The dict return type is exactly what a future Streamlit panel will consume:
```python
# Sketch only — NOT implemented in this bucket
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.visualization.plots import plot_completeness_map
from astraeus.analysis.reporting import generate_completeness_report

cfg = CompletenessSweepConfig(...)
result = run_completeness_sweep(cfg, progress_callback=lambda c, t, _: st.progress(c / t))
heatmap_p, snr_p = plot_completeness_map(result, out_dir)
payload = generate_completeness_report(result, cfg, {"heatmap": heatmap_p, "snr_slope": snr_p})
st.json(payload["summary_stats"])
st.image(str(heatmap_p))
st.dataframe(payload["per_cell_table"])
```
Streamlit wiring is explicitly out of scope for bucket 3.

---

## 8. Acceptance criteria

| Criterion | Status |
|-----------|--------|
| `git status` clean on `feature/completeness-sweep` | ✅ |
| `tests/test_synthetic_simulation.py` passes unchanged | ✅ (4 passed) |
| `tests/test_completeness_sweep.py` (6 tests) passes | ✅ (6 passed) |
| Full suite passed ≥ baseline, failures == 0 | ✅ **91 passed, 1 skipped, 33 deselected** (baseline was 85/1/33; +6 new) |
| Integration run produces heatmap.png, snr_slope.png, result.json, manifest.json, cells/*.json | ✅ (committed in `e3a2d95`) |
| Re-running same config produces `cache_hits == total_cells` | ✅ (18/18 in run 3) |
| `reports/bucket3_summary.md` references actual artifact paths | ✅ (§5 above) |
| No changes to `run_injection_recovery` signature | ✅ (additive dict key only) |
| No Streamlit/dashboard wiring | ✅ |

---

## 9. Verification commands

```bash
# Phase 0 baseline
python -m pytest tests/ -m "not network and not slow" \
    > reports/bucket3_pretest_baseline.txt 2>&1
# Expected: 85 passed, 1 skipped, 33 deselected

# Phase 2 regression gate (after every source commit)
python -m pytest tests/test_synthetic_simulation.py -v
# Expected: 4 passed

# Phase 3 full suite
python -m pytest tests/ -m "not network and not slow" \
    > reports/bucket3_posttest.txt 2>&1
# Expected: 91 passed, 1 skipped, 33 deselected (+6 from bucket 3)

# Phase 3 genuine integration run (3x3x2 = 18 cells, ~6 min cold; <1 s warm)
python -c "
from pathlib import Path
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.visualization.plots import plot_completeness_map
from astraeus.analysis.reporting import generate_completeness_report
cfg = CompletenessSweepConfig(
    period_count=3, radius_ratio_count=3, snr_values=(10.0, 50.0),
    n_injections=3, seed=42,
    cache_dir='outputs/completeness_sweeps/integration_demo',
)
r = run_completeness_sweep(cfg)
out = Path(cfg.cache_dir) / r.config_hash
hm, sn = plot_completeness_map(r, out)
print(generate_completeness_report(r, cfg, {'heatmap': hm, 'snr_slope': sn})['summary_stats'])
"
```

---

## 10. Commits on `feature/completeness-sweep`

| SHA | Subject |
|-----|---------|
| `a97d627` | chore(bucket3): capture Phase 0 baseline test output |
| `82a5f17` | feat(synthetic): expose recovered_depth in run_injection_recovery return |
| `ee1068f` | docs(bucket3): Phase 1 discovery report + revised default grid |
| `c302b3b` | feat(simulation): CompletenessSweepConfig dataclass with validation gate |
| `d111d79` | feat(simulation): CompletenessSweepResult dataclass with to_dict/save/load |
| `9bb04b5` | feat(simulation): run_completeness_sweep core (no caching yet) |
| `9200bb3` | feat(simulation): per-cell caching + atomic manifest + resumability |
| `5abe376` | feat(visualization): plot_completeness_map (heatmap + SNR-slope) |
| `c1fcd18` | feat(reporting): generate_completeness_report (JSON payload, schema-sibling) |
| `a232a7d` | test(sweep): 6 tests + relax dataclass validation to count >= 1 |
| `e3a2d95` | feat(bucket3): integration_demo artifacts (heatmap, snr_slope, 18 cached cells) |

---

## 11. Deferred / out of scope

- **PDF rendering of completeness data** — this bucket returns a JSON dict; a future bucket can add `completeness_report_to_pdf(payload)`.
- **Streamlit UI wiring** — deferred per spec §6 until Buckets 0 and 1 are stable.
- **Parallel cell execution** (joblib / multiprocessing) — the default grid completes in ~17 min serially; parallelism is deferred.
- **Out-of-memory protection under very large `n_injections`** — not addressed in this bucket; documented in spec §5.2.
- **Stricter than 1% period-tolerance recovery criterion** — the existing `run_injection_recovery` tolerance is preserved verbatim. The Phase 1 measurement showed this is sometimes the binding constraint (the 10 d, r=0.05, SNR=50 cell landed at 1.1% off and was not recovered). A future bucket could parameterize the tolerance; out of scope here.

---

## 12. Notes for the user

- The `.genome/` knowledge graph should be refreshed to include the new `astraeus/simulation/completeness.py` module: `codegenome analyze` (or `codegenome evolve --live` for the live server).
- The first integration run took ~6 min cold; subsequent runs with the same config are sub-second thanks to per-cell caching.
- The default grid (`CompletenessSweepConfig()`) is intentionally conservative (36 cells × 5 injections ≈ 17 min). For a publication-grade completeness map, configure a larger grid and let it run overnight — caching means partial results are never lost.