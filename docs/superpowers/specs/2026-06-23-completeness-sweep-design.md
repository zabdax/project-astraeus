# Completeness Sweep — Design Spec

**Date:** 2026-06-23
**Bucket:** 3
**Branch:** `feature/completeness-sweep`
**Status:** Design synthesis — pending user approval before implementation

---

## 0. Context & Motivation

ASTRAEUS already has an injection-recovery primitive (`astraeus/simulation/synthetic.py:131`):
`run_injection_recovery(time, flux, injected_period, injected_r_ratio, injected_b, injected_epoch, ...)`
which performs a single BLS-based recovery of a known synthetic signal and returns a
boolean `signal_recovered` based on a 1% relative-period tolerance. It runs a focused,
narrow-band (5%) BLS search and does **not** invoke the full pipeline
(`detect_transit_candidate` in `astraeus/analysis/detection.py:19`).

The bucket's job is to build a *systematic* completeness sweep on top of this primitive:
a grid (period × depth × SNR) of repeated injections that yields a recovery-rate map.
Because the existing primitive measures "can BLS find the period" and the full pipeline
measures "does the detector + vetting correctly classify it as a Verified Planet Candidate",
the sweep must surface **both** metrics as separate, clearly-labeled quantities.

This spec covers Phase 1–4 of the bucket:

- **Phase 1:** Discovery — what exists today, what cost a single cell carries, what defaults
  are realistic.
- **Phase 2:** Implementation — new module `astraeus/simulation/completeness.py`, additive
  plotting & reporting extensions.
- **Phase 3:** Tests — 6 tests in `tests/test_completeness_sweep.py`, plus a genuine small
  end-to-end integration run.
- **Phase 4:** Summary report — `reports/bucket3_summary.md`.

---

## 1. Architecture & Components

### 1.1 Module split

| File | Role | Modified? |
|------|------|-----------|
| `astraeus/simulation/synthetic.py` | Existing primitive | **Additive (one dict key)** — `run_injection_recovery` return dict gains `recovered_depth: float`. No signature change; no existing caller breaks (return is a dict, not a dataclass; no test destructures it). |
| `astraeus/simulation/completeness.py` | New sweep orchestrator (dataclasses + runner + cell caching) | **New** |
| `astraeus/simulation/__init__.py` | Re-export new public types | Additive |
| `astraeus/visualization/plots.py` | Append `plot_completeness_map` | Additive |
| `astraeus/analysis/reporting.py` | Append `generate_completeness_report` (JSON payload, not PDF) | Additive |
| `tests/test_completeness_sweep.py` | New tests for the sweep layer | **New** |
| `astraeus/simulation/synthetic.py`, `astraeus/analysis/detection.py`, all dashboard / Streamlit / orchestrator code | Untouched | **Unchanged** |

No existing signature or behavior is modified.

### 1.2 Data flow

```
CompletenessSweepConfig
        │
        ▼
run_completeness_sweep(config)
        │
        │ for each (period, radius_ratio, snr) cell:
        │     1. cell_hash = sha256(json({period, radius_ratio, snr, n_injections, seed, use_full_pipeline}, sort_keys=True))
        │     2. if cells/<cell_hash>.json exists & stored config_hash matches → load & skip
        │     3. else: for i in range(n_injections):
        │             curve = generate_synthetic_transit_series(
        │                 per_cell_scenario(seed=config.seed + cell_index * 1000 + i))
        │             if use_full_pipeline:
        │                 candidate = detect_transit_candidate(curve.time_days, curve.observed_flux, ...)
        │                 recovered = (
        │                     candidate["candidate_found"]
        │                     and abs(candidate["period_days"] - period) / period <= 0.01
        │                     and candidate["vetting_status"] in {
        │                         "Verified Planet Candidate",
        │                         "Verified Planet Candidate (Atmospheric Occultation Detected)",
        │                     }
        │                 )
        │             else:
        │                 result = run_injection_recovery(curve.time_days, curve.observed_flux,
        │                                                period, radius_ratio, b, t0, ...)
        │                 recovered = result["signal_recovered"]  # existing 1% tolerance
        │                 # recovered_period / recovered_depth / recovered_snr all logged
        │                 # for per-cell depth_err_median / period_err_median aggregation.
        │     4. aggregate per-cell recovery rate + period/depth error stats + per-injection records
        │     5. atomic write cells/<cell_hash>.json  (temp + os.replace)
        │     6. update manifest.json  (atomic, every cell)
        │     7. progress_callback(cell_idx + 1, total_cells, last_cell_data)
        ▼
CompletenessSweepResult  (with shape, cache_hits, cache_misses, total_runtime_seconds, config_hash)
```

### 1.3 Public types

**`astraeus/simulation/completeness.py`** exposes:

- `class CompletenessSweepConfig` (frozen dataclass)
- `class CompletenessSweepResult` (frozen dataclass, numpy-array-bearing)
- `def run_completeness_sweep(config, *, progress_callback=None) -> CompletenessSweepResult`
- private helpers: `_compute_config_hash`, `_compute_cell_hash`, `_load_cell_cache`,
  `_save_cell_cache`, `_run_one_cell`, `_aggregate_cell_results`,
  `_atomic_write_json`, `_load_or_init_manifest`, `_atomic_write_manifest`.

The simulation package's `__init__.py` re-exports `CompletenessSweepConfig`,
`CompletenessSweepResult`, `run_completeness_sweep`.

---

## 2. Configuration & Result Types

### 2.1 `CompletenessSweepConfig` (frozen dataclass)

| Field | Default | Meaning |
|-------|---------|---------|
| `period_min_days` | `0.5` | Smallest period swept (log-spaced grid). |
| `period_max_days` | `30.0` | Largest period swept. |
| `period_count` | `8` | Number of period grid points (log-spaced via `np.geomspace`). |
| `radius_ratio_min` | `0.005` | Smallest planet/star radius ratio swept. |
| `radius_ratio_max` | `0.10` | Largest radius ratio (hot-Jupiter class). |
| `radius_ratio_count` | `6` | Number of depth grid points (log-spaced). |
| `snr_values` | `(5.0, 10.0, 20.0, 50.0, 100.0)` | SNR enumeration; `len == 1` ⇒ 2D sweep. **Controls the Gaussian noise level of synthetic generation (higher SNR = less noise).** This is **NOT** the BLS-output SNR — it is the injection-level signal quality parameter forwarded to `SyntheticTransitScenario.snr`. |
| `n_injections` | `10` | Noisy realizations per cell. |
| `seed` | `1729` | Master RNG seed. Per-injection seed = `seed + cell_index * 1000 + i`. |
| `use_full_pipeline` | `False` | `False` → `run_injection_recovery` (BLS-only); `True` → `detect_transit_candidate`. |
| `duration_days` | `90.0` | Synthetic baseline. **Validation gate:** must satisfy `>= 2 * period_max_days` so every cell has ≥ 2 transits (BLS requires ≥ 2 for reliable detection; 90 d ≈ 3 × period_max_days yields ≥ 3 transits for the longest-period cells — statistically meaningful). Enforced in `__post_init__`. |
| `samples` | `4_000` | Samples per light curve (matches scenario default). |
| `impact_parameter` | `0.3` | Injected transit geometry, fixed across the grid. |
| `transit_epoch_fraction` | `0.5` | Injected epoch, as a fraction of `duration_days`. |
| `cache_dir` | `"outputs/completeness_sweeps"` | Parent dir; per-sweep subdir = `<cache_dir>/<config_hash>/`. |
| `known_planets` | `None` | Forwarded to `run_injection_recovery` in BLS-only mode. |
| `metadata` | `None` | Forwarded to `run_injection_recovery` (limb darkening, etc.). |

**Validation gate (in `__post_init__`):**

```python
def __post_init__(self) -> None:
    if self.duration_days < 2 * self.period_max_days:
        raise ValueError(
            f"duration_days ({self.duration_days}) must be >= 2 * period_max_days "
            f"({2 * self.period_max_days}) to ensure >= 2 transits per period cell"
        )
```

This prevents future users from silently creating broken configs (a 30-day baseline at
`period_max=30` would yield at most one transit per cell and BLS would return near-zero
recovery rates regardless of depth or SNR — a misleading completeness map).

**Defaults are deliberately conservative.** With period_count=8, radius_ratio_count=6,
snr_values length=5, n_injections=10, the default grid is **8 × 6 × 5 = 240 cells × 10
injections = 2 400 BLS runs**. Phase 1 will time a single cell and may revise the defaults
to fit a "few minutes" budget — but the *contract* above is what the implementation honors.

**Grid spacing:** period and radius_ratio use `np.geomspace` (log-spaced) because
completeness varies over orders of magnitude in those parameters. SNR is enumerated as a
small tuple of canonical values.

### 2.2 `CompletenessSweepResult` (frozen dataclass)

| Field | Shape | Meaning |
|-------|-------|---------|
| `config` | `CompletenessSweepConfig` | The config that produced this result. |
| `config_hash` | `str` (hex) | `sha256` of canonicalized config — also the sweep subdir name. |
| `periods_days` | `(P,)` | Log-spaced grid. |
| `radius_ratios` | `(D,)` | Log-spaced grid. |
| `snrs` | `(S,)` | SNR enumeration. |
| `recovery_rate` | `(P, D, S)` | Fraction of injections recovered in `[0, 1]`. |
| `period_err_median` | `(P, D, S)` | Median `|recovered_period − injected_period|` in days. **`NaN` where `n_recovered < 2`.** |
| `period_err_std` | `(P, D, S)` | Std of the same. **`NaN` where `n_recovered < 2`.** |
| `depth_err_median` | `(P, D, S)` | Median `|recovered_depth − injected_depth|` in fractional units. **`NaN` where `n_recovered < 2`.** |
| `depth_err_std` | `(P, D, S)` | Same. |
| `n_recovered` | `(P, D, S)` `int` | Count of successful recoveries per cell. |
| `cell_runtime_seconds` | `(P, D, S)` | Wall-clock time per cell (cache hits: time to load JSON). |
| `total_runtime_seconds` | `float` | Sweep wall-clock. |
| `cache_hits` | `int` | Cells served from disk cache. |
| `cache_misses` | `int` | Cells actually run. |
| `started_at_iso` | `str` | UTC ISO 8601. |
| `finished_at_iso` | `str` | UTC ISO 8601. |

**Why NaN (not 0) when `n_recovered < 2`?** Reporting and plotting must distinguish
"cell had zero recoveries" from "cell had 1 recovery (no spread to compute)". Plot code
uses `np.nanmean` / masked arrays; test #1 asserts `np.isnan(err_median)` for the
appropriate edge case.

**Methods:**

- `@property shape -> tuple[int, int, int]`
- `to_dict() -> dict` — JSON-serializable view (np → list, NaN → null).
- `save(path) -> Path` — write `to_dict()` to disk (atomic temp+replace).
- `@classmethod load(path) -> CompletenessSweepResult`.

---

## 3. Caching, Resumability & On-Disk Layout

### 3.1 Directory layout

For `config_hash = "a3f2..."`:

```
outputs/completeness_sweeps/
└── a3f2.../
    ├── config.json
    ├── manifest.json
    ├── result.json
    └── cells/
        ├── 1c4d...json
        ├── 2f8a...json
        └── ...
```

**Naming rules:**

- `config_hash = sha256(json.dumps(asdict(config), sort_keys=True, default=str))` — same
  `sort_keys=True, default=str` convention as `generate_dataset_hash`
  (`astraeus/analysis/logging.py:13`).
- `cell_hash = sha256(json.dumps({period, radius_ratio, snr, n_injections, seed, use_full_pipeline}, sort_keys=True))`. The master `seed` is included because different master seeds produce different per-injection noise realizations — sharing a cache across master seeds would silently give wrong answers.
- Cells are flat under `cells/` (no nested dirs) — keeps `os.listdir` cheap; 240 cells
  default is uncluttered.

### 3.2 Per-cell JSON shape

```json
{
  "config_hash": "a3f2...",
  "cell": {
    "period_days": 3.0,
    "radius_ratio": 0.05,
    "snr": 50.0,
    "n_injections": 10,
    "mode": "bls_only"
  },
  "result": {
    "recovery_rate": 0.9,
    "period_err_median": 0.0123,
    "period_err_std": 0.005,
    "depth_err_median": 0.0008,
    "depth_err_std": 0.0003,
    "n_recovered": 9,
    "runtime_seconds": 1.234,
    "injection_records": [
      {"seed": 1729, "recovered": true, "recovered_period": 3.005,
       "recovered_depth": 0.00249, "recovered_snr": 51.2, "vetting_status": "n/a"}
    ]
  },
  "schema_version": 1,
  "written_at_iso": "2026-06-23T15:42:01Z"
}
```

**Why keep per-injection records?** Two reasons: (1) the resumability test (test #3)
needs to confirm that running with the same config reproduces the same per-cell outcomes —
i.e., deterministic per-cell behavior; (2) downstream analysis may want to re-aggregate
or compute different summary statistics without rerunning the sweep. Cost: a few KB per
cell.

**Atomicity:** every write goes through `temp_path = <file>.tmp` → `os.replace(temp_path,
<file>)`. This matches the existing convention in `ExperimentLedger.log_candidate`
(`astraeus/analysis/logging.py:108-117`).

### 3.3 `manifest.json` shape

```json
{
  "config_hash": "a3f2...",
  "total_cells": 240,
  "completed_cells": ["1c4d...", "2f8a...", ...],
  "in_progress_cells": [],
  "started_at_iso": "...",
  "last_updated_iso": "..."
}
```

**In-progress cells** are reserved for a future improvement (long cells that exceed a
configurable timeout). For this bucket, a cell is either "completed" (file present with
matching `config_hash`) or "not started". A cell is removed from `in_progress_cells` if
its `.tmp` is present but the atomic rename never fired (crash recovery: rename
`tmp → final` if both exist and `final` is missing).

### 3.4 Resumability algorithm

```python
def run_completeness_sweep(config, *, progress_callback=None):
    config_hash = _compute_config_hash(config)
    sweep_dir = Path(config.cache_dir) / config_hash
    cells_dir = sweep_dir / "cells"
    _ensure_dirs(sweep_dir, cells_dir)
    _save_config(sweep_dir, config)
    manifest = _load_or_init_manifest(sweep_dir, config_hash, config.total_cells)

    result_grid = _init_empty_arrays(config)
    cache_hits = cache_misses = 0

    for cell_idx, cell_key in enumerate(_enumerate_cells(config)):
        cell_hash = _compute_cell_hash(cell_key)
        cell_path = cells_dir / f"{cell_hash}.json"

        if _is_valid_cache_hit(cell_path, config_hash):
            cell_data = _load_cell_data(cell_path)
            cache_hits += 1
        else:
            cell_data = _run_one_cell(config, cell_key)
            _atomic_write_json(cell_path, cell_data)
            cache_misses += 1

        manifest["completed_cells"].append(cell_hash)
        _atomic_write_manifest(sweep_dir, manifest)
        _populate_grid(result_grid, cell_idx, cell_data)

        if progress_callback is not None:
            progress_callback(cell_idx + 1, config.total_cells, cell_data)

    _atomic_write_json(sweep_dir / "result.json", result.to_dict())
    return result
```

**Cache invalidation:** if a cell file's stored `config_hash` does not match the current
run's `config_hash`, the file is **ignored** (not deleted, not overwritten — left alone as
a historical record). Non-destructive cache policy, consistent with the project's "never
delete code, deprecate instead" ground rule.

**Determinism:** every cell uses `np.random.default_rng(seed + cell_index * 1000 + i)` as
its RNG. The same `(config, period, depth, snr)` always produces the same per-injection
outcomes, so cache hits are guaranteed stable.

---

## 4. Plotting & Reporting Integration

### 4.1 `plot_completeness_map(result, output_dir) -> tuple[Path, Path]`

Appended to `astraeus/visualization/plots.py`. Same style as `plot_synthetic_validation`:
Agg backend, `dpi=200`, `output.parent.mkdir(parents=True, exist_ok=True)`, returns `Path`.

**Output 1: heatmap** — `<output_dir>/heatmap.png`

- `result.snrs.size == 1`: single 2D heatmap of `recovery_rate[:, :, 0]`. Period on x-axis
  (log-scaled), radius_ratio on y-axis (log-scaled), `viridis` colormap, colorbar labeled
  "Recovery rate", title `"Completeness (mode={bls_only|full_pipeline}, n_injections={N})"`.
- `result.snrs.size > 1`: row of small-multiples heatmaps, one panel per SNR value,
  sharing the y-axis range and colorbar scale.

**Output 2: SNR-slope plot** — `<output_dir>/snr_slope.png`

For each `(period, depth)` reference cell on a fixed grid (default: every other period ×
middle depth, max 6 lines), plot `recovery_rate[i, j, :]` vs `result.snrs`. Reference
horizontal line at 0.5 marks half-completeness. Title
`"Recovery vs SNR (reference period / depth cells)"`, legend listing `(P, D)` per line.

Both PNGs returned as `Path` in `(heatmap_path, snr_slope_path)` order.

### 4.2 `generate_completeness_report(result, config, fig_paths) -> dict`

Appended to `astraeus/analysis/reporting.py`. **Distinct** from `generate_academic_report`
— the prompt explicitly says "do not force the existing schema if it doesn't fit
completeness data". This new function returns a **JSON payload** (not a PDF), so it can
be consumed by a future UI panel or piped into a separate PDF-rendering bucket later.

```python
def generate_completeness_report(
    result: CompletenessSweepResult,
    config: CompletenessSweepConfig,
    fig_paths: dict[str, Path],
) -> dict:
    """Produce a JSON-shaped summary of one completeness sweep.

    Returns a dict with keys:
      - schema_version: int (= 1)
      - generated_at_iso: str
      - mode: "bls_only" | "full_pipeline"
      - config_summary: dict (subset of config fields for human readability)
      - summary_stats: dict (overall recovery rate, mean period error across recovered,
                             worst-performing cell, best-performing cell)
      - per_cell_table: list[dict] (one row per cell, formatted for display)
      - figure_paths: dict[str, str] (the PNG paths, relative or absolute)
    """
```

**No `_validate_schema` is run.** This payload is intentionally not a
`generate_academic_report` input — the two are siblings, not parent/child. A future bucket
can write a `completeness_report_to_pdf(payload) -> BytesIO` that consumes this dict if
PDF rendering is needed.

### 4.3 Future UI hook (not built in this bucket)

```python
# Sketch only — not implemented here
payload = generate_completeness_report(result, config, {"heatmap": p1, "snr_slope": p2})
st.json(payload["summary_stats"])
st.image(str(p1))
st.dataframe(payload["per_cell_table"])
```

The Streamlit UI wiring is explicitly out of scope per the bucket's hard constraints.

---

## 5. Tests, Verification & Failure Modes

### 5.1 Test file: `tests/test_completeness_sweep.py`

| # | Test | What it pins |
|---|------|--------------|
| 1 | `test_small_sweep_returns_expected_shape` | A 2×2×1 grid with n_injections=2 → result shape (2, 2, 1); `recovery_rate` in [0, 1]; all numeric arrays finite where `n_recovered ≥ 2`. |
| 2 | `test_caching_skips_completed_cells` | Run sweep A → record `cache_misses`. Run sweep A again with identical config but a fresh `cache_dir` → assert `cache_hits == A.total_cells`. Optionally assert wall-clock of second run < first run × 0.5. |
| 3 | `test_resumability_after_interruption` | Configure 3×3×1 grid. Run with a monkeypatched wrapper that raises after cell 4 is committed. Re-run with identical config → assert `cache_hits == 4` and the second run's aggregated result equals the first run's aggregated result on the cells it did complete (compared cell-by-cell via `cell_hash`-keyed lookup). |
| 4 | `test_use_full_pipeline_changes_recovery_semantics` | Same injected curve, run once with `use_full_pipeline=False` and once with `True`. Assert: (a) BLS-only run produces a result via the 1% tolerance path; (b) full-pipeline run produces a result with a stricter verdict set (typically `recovery_rate_full ≤ recovery_rate_bls_only`); (c) the two modes produce **different** `cell_hash` values for the same (P, D, SNR) cell so cache keying is mode-aware (verified by reading the on-disk `cells/<hash>.json` filename differs between the two runs). |
| 5 | `test_result_to_dict_load_roundtrip` | Run a small sweep, `result.save(path)`, `CompletenessSweepResult.load(path)`, assert all numeric arrays and config fields match. |
| 6 | `test_progress_callback_invoked_per_cell` | Spy on a callback; assert it is called exactly `total_cells` times, with monotonically increasing `current` values. |

All tests use small grids (≤ 3×3×2, n_injections ≤ 2) and an isolated `cache_dir=tmp_path`
fixture so they don't pollute `outputs/`.

### 5.2 Failure modes & how the design handles them

| Failure | Behavior |
|---------|----------|
| Crash mid-cell | `cells/<hash>.json.tmp` is left on disk; on next run, `_is_valid_cache_hit` returns False, the cell is rerun, atomic rename replaces any orphan `.tmp` with a valid `.json`. |
| Config change between runs | `config_hash` differs → new sweep subdir is created; old cells are NOT touched (non-destructive cache). |
| Per-injection exception | Caught per-injection, recorded as `recovered=false` with an `"error"` key in the per-injection record. Sweep continues. |
| Missing reportlab | `_validate_schema` is not in this module's path; `generate_completeness_report` always returns a `dict` regardless of reportlab availability. |
| Out-of-memory under large `n_injections` | Not addressed in this bucket (would require per-injection GC or batching). Documented as a deferred concern in the summary report. |

### 5.3 Verification commands (mirrors the summary report)

```bash
# Phase 0 baseline
git checkout -b feature/completeness-sweep
python -m pytest tests/ -v > reports/bucket3_pretest_baseline.txt 2>&1

# Phase 1 (discovery) — produce reports/bucket3_sweep_design.md
# Phase 2 implementation — incremental commits, after each:
python -m pytest tests/test_synthetic_simulation.py -v
python -m pytest tests/test_completeness_sweep.py -v    # as tests are added

# Phase 3 (full test)
python -m pytest tests/ -v > reports/bucket3_posttest.txt 2>&1

# Phase 3 (genuine small integration run)
python -c "
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.visualization.plots import plot_completeness_map
from astraeus.analysis.reporting import generate_completeness_report
import json
cfg = CompletenessSweepConfig(
    period_count=3, radius_ratio_count=3, snr_values=(10.0, 50.0),
    n_injections=3, seed=42,
    cache_dir='outputs/completeness_sweeps/integration_demo',
)
result = run_completeness_sweep(cfg)
heatmap_p, snr_p = plot_completeness_map(result, cfg.cache_dir + '/' + result.config_hash)
payload = generate_completeness_report(result, cfg, {'heatmap': heatmap_p, 'snr_slope': snr_p})
print(json.dumps(payload['summary_stats'], indent=2))
"

# Phase 4 (summary report) — write reports/bucket3_summary.md
```

---

## 6. Out of Scope (Explicit)

- Streamlit UI integration — future bucket, after Buckets 0 and 1 are stable.
- PDF rendering of completeness data — future bucket; this bucket returns a JSON payload.
- Multi-planet, TTV, or injection into non-Kepler-like baselines — out of scope.
- Replacing or rewriting `run_injection_recovery` — primitive is preserved verbatim.
- Parallel execution across cells (joblib/multiprocessing) — deferred; cell runtime is
  small enough at default resolution that serial execution is acceptable.

---

## 7. Phase Plan & Commit Cadence

1. **Phase 0** — `git checkout -b feature/completeness-sweep`, run baseline tests, save
   to `reports/bucket3_pretest_baseline.txt`. No code changes.
2. **Phase 1** — produce `reports/bucket3_sweep_design.md` (this spec, condensed), with
   empirical per-cell cost measured and any default-resolution adjustments documented.
3. **Phase 2** — implementation, split into 5 commits:
   - (a) `CompletenessSweepConfig` + `CompletenessSweepResult` dataclasses, no runner yet.
   - (b) `run_completeness_sweep` core loop (no caching).
   - (c) Cell-level caching + manifest + atomic writes + resumability.
   - (d) `plot_completeness_map` + simulation `__init__` re-exports.
   - (e) `generate_completeness_report` in reporting.py.
4. **Phase 3** — `tests/test_completeness_sweep.py` (6 tests) + genuine small integration
   run with output inspection. Save full-suite run to `reports/bucket3_posttest.txt`.
5. **Phase 4** — `reports/bucket3_summary.md` covering: grid design + cost estimate,
   per-cell cost measured, caching/resumability behavior, sample output, reporting
   wiring, future-UI hook sketch, verification commands.

---

## 8. Acceptance Criteria

The bucket is complete when ALL of the following hold:

- [ ] `git status` is clean on `feature/completeness-sweep` (final state).
- [ ] `tests/test_synthetic_simulation.py` passes unchanged.
- [ ] `tests/test_completeness_sweep.py` (6 tests) passes.
- [ ] Full suite: `passed >= baseline`, `failures == 0`.
- [ ] Genuine integration run produces `outputs/completeness_sweeps/<config_hash>/heatmap.png`,
      `snr_slope.png`, `result.json`, `manifest.json`, `cells/*.json`.
- [ ] Re-running the same integration command with the same `config` produces
      `cache_hits == total_cells` (zero re-work).
- [ ] `reports/bucket3_summary.md` exists and references the actual artifact paths
      produced by the integration run.
- [ ] No changes to `astraeus/simulation/synthetic.py`,
      `astraeus/analysis/detection.py`, or any Streamlit/dashboard code.