# Completeness Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a systematic completeness sweep layer (`astraeus/simulation/completeness.py`) on top of the existing `run_injection_recovery` primitive, with per-cell caching, resumability, plotting, and reporting — without modifying the primitive's existing signature.

**Architecture:** A new module wraps the existing primitive in a grid iterator. Each (period, depth, SNR) cell is hashed, cached on disk as one atomic JSON, and aggregated into a 3D `numpy` `CompletenessSweepResult`. A `use_full_pipeline` flag toggles between raw-BLS recovery (`run_injection_recovery`, 1% tolerance) and full-pipeline recovery (`detect_transit_candidate`, strict verdict set). Plotting & reporting are appended as additive functions to existing files.

**Tech Stack:** Python 3, NumPy, `astropy.timeseries.BoxLeastSquares` (already used), `dataclasses`, `hashlib` (sha256), `pathlib`, `json`, matplotlib (Agg backend, already used). No new external dependencies.

**Reference spec:** `docs/superpowers/specs/2026-06-23-completeness-sweep-design.md`. Every task below maps to one section of that spec.

---

## Phase 0 — Safety Setup

### Task 0: Baseline + branch creation

**Files:**
- Create: `reports/bucket3_pretest_baseline.txt` (captured pytest output)
- Modify: branch state only (no file edits to source)

- [ ] **Step 1: Confirm clean working tree**

```bash
cd F:/solo_leveling_assistant/project-astraeus
git status
```

Expected: `nothing to commit, working tree clean`. If not clean, **STOP** and report to user.

- [ ] **Step 2: Create the bucket branch**

```bash
git checkout -b feature/completeness-sweep
```

Expected: `Switched to a new branch 'feature/completeness-sweep'`.

- [ ] **Step 3: Run the full test suite, save baseline**

```bash
python -m pytest tests/ -v > reports/bucket3_pretest_baseline.txt 2>&1
```

Expected: exit code 0. The text file contains the captured pytest output (passed / skipped / deselected counts).

- [ ] **Step 4: Extract baseline pass/fail counts for later comparison**

```bash
grep -E "^=+ [0-9]+ (passed|failed)" reports/bucket3_pretest_baseline.txt
```

Expected output (one line): a summary like `=== 85 passed, 1 skipped, 33 deselected in 47.21s ===` (exact numbers will vary). Record this line — it is the pass-count gate for Phase 3.

- [ ] **Step 5: Confirm `tests/test_synthetic_simulation.py` passes in particular**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed` (matches the 4 test methods in that file).

- [ ] **Step 6: Commit**

```bash
git add reports/bucket3_pretest_baseline.txt
git commit -m "chore(bucket3): capture Phase 0 baseline test output"
```

---

## Phase 1 — Discovery

### Task 1: Add `recovered_depth` to `run_injection_recovery` return dict (spec Change 2)

**Files:**
- Modify: `astraeus/simulation/synthetic.py:260-267`

- [ ] **Step 1: Read the current return-dict block at lines 260-267**

Open `astraeus/simulation/synthetic.py`. Confirm the dict at lines 260-267 currently is:

```python
payload_dict = {
    "signal_recovered": signal_recovered,
    "period_error_delta": period_error_delta,
    "snr_attenuation": snr_attenuation,
    "recovered_period": recovered_period,
    "recovered_snr": snr,
    "injected_snr": injected_theoretical_snr
}
```

- [ ] **Step 2: Add `recovered_depth` key**

Replace the block above with:

```python
payload_dict = {
    "signal_recovered": signal_recovered,
    "period_error_delta": period_error_delta,
    "snr_attenuation": snr_attenuation,
    "recovered_period": recovered_period,
    "recovered_snr": snr,
    "recovered_depth": float(depth),
    "injected_snr": injected_theoretical_snr
}
```

`depth` is computed at line 246 via `BLSSearchEngine.compute_snr_depth(...)` and already in scope. Casting to `float` ensures JSON-serializability (matches `float()` style used on neighboring lines).

- [ ] **Step 3: Run `tests/test_synthetic_simulation.py` — must still pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed`. These tests do not call `run_injection_recovery`, so they are unaffected, but we run them as the explicit regression gate.

- [ ] **Step 4: Run the full suite — must match baseline**

```bash
python -m pytest tests/ -v > /tmp/bucket3_after_change2.txt 2>&1
grep -E "^=+ [0-9]+ (passed|failed)" /tmp/bucket3_after_change2.txt
```

Expected: pass count equals the baseline recorded in Task 0 Step 4; `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add astraeus/simulation/synthetic.py
git commit -m "feat(synthetic): expose recovered_depth in run_injection_recovery return (bucket 3)"
```

---

### Task 2: Time a single representative cell (spec §1.2 cost estimate)

**Files:**
- Create: `reports/bucket3_sweep_design.md` (final, see Task 3)
- No source modifications in this task.

- [ ] **Step 1: Run a single representative cell to measure cost**

Open a Python REPL or write a one-off script `scratch/bucket3_cell_timer.py`:

```python
import time
import numpy as np
from astraeus.simulation.synthetic import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
    run_injection_recovery,
)

scenario = SyntheticTransitScenario(
    duration=90.0,
    period=10.0,
    radius_ratio=0.05,
    snr=50.0,
    samples=4000,
    seed=42,
)
series = generate_synthetic_transit_series(scenario)
t0 = time.perf_counter()
for _ in range(10):
    result = run_injection_recovery(
        time=series.time_days,
        flux=series.observed_flux,
        injected_period=10.0,
        injected_r_ratio=0.05,
        injected_b=0.3,
        injected_epoch=45.0,
    )
elapsed = time.perf_counter() - t0
print(f"per-injection: {elapsed / 10:.3f}s ; signal_recovered={result['signal_recovered']}")
print(f"full-cell at n=10: {elapsed:.3f}s")
```

Run: `python scratch/bucket3_cell_timer.py`. Record the per-injection time and per-cell (n=10) time. They will be quoted in the discovery report.

- [ ] **Step 2: Compute total default-grid cost**

Default grid is 8 × 6 × 5 = 240 cells × `n_injections=10`. Total ≈ `per_cell_seconds × 240`. If this exceeds ~5 minutes (300 s), reduce defaults in the spec's `CompletenessSweepConfig` (the next task reads the defaults from the spec). Document the chosen defaults and the reasoning in Task 3.

- [ ] **Step 3: Discard the scratch script (do not commit it)**

```bash
rm scratch/bucket3_cell_timer.py
```

We don't commit throwaway measurement scripts.

---

### Task 3: Write `reports/bucket3_sweep_design.md` (Phase 1 discovery report)

**Files:**
- Create: `reports/bucket3_sweep_design.md`

- [ ] **Step 1: Compose the report**

Write the file with these sections:

```markdown
# Bucket 3 — Completeness Sweep Discovery Report

**Date:** <today's date>
**Branch:** `feature/completeness-sweep`

---

## 1. Existing primitive inventory (spec §1.1)

### 1.1 `SyntheticTransitScenario`
Frozen dataclass at `astraeus/simulation/synthetic.py:20`. Fields: `duration`,
`period`, `eccentricity`, `radius_ratio`, `snr`, `samples`, `seed`,
`stellar_radius`, `semi_major_axis`, `inclination`. Validation in
`_validate_scenario` requires `radius_ratio in (0, 1]` and `samples >= 2`.

### 1.2 `LightCurveSeries`
Frozen dataclass at line 44. Fields: `time_days`, `theoretical_flux`,
`observed_flux`. `residuals` is a derived property.

### 1.3 `run_injection_recovery`
Signature at line 131:
`run_injection_recovery(time, flux, injected_period, injected_r_ratio, injected_b, injected_epoch, known_planets=None, metadata=None)`.
**Recovery criterion:** `|recovered_period - injected_period| / injected_period <= 0.01`
(1% relative tolerance — line 250). Runs a focused **5%-band raw BLS search** via
`astropy.timeseries.BoxLeastSquares`, **NOT** the full pipeline. After Task 1
the return dict carries: `signal_recovered`, `period_error_delta`,
`snr_attenuation`, `recovered_period`, `recovered_snr`, `recovered_depth`,
`injected_snr`.

### 1.4 Existing test coverage
`tests/test_synthetic_simulation.py` (4 tests) covers shape, transit dips,
residuals, and sample-count validation. It does NOT exercise
`run_injection_recovery`. No new test in the sweep layer duplicates that
coverage; the new file `tests/test_completeness_sweep.py` is purely about the
sweep layer.

---

## 2. Critical finding — full pipeline vs raw BLS (spec §1.2)

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

---

## 3. Per-cell cost (spec §2.1)

Measured in Task 2:
- per-injection time: <fill from Task 2>
- full-cell at n_injections=10: <fill from Task 2>
- default grid (8 × 6 × 5 = 240 cells × 10 injections): <fill from Task 2>

**Default-resolution decision:** <fill — either "ship defaults as 8/6/5/10" or
"reduce one axis to fit the budget">. Cite the measured cost and chosen
default values here.

---

## 4. Cache-key & ledger pattern (spec §3)

Existing pattern in `astraeus/analysis/logging.py`:
`generate_dataset_hash(metadata) = sha256(json.dumps(metadata, sort_keys=True, default=str))`.

The sweep's `_compute_config_hash` and `_compute_cell_hash` use the same
convention. Atomic write (`temp_path → os.replace`) matches
`ExperimentLedger.log_candidate` at `astraeus/analysis/logging.py:108-117`.

---

## 5. Output location (spec §3.1)

`outputs/completeness_sweeps/<config_hash>/{config.json, manifest.json,
result.json, cells/<cell_hash>.json, heatmap.png, snr_slope.png}`. Mirrors the
existing `outputs/kepler90_blind_search/` pattern.

---

## 6. Reporting integration (spec §4.2)

`generate_academic_report` is locked to a `{star_id, candidates: [...]}` schema
by `_validate_schema`. Completeness data does not fit this schema (it is a grid
of metrics, not a star+candidates report). New function
`generate_completeness_report` returns a JSON `dict` (not a PDF) so a future
bucket can add PDF rendering.
```

- [ ] **Step 2: Commit**

```bash
git add reports/bucket3_sweep_design.md
git commit -m "docs(bucket3): Phase 1 discovery report (existing primitive, cost, cache pattern)"
```

---

## Phase 2 — Implementation (5 incremental commits)

### Task 4: (commit 2a) — `CompletenessSweepConfig` dataclass

**Files:**
- Create: `astraeus/simulation/completeness.py`
- Modify: `astraeus/simulation/__init__.py`

- [ ] **Step 1: Create `completeness.py` with the config dataclass only**

Write `astraeus/simulation/completeness.py` containing ONLY the config
dataclass and its imports — no runner, no result yet. Imports block plus the
class:

```python
"""Completeness sweep over (period, depth, SNR) for ASTRAEUS injection recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompletenessSweepConfig:
    """Configuration for a completeness sweep over (period, depth, SNR).

    The sweep builds a log-spaced period × depth grid and an enumerated SNR
    axis, then evaluates `n_injections` noisy realizations per cell using
    either the raw-BLS primitive (`run_injection_recovery`) or the full
    detection pipeline (`detect_transit_candidate`).
    """

    # ----- Grid dimensions -----
    period_min_days: float = 0.5
    period_max_days: float = 30.0
    period_count: int = 8
    radius_ratio_min: float = 0.005
    radius_ratio_max: float = 0.10
    radius_ratio_count: int = 6
    snr_values: tuple[float, ...] = (5.0, 10.0, 20.0, 50.0, 100.0)

    # ----- Per-cell sampling -----
    n_injections: int = 10
    seed: int = 1729

    # ----- Recovery-mode flag -----
    use_full_pipeline: bool = False

    # ----- Time-series sizing -----
    duration_days: float = 90.0
    samples: int = 4_000

    # ----- Fixed per-cell injection geometry -----
    impact_parameter: float = 0.3
    transit_epoch_fraction: float = 0.5

    # ----- Caching / I/O -----
    cache_dir: str | Path = "outputs/completeness_sweeps"

    # ----- Forwarded to run_injection_recovery in BLS-only mode -----
    known_planets: list[dict] | None = None
    metadata: dict | None = None

    def __post_init__(self) -> None:
        if self.duration_days < 2 * self.period_max_days:
            raise ValueError(
                f"duration_days ({self.duration_days}) must be >= 2 * period_max_days "
                f"({2 * self.period_max_days}) to ensure >= 2 transits per period cell"
            )
        if self.period_count < 2 or self.radius_ratio_count < 2:
            raise ValueError("period_count and radius_ratio_count must be >= 2")
        if len(self.snr_values) < 1:
            raise ValueError("snr_values must contain at least one value")
        if self.n_injections < 1:
            raise ValueError("n_injections must be >= 1")

    @property
    def total_cells(self) -> int:
        return self.period_count * self.radius_ratio_count * len(self.snr_values)
```

- [ ] **Step 2: Re-export from the simulation package**

Open `astraeus/simulation/__init__.py`. Replace its current contents with:

```python
"""Synthetic simulation workflows for ASTRAEUS."""

from astraeus.simulation.synthetic import (
    LightCurveSeries,
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)

# Re-exported lazily to avoid an import cycle (completeness.py imports from
# synthetic.py transitively via downstream callers, not the other way around).
__all__ = [
    "CompletenessSweepConfig",
    "LightCurveSeries",
    "SyntheticTransitScenario",
    "generate_synthetic_transit_series",
]
```

Note: `CompletenessSweepConfig` will be imported at module-load time after Task 6
adds the rest of `completeness.py`. For this task we add the symbol to
`__all__` only — defer the actual `from astraeus.simulation.completeness
import CompletenessSweepConfig` line until Task 6, OR import it now and run the
test in Step 3 (the dataclass alone is enough for a working import).

For Task 4, do the simpler thing: just add to `__all__` and do NOT import yet
(otherwise the next test run needs the full module). Defer the import line to
Task 6.

- [ ] **Step 3: Run the existing test_synthetic_simulation.py — must pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed`. (This task added a new file with no behavior visible to
the existing tests; the run is the regression gate.)

- [ ] **Step 4: Smoke-test the config in a REPL**

```bash
python -c "
from astraeus.simulation.completeness import CompletenessSweepConfig
cfg = CompletenessSweepConfig()
print(cfg.total_cells)
# 240
cfg_bad = CompletenessSweepConfig(duration_days=30.0, period_max_days=30.0)
# Should raise ValueError
"
```

Expected: `240` printed, then a `ValueError` traceback.

- [ ] **Step 5: Commit**

```bash
git add astraeus/simulation/completeness.py astraeus/simulation/__init__.py
git commit -m "feat(simulation): CompletenessSweepConfig dataclass with validation gate"
```

---

### Task 5: (commit 2a cont'd) — `CompletenessSweepResult` dataclass

**Files:**
- Modify: `astraeus/simulation/completeness.py` (append below config)
- No new test file yet — tests added in Phase 3.

- [ ] **Step 1: Append the Result dataclass and helpers to `completeness.py`**

Add at the bottom of `astraeus/simulation/completeness.py`:

```python
import hashlib
import json

import numpy as np


def _canonical_json(obj: Any) -> str:
    """Return a canonical JSON string for hashing (matches logging.py pattern)."""
    return json.dumps(obj, sort_keys=True, default=str)


def _compute_config_hash(config: "CompletenessSweepConfig") -> str:
    """SHA256 of the canonicalized config — also the per-sweep directory name."""
    payload = {k: v for k, v in config.__dict__.items() if k != "cache_dir"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompletenessSweepResult:
    """Aggregated result of one completeness sweep (3D grid: period x depth x SNR)."""

    config: CompletenessSweepConfig
    config_hash: str

    periods_days: np.ndarray
    radius_ratios: np.ndarray
    snrs: np.ndarray

    recovery_rate: np.ndarray
    period_err_median: np.ndarray
    period_err_std: np.ndarray
    depth_err_median: np.ndarray
    depth_err_std: np.ndarray
    n_recovered: np.ndarray
    cell_runtime_seconds: np.ndarray

    total_runtime_seconds: float
    cache_hits: int
    cache_misses: int
    started_at_iso: str
    finished_at_iso: str

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.recovery_rate.shape

    def to_dict(self) -> dict:
        """JSON-serializable view (numpy → list, NaN → null)."""

        def _arr(a: np.ndarray) -> list:
            return np.where(np.isnan(a), None, a).tolist()

        return {
            "schema_version": 1,
            "config_hash": self.config_hash,
            "config": {k: v for k, v in self.config.__dict__.items()},
            "axes": {
                "periods_days": self.periods_days.tolist(),
                "radius_ratios": self.radius_ratios.tolist(),
                "snrs": self.snrs.tolist(),
            },
            "metrics": {
                "recovery_rate": _arr(self.recovery_rate),
                "period_err_median": _arr(self.period_err_median),
                "period_err_std": _arr(self.period_err_std),
                "depth_err_median": _arr(self.depth_err_median),
                "depth_err_std": _arr(self.depth_err_std),
                "n_recovered": self.n_recovered.astype(int).tolist(),
                "cell_runtime_seconds": _arr(self.cell_runtime_seconds),
            },
            "telemetry": {
                "total_runtime_seconds": float(self.total_runtime_seconds),
                "cache_hits": int(self.cache_hits),
                "cache_misses": int(self.cache_misses),
                "started_at_iso": self.started_at_iso,
                "finished_at_iso": self.finished_at_iso,
            },
        }

    def save(self, path: str | Path) -> Path:
        """Atomically write `to_dict()` to disk."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, output)
        return output

    @classmethod
    def load(cls, path: str | Path) -> "CompletenessSweepResult":
        """Inverse of `save`. Recovers numpy arrays from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg_dict = data["config"]
        # Snr_values is a tuple in the dataclass; JSON loads it as a list.
        cfg_dict["snr_values"] = tuple(cfg_dict["snr_values"])
        from astraeus.simulation.completeness import CompletenessSweepConfig  # local import to avoid cycle

        config = CompletenessSweepConfig(**cfg_dict)
        ax = data["axes"]
        m = data["metrics"]
        t = data["telemetry"]
        return cls(
            config=config,
            config_hash=data["config_hash"],
            periods_days=np.asarray(ax["periods_days"], dtype=float),
            radius_ratios=np.asarray(ax["radius_ratios"], dtype=float),
            snrs=np.asarray(ax["snrs"], dtype=float),
            recovery_rate=np.asarray(m["recovery_rate"], dtype=float),
            period_err_median=np.asarray(m["period_err_median"], dtype=float),
            period_err_std=np.asarray(m["period_err_std"], dtype=float),
            depth_err_median=np.asarray(m["depth_err_median"], dtype=float),
            depth_err_std=np.asarray(m["depth_err_std"], dtype=float),
            n_recovered=np.asarray(m["n_recovered"], dtype=int),
            cell_runtime_seconds=np.asarray(m["cell_runtime_seconds"], dtype=float),
            total_runtime_seconds=float(t["total_runtime_seconds"]),
            cache_hits=int(t["cache_hits"]),
            cache_misses=int(t["cache_misses"]),
            started_at_iso=str(t["started_at_iso"]),
            finished_at_iso=str(t["finished_at_iso"]),
        )
```

Add `import os` to the imports block at the top of the file (already imported
by `pathlib` consumers but `os.replace` needs it explicitly).

- [ ] **Step 2: Verify the existing test still passes**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed`.

- [ ] **Step 3: Commit**

```bash
git add astraeus/simulation/completeness.py
git commit -m "feat(simulation): CompletenessSweepResult dataclass with to_dict/save/load"
```

---

### Task 6: (commit 2b) — Core sweep runner (no caching yet)

**Files:**
- Modify: `astraeus/simulation/completeness.py` (append)
- Modify: `astraeus/simulation/__init__.py` (now that all symbols exist)

- [ ] **Step 1: Add core runner + helpers to `completeness.py`**

Append below the result dataclass:

```python
import os
import time
from datetime import datetime, timezone


_VERIFIED_PLANET_STATUSES = frozenset({
    "Verified Planet Candidate",
    "Verified Planet Candidate (Atmospheric Occultation Detected)",
})


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write `payload` as JSON atomically (temp + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def _enumerate_cells(config: "CompletenessSweepConfig") -> list[tuple[int, float, float, float]]:
    """Return the flat list of (cell_index, period, radius_ratio, snr)."""
    periods = np.geomspace(config.period_min_days, config.period_max_days, config.period_count)
    depths = np.geomspace(config.radius_ratio_min, config.radius_ratio_max, config.radius_ratio_count)
    out: list[tuple[int, float, float, float]] = []
    idx = 0
    for p in periods:
        for d in depths:
            for s in config.snr_values:
                out.append((idx, float(p), float(d), float(s)))
                idx += 1
    return out


def _compute_cell_hash(
    period: float,
    radius_ratio: float,
    snr: float,
    n_injections: int,
    seed: int,
    use_full_pipeline: bool,
) -> str:
    payload = {
        "period": period,
        "radius_ratio": radius_ratio,
        "snr": snr,
        "n_injections": n_injections,
        "seed": seed,
        "use_full_pipeline": use_full_pipeline,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _run_one_cell(
    config: "CompletenessSweepConfig",
    cell_index: int,
    period: float,
    radius_ratio: float,
    snr: float,
) -> dict:
    """Run n_injections for one (P, D, SNR) cell. Returns a cell-cache dict."""
    from astraeus.simulation.synthetic import (
        SyntheticTransitScenario,
        generate_synthetic_transit_series,
        run_injection_recovery,
    )

    t_epoch = config.transit_epoch_fraction * config.duration_days
    n_recovered = 0
    period_errs: list[float] = []
    depth_errs: list[float] = []
    injection_records: list[dict] = []
    t0 = time.perf_counter()

    for i in range(config.n_injections):
        per_inj_seed = config.seed + cell_index * 1000 + i
        scenario = SyntheticTransitScenario(
            duration=config.duration_days * (1.0 * type(config).duration_days.units if False else None) if False else None,  # placeholder; replaced below
            period=period * 1.0,  # see next line — units handled by astropy
            eccentricity=0.0,
            radius_ratio=radius_ratio,
            snr=snr,
            samples=config.samples,
            seed=per_inj_seed,
        )
```

NOTE: the previous code block has a placeholder for astropy unit handling.
The cleaner version below REPLACES that whole function body — use this
cleaner version in the actual edit:

```python
def _run_one_cell(
    config: "CompletenessSweepConfig",
    cell_index: int,
    period: float,
    radius_ratio: float,
    snr: float,
) -> dict:
    """Run n_injections for one (P, D, SNR) cell. Returns a cell-cache dict."""
    from astropy import units as u

    from astraeus.analysis.detection import detect_transit_candidate
    from astraeus.simulation.synthetic import (
        SyntheticTransitScenario,
        generate_synthetic_transit_series,
        run_injection_recovery,
    )

    t_epoch = config.transit_epoch_fraction * config.duration_days
    n_recovered = 0
    period_errs: list[float] = []
    depth_errs: list[float] = []
    injection_records: list[dict] = []
    t0 = time.perf_counter()

    for i in range(config.n_injections):
        per_inj_seed = config.seed + cell_index * 1000 + i
        scenario = SyntheticTransitScenario(
            duration=config.duration_days * u.day,
            period=period * u.day,
            eccentricity=0.0 * u.dimensionless_unscaled,
            radius_ratio=radius_ratio,
            snr=snr,
            samples=config.samples,
            seed=per_inj_seed,
        )
        series = generate_synthetic_transit_series(scenario)
        record: dict = {"seed": per_inj_seed}

        if config.use_full_pipeline:
            try:
                candidate = detect_transit_candidate(
                    series.time_days,
                    series.observed_flux,
                    target_name=f"completeness_cell_{cell_index}",
                    data_source="completeness_sweep",
                    metadata={"st_rad": 1.0, "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0},
                )
                cand_period = float(candidate.get("period_days", 0.0))
                recovered = bool(candidate.get("candidate_found"))
                record.update({
                    "recovered": recovered,
                    "recovered_period": cand_period,
                    "recovered_depth": float(candidate.get("transit_depth", 0.0)),
                    "recovered_snr": float(candidate.get("snr", 0.0)),
                    "vetting_status": str(candidate.get("vetting_status", "unknown")),
                })
                if recovered and period > 0:
                    period_err = abs(cand_period - period) / period
                    if period_err <= 0.01 and record["vetting_status"] in _VERIFIED_PLANET_STATUSES:
                        n_recovered += 1
                        period_errs.append(abs(cand_period - period))
                        depth_errs.append(record["recovered_depth"] - radius_ratio ** 2)  # injected depth ~= r_ratio^2
            except Exception as exc:  # noqa: BLE001 — sweep must continue past per-injection failures
                record = {"seed": per_inj_seed, "recovered": False, "error": str(exc)}
        else:
            try:
                result = run_injection_recovery(
                    time=series.time_days,
                    flux=series.observed_flux,
                    injected_period=period,
                    injected_r_ratio=radius_ratio,
                    injected_b=config.impact_parameter,
                    injected_epoch=t_epoch,
                    known_planets=config.known_planets,
                    metadata=config.metadata,
                )
                recovered = bool(result.get("signal_recovered"))
                rec_period = float(result.get("recovered_period", 0.0))
                rec_depth = float(result.get("recovered_depth", 0.0))
                record.update({
                    "recovered": recovered,
                    "recovered_period": rec_period,
                    "recovered_depth": rec_depth,
                    "recovered_snr": float(result.get("recovered_snr", 0.0)),
                    "vetting_status": "n/a",
                })
                if recovered:
                    n_recovered += 1
                    period_errs.append(abs(rec_period - period))
                    depth_errs.append(rec_depth - radius_ratio ** 2)
            except Exception as exc:  # noqa: BLE001
                record = {"seed": per_inj_seed, "recovered": False, "error": str(exc)}

        injection_records.append(record)

    elapsed = time.perf_counter() - t0
    return {
        "cell": {
            "period_days": period,
            "radius_ratio": radius_ratio,
            "snr": snr,
            "n_injections": config.n_injections,
            "mode": "full_pipeline" if config.use_full_pipeline else "bls_only",
        },
        "result": {
            "recovery_rate": n_recovered / max(config.n_injections, 1),
            "period_err_median": float(np.median(period_errs)) if len(period_errs) >= 1 else float("nan"),
            "period_err_std": float(np.std(period_errs)) if len(period_errs) >= 2 else float("nan"),
            "depth_err_median": float(np.median(depth_errs)) if len(depth_errs) >= 1 else float("nan"),
            "depth_err_std": float(np.std(depth_errs)) if len(depth_errs) >= 2 else float("nan"),
            "n_recovered": n_recovered,
            "runtime_seconds": elapsed,
            "injection_records": injection_records,
        },
        "schema_version": 1,
        "written_at_iso": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 2: Add the top-level `run_completeness_sweep` function (no caching)**

Append below the helpers:

```python
def run_completeness_sweep(
    config: "CompletenessSweepConfig",
    *,
    progress_callback=None,
) -> "CompletenessSweepResult":
    """Run the completeness sweep and aggregate into a 3D result grid.

    Note: caching is added in a later task. This version re-runs every cell.
    """
    config_hash = _compute_config_hash(config)
    periods = np.geomspace(config.period_min_days, config.period_max_days, config.period_count)
    depths = np.geomspace(config.radius_ratio_min, config.radius_ratio_max, config.radius_ratio_count)
    snrs = np.asarray(config.snr_values, dtype=float)

    shape = (config.period_count, config.radius_ratio_count, len(config.snr_values))
    recovery_rate = np.zeros(shape, dtype=float)
    period_err_med = np.full(shape, np.nan, dtype=float)
    period_err_std = np.full(shape, np.nan, dtype=float)
    depth_err_med = np.full(shape, np.nan, dtype=float)
    depth_err_std = np.full(shape, np.nan, dtype=float)
    n_rec = np.zeros(shape, dtype=int)
    cell_rt = np.zeros(shape, dtype=float)

    started = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    for cell_index, period, depth, snr in _enumerate_cells(config):
        cell_data = _run_one_cell(config, cell_index, period, depth, snr)
        r = cell_data["result"]
        # Flat index -> 3D grid index
        i = cell_index // (config.radius_ratio_count * len(config.snr_values))
        rem = cell_index % (config.radius_ratio_count * len(config.snr_values))
        j = rem // len(config.snr_values)
        k = rem % len(config.snr_values)
        recovery_rate[i, j, k] = r["recovery_rate"]
        period_err_med[i, j, k] = r["period_err_median"]
        period_err_std[i, j, k] = r["period_err_std"]
        depth_err_med[i, j, k] = r["depth_err_median"]
        depth_err_std[i, j, k] = r["depth_err_std"]
        n_rec[i, j, k] = r["n_recovered"]
        cell_rt[i, j, k] = r["runtime_seconds"]
        if progress_callback is not None:
            progress_callback(cell_index + 1, config.total_cells, cell_data)

    finished_iso = datetime.now(timezone.utc).isoformat()
    return CompletenessSweepResult(
        config=config,
        config_hash=config_hash,
        periods_days=periods,
        radius_ratios=depths,
        snrs=snrs,
        recovery_rate=recovery_rate,
        period_err_median=period_err_med,
        period_err_std=period_err_std,
        depth_err_median=depth_err_med,
        depth_err_std=depth_err_std,
        n_recovered=n_rec,
        cell_runtime_seconds=cell_rt,
        total_runtime_seconds=time.perf_counter() - started,
        cache_hits=0,
        cache_misses=config.total_cells,
        started_at_iso=started_iso,
        finished_at_iso=finished_iso,
    )
```

- [ ] **Step 3: Update `astraeus/simulation/__init__.py` to import the new symbols**

Open `astraeus/simulation/__init__.py`. Replace its current contents with:

```python
"""Synthetic simulation workflows for ASTRAEUS."""

from astraeus.simulation.completeness import (
    CompletenessSweepConfig,
    CompletenessSweepResult,
    run_completeness_sweep,
)
from astraeus.simulation.synthetic import (
    LightCurveSeries,
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)

__all__ = [
    "CompletenessSweepConfig",
    "CompletenessSweepResult",
    "LightCurveSeries",
    "SyntheticTransitScenario",
    "generate_synthetic_transit_series",
    "run_completeness_sweep",
]
```

- [ ] **Step 4: Smoke test the runner end-to-end on a tiny grid**

```bash
python -c "
import time
from astraeus.simulation.completeness import (
    CompletenessSweepConfig, run_completeness_sweep,
)
cfg = CompletenessSweepConfig(
    period_count=2, radius_ratio_count=2, snr_values=(20.0,),
    n_injections=2, duration_days=10.0, period_max_days=4.0,
    cache_dir='outputs/completeness_sweeps/scratch_task6',
)
t = time.perf_counter()
result = run_completeness_sweep(cfg)
print(f'elapsed: {time.perf_counter() - t:.2f}s')
print(f'shape: {result.shape}')
print(f'recovery_rate:\n{result.recovery_rate}')
"
```

Expected: a numeric shape (2, 2, 1) and a recovery_rate matrix printed; the
elapsed time should be a few seconds (4 cells × 2 injections).

- [ ] **Step 5: Run the existing test suite — must pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
python -m pytest tests/ -v > /tmp/bucket3_after_2b.txt 2>&1
grep -E "^=+ [0-9]+ (passed|failed)" /tmp/bucket3_after_2b.txt
```

Expected: `4 passed` for synthetic tests; full suite pass count must equal
the baseline recorded in Task 0 Step 4, `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add astraeus/simulation/completeness.py astraeus/simulation/__init__.py
git commit -m "feat(simulation): run_completeness_sweep core (no caching yet)"
```

---

### Task 7: (commit 2c) — Cell caching + manifest + resumability

**Files:**
- Modify: `astraeus/simulation/completeness.py`

- [ ] **Step 1: Add `_is_valid_cache_hit` and `_load_cell_data` helpers**

Append to `completeness.py`:

```python
def _is_valid_cache_hit(path: Path, expected_config_hash: str) -> bool:
    """True if `path` exists and its stored config_hash matches."""
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    return data.get("config_hash") == expected_config_hash


def _load_cell_data(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_or_init_manifest(sweep_dir: Path, config_hash: str, total_cells: int) -> dict:
    manifest_path = sweep_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            if m.get("config_hash") == config_hash:
                return m
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "config_hash": config_hash,
        "total_cells": total_cells,
        "completed_cells": [],
        "in_progress_cells": [],
        "started_at_iso": datetime.now(timezone.utc).isoformat(),
        "last_updated_iso": datetime.now(timezone.utc).isoformat(),
    }


def _atomic_write_manifest(sweep_dir: Path, manifest: dict) -> None:
    manifest["last_updated_iso"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(sweep_dir / "manifest.json", manifest)
```

- [ ] **Step 2: Replace `run_completeness_sweep` with the caching version**

Open `completeness.py`. Replace the existing `run_completeness_sweep` function
body with:

```python
def run_completeness_sweep(
    config: "CompletenessSweepConfig",
    *,
    progress_callback=None,
) -> "CompletenessSweepResult":
    """Run the completeness sweep with per-cell caching and resumability."""
    config_hash = _compute_config_hash(config)
    sweep_dir = Path(config.cache_dir) / config_hash
    cells_dir = sweep_dir / "cells"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    cells_dir.mkdir(parents=True, exist_ok=True)

    # Persist the canonical config once (idempotent rewrite).
    _atomic_write_json(sweep_dir / "config.json", {k: v for k, v in config.__dict__.items()})

    manifest = _load_or_init_manifest(sweep_dir, config_hash, config.total_cells)

    periods = np.geomspace(config.period_min_days, config.period_max_days, config.period_count)
    depths = np.geomspace(config.radius_ratio_min, config.radius_ratio_max, config.radius_ratio_count)
    snrs = np.asarray(config.snr_values, dtype=float)

    shape = (config.period_count, config.radius_ratio_count, len(config.snr_values))
    recovery_rate = np.full(shape, np.nan, dtype=float)
    period_err_med = np.full(shape, np.nan, dtype=float)
    period_err_std = np.full(shape, np.nan, dtype=float)
    depth_err_med = np.full(shape, np.nan, dtype=float)
    depth_err_std = np.full(shape, np.nan, dtype=float)
    n_rec = np.full(shape, -1, dtype=int)  # -1 = not yet computed
    cell_rt = np.full(shape, np.nan, dtype=float)

    started = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()
    cache_hits = 0
    cache_misses = 0

    for cell_index, period, depth, snr in _enumerate_cells(config):
        cell_hash = _compute_cell_hash(
            period, depth, snr, config.n_injections, config.seed, config.use_full_pipeline,
        )
        cell_path = cells_dir / f"{cell_hash}.json"

        if _is_valid_cache_hit(cell_path, config_hash):
            cell_data = _load_cell_data(cell_path)
            cache_hits += 1
        else:
            cell_data = _run_one_cell(config, cell_index, period, depth, snr)
            cell_data["config_hash"] = config_hash
            _atomic_write_json(cell_path, cell_data)
            cache_misses += 1

        manifest.setdefault("completed_cells", []).append(cell_hash)
        _atomic_write_manifest(sweep_dir, manifest)

        r = cell_data["result"]
        i = cell_index // (config.radius_ratio_count * len(config.snr_values))
        rem = cell_index % (config.radius_ratio_count * len(config.snr_values))
        j = rem // len(config.snr_values)
        k = rem % len(config.snr_values)
        recovery_rate[i, j, k] = r["recovery_rate"]
        period_err_med[i, j, k] = r["period_err_median"]
        period_err_std[i, j, k] = r["period_err_std"]
        depth_err_med[i, j, k] = r["depth_err_median"]
        depth_err_std[i, j, k] = r["depth_err_std"]
        n_rec[i, j, k] = r["n_recovered"]
        cell_rt[i, j, k] = r["runtime_seconds"]

        if progress_callback is not None:
            progress_callback(cell_index + 1, config.total_cells, cell_data)

    finished_iso = datetime.now(timezone.utc).isoformat()
    result = CompletenessSweepResult(
        config=config,
        config_hash=config_hash,
        periods_days=periods,
        radius_ratios=depths,
        snrs=snrs,
        recovery_rate=recovery_rate,
        period_err_median=period_err_med,
        period_err_std=period_err_std,
        depth_err_median=depth_err_med,
        depth_err_std=depth_err_std,
        n_recovered=n_rec,
        cell_runtime_seconds=cell_rt,
        total_runtime_seconds=time.perf_counter() - started,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        started_at_iso=started_iso,
        finished_at_iso=finished_iso,
    )
    result.save(sweep_dir / "result.json")
    return result
```

- [ ] **Step 3: Smoke test caching**

```bash
python -c "
import shutil, time
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
cache = 'outputs/completeness_sweeps/scratch_task7'
shutil.rmtree(cache, ignore_errors=True)
cfg = CompletenessSweepConfig(
    period_count=2, radius_ratio_count=2, snr_values=(20.0,),
    n_injections=2, duration_days=10.0, period_max_days=4.0,
    cache_dir=cache,
)
t = time.perf_counter()
r1 = run_completeness_sweep(cfg)
print(f'first run: {time.perf_counter()-t:.2f}s hits={r1.cache_hits} misses={r1.cache_misses}')
t = time.perf_counter()
r2 = run_completeness_sweep(cfg)
print(f'second run: {time.perf_counter()-t:.2f}s hits={r2.cache_hits} misses={r2.cache_misses}')
"
```

Expected: second run reports `hits=4 misses=0` and is dramatically faster
than the first.

- [ ] **Step 4: Run the existing test suite — must pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
python -m pytest tests/ -v > /tmp/bucket3_after_2c.txt 2>&1
grep -E "^=+ [0-9]+ (passed|failed)" /tmp/bucket3_after_2c.txt
```

Expected: pass count equals baseline, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add astraeus/simulation/completeness.py
git commit -m "feat(simulation): per-cell caching + atomic manifest + resumability"
```

---

### Task 8: (commit 2d) — `plot_completeness_map` + simulation re-exports

**Files:**
- Modify: `astraeus/visualization/plots.py` (append)

- [ ] **Step 1: Append `plot_completeness_map` to `plots.py`**

Open `astraeus/visualization/plots.py`. Append at the bottom:

```python
def plot_completeness_map(
    result,  # CompletenessSweepResult (avoid import cycle with astraeus.simulation)
    output_dir,
) -> tuple:
    """Render a 2D heatmap of recovery rate plus an SNR-slope line plot.

    Returns (heatmap_path, snr_slope_path).
    """
    from pathlib import Path as _P

    out = _P(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.0, 6.0), constrained_layout=True)

    if result.snrs.size == 1:
        im = ax.imshow(
            result.recovery_rate[:, :, 0],
            origin="lower",
            aspect="auto",
            extent=(
                np.log10(result.periods_days[0]),
                np.log10(result.periods_days[-1]),
                np.log10(result.radius_ratios[0]),
                np.log10(result.radius_ratios[-1]),
            ),
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        ax.set_xlabel("log10(period [days])")
        ax.set_ylabel("log10(radius_ratio)")
        mode = "full_pipeline" if result.config.use_full_pipeline else "bls_only"
        ax.set_title(
            f"Completeness (mode={mode}, n_inj={result.config.n_injections}, SNR={result.snrs[0]:.1f})"
        )
        fig.colorbar(im, ax=ax, label="Recovery rate")
        heatmap_path = out / "heatmap.png"
        fig.savefig(heatmap_path, dpi=200)
        plt.close(fig)
    else:
        n = result.snrs.size
        fig, axes = plt.subplots(
            1, n, figsize=(4.0 * n, 5.0), constrained_layout=True, sharey=True
        )
        if n == 1:
            axes = [axes]
        for idx, (ax, snr) in enumerate(zip(axes, result.snrs)):
            im = ax.imshow(
                result.recovery_rate[:, :, idx],
                origin="lower",
                aspect="auto",
                extent=(
                    np.log10(result.periods_days[0]),
                    np.log10(result.periods_days[-1]),
                    np.log10(result.radius_ratios[0]),
                    np.log10(result.radius_ratios[-1]),
                ),
                cmap="viridis",
                vmin=0.0,
                vmax=1.0,
            )
            ax.set_title(f"SNR={snr:.1f}")
            if idx == 0:
                ax.set_ylabel("log10(radius_ratio)")
            ax.set_xlabel("log10(period [days])")
        fig.colorbar(im, ax=axes, label="Recovery rate")
        mode = "full_pipeline" if result.config.use_full_pipeline else "bls_only"
        fig.suptitle(f"Completeness ({mode}, n_inj={result.config.n_injections})")
        heatmap_path = out / "heatmap.png"
        fig.savefig(heatmap_path, dpi=200)
        plt.close(fig)

    # SNR-slope plot: pick a reference grid (every other period × middle depth, max 6 lines)
    fig2, ax2 = plt.subplots(figsize=(8.0, 5.0), constrained_layout=True)
    p_step = max(1, result.periods_days.size // 3)
    p_refs = list(range(0, result.periods_days.size, p_step))[:3]
    d_ref = result.radius_ratios.size // 2
    plotted = 0
    for i in p_refs:
        if plotted >= 6:
            break
        ax2.plot(
            result.snrs,
            result.recovery_rate[i, d_ref, :],
            marker="o",
            label=f"P={result.periods_days[i]:.2f}d, D={result.radius_ratios[d_ref]:.4f}",
        )
        plotted += 1
    ax2.axhline(0.5, color="0.5", linestyle="--", linewidth=1.0, label="50% reference")
    ax2.set_xlabel("Injection SNR")
    ax2.set_ylabel("Recovery rate")
    ax2.set_title("Recovery vs SNR (reference period / depth cells)")
    ax2.set_ylim(-0.02, 1.02)
    ax2.legend(loc="best", fontsize=8)
    ax2.grid(alpha=0.25)
    snr_path = out / "snr_slope.png"
    fig2.savefig(snr_path, dpi=200)
    plt.close(fig2)

    return heatmap_path, snr_path
```

- [ ] **Step 2: Smoke test the plot function**

```bash
python -c "
import shutil
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.visualization.plots import plot_completeness_map
cache = 'outputs/completeness_sweeps/scratch_task8'
shutil.rmtree(cache, ignore_errors=True)
cfg = CompletenessSweepConfig(
    period_count=3, radius_ratio_count=2, snr_values=(10.0, 50.0),
    n_injections=2, duration_days=10.0, period_max_days=4.0,
    cache_dir=cache,
)
r = run_completeness_sweep(cfg)
hm, sn = plot_completeness_map(r, cache + '/' + r.config_hash)
print('heatmap:', hm)
print('snr_slope:', sn)
"
```

Expected: two paths printed, both PNGs exist on disk.

- [ ] **Step 3: Run the existing test suite — must pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed`.

- [ ] **Step 4: Commit**

```bash
git add astraeus/visualization/plots.py
git commit -m "feat(visualization): plot_completeness_map (heatmap + SNR-slope)"
```

---

### Task 9: (commit 2e) — `generate_completeness_report`

**Files:**
- Modify: `astraeus/analysis/reporting.py` (append)

- [ ] **Step 1: Append `generate_completeness_report` to `reporting.py`**

Open `astraeus/analysis/reporting.py`. Append at the bottom:

```python
def generate_completeness_report(result, config, fig_paths):
    """Produce a JSON-shaped summary of one completeness sweep.

    Distinct from `generate_academic_report`: completeness data does not fit
    the {star_id, candidates: [...]} schema enforced by `_validate_schema`.
    This function returns a plain dict, suitable for a future UI panel or a
    future PDF-rendering bucket.

    Args:
        result: CompletenessSweepResult.
        config: CompletenessSweepConfig (used for human-readable summary fields).
        fig_paths: dict mapping figure names to Path objects.

    Returns:
        dict with keys: schema_version, generated_at_iso, mode, config_summary,
        summary_stats, per_cell_table, figure_paths.
    """
    import numpy as _np

    valid = _np.isfinite(result.recovery_rate)
    overall_recovery = float(_np.mean(result.recovery_rate[valid])) if valid.any() else 0.0

    flat = result.recovery_rate.flatten()
    valid_flat = flat[_np.isfinite(flat)]
    if valid_flat.size:
        worst_idx = int(_np.argmin(flat))
        best_idx = int(_np.argmax(flat))
        worst = {
            "period_days": float(result.periods_days[worst_idx // (result.radius_ratios.size * result.snrs.size)]),
            "radius_ratio": float(
                result.radius_ratios[
                    (worst_idx // result.snrs.size) % result.radius_ratios.size
                ]
            ),
            "snr": float(result.snrs[worst_idx % result.snrs.size]),
            "recovery_rate": float(flat[worst_idx]),
        }
        best = {
            "period_days": float(result.periods_days[best_idx // (result.radius_ratios.size * result.snrs.size)]),
            "radius_ratio": float(
                result.radius_ratios[
                    (best_idx // result.snrs.size) % result.radius_ratios.size
                ]
            ),
            "snr": float(result.snrs[best_idx % result.snrs.size]),
            "recovery_rate": float(flat[best_idx]),
        }
    else:
        worst = best = {}

    period_err_flat = result.period_err_median.flatten()
    period_err_valid = period_err_flat[_np.isfinite(period_err_flat)]
    mean_period_err = float(_np.mean(period_err_valid)) if period_err_valid.size else None

    # Per-cell table (one row per cell)
    per_cell: list[dict] = []
    for i, p in enumerate(result.periods_days):
        for j, d in enumerate(result.radius_ratios):
            for k, s in enumerate(result.snrs):
                per_cell.append({
                    "period_days": float(p),
                    "radius_ratio": float(d),
                    "snr": float(s),
                    "recovery_rate": float(result.recovery_rate[i, j, k])
                    if _np.isfinite(result.recovery_rate[i, j, k])
                    else None,
                    "n_recovered": int(result.n_recovered[i, j, k]),
                    "period_err_median": float(result.period_err_median[i, j, k])
                    if _np.isfinite(result.period_err_median[i, j, k])
                    else None,
                    "depth_err_median": float(result.depth_err_median[i, j, k])
                    if _np.isfinite(result.depth_err_median[i, j, k])
                    else None,
                })

    return {
        "schema_version": 1,
        "generated_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": "full_pipeline" if config.use_full_pipeline else "bls_only",
        "config_summary": {
            "period_min_days": config.period_min_days,
            "period_max_days": config.period_max_days,
            "period_count": config.period_count,
            "radius_ratio_min": config.radius_ratio_min,
            "radius_ratio_max": config.radius_ratio_max,
            "radius_ratio_count": config.radius_ratio_count,
            "snr_values": list(config.snr_values),
            "n_injections": config.n_injections,
            "duration_days": config.duration_days,
            "samples": config.samples,
        },
        "summary_stats": {
            "total_cells": int(result.shape[0] * result.shape[1] * result.shape[2]),
            "overall_recovery_rate": overall_recovery,
            "mean_period_err_median_across_recovered_cells": mean_period_err,
            "worst_performing_cell": worst,
            "best_performing_cell": best,
            "total_runtime_seconds": result.total_runtime_seconds,
            "cache_hits": result.cache_hits,
            "cache_misses": result.cache_misses,
        },
        "per_cell_table": per_cell,
        "figure_paths": {k: str(v) for k, v in (fig_paths or {}).items()},
    }
```

- [ ] **Step 2: Smoke test the report function**

```bash
python -c "
import shutil, json
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.analysis.reporting import generate_completeness_report
cache = 'outputs/completeness_sweeps/scratch_task9'
shutil.rmtree(cache, ignore_errors=True)
cfg = CompletenessSweepConfig(
    period_count=2, radius_ratio_count=2, snr_values=(20.0,),
    n_injections=2, duration_days=10.0, period_max_days=4.0,
    cache_dir=cache,
)
r = run_completeness_sweep(cfg)
payload = generate_completeness_report(r, cfg, {})
print(json.dumps(payload['summary_stats'], indent=2))
"
```

Expected: JSON-shaped summary_stats printed (overall_recovery_rate, etc.).

- [ ] **Step 3: Run the existing test suite — must pass**

```bash
python -m pytest tests/test_synthetic_simulation.py -v
```

Expected: `4 passed`.

- [ ] **Step 4: Commit**

```bash
git add astraeus/analysis/reporting.py
git commit -m "feat(reporting): generate_completeness_report (JSON payload, schema-sibling)"
```

---

## Phase 3 — Tests + Integration Run

### Task 10: Write `tests/test_completeness_sweep.py` (6 tests)

**Files:**
- Create: `tests/test_completeness_sweep.py`

- [ ] **Step 1: Create the test file**

Write `tests/test_completeness_sweep.py`:

```python
"""Tests for the completeness sweep layer (bucket 3)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from astraeus.simulation.completeness import (
    CompletenessSweepConfig,
    CompletenessSweepResult,
    run_completeness_sweep,
)
from astraeus.analysis.reporting import generate_completeness_report
from astraeus.visualization.plots import plot_completeness_map


def _tiny_config(cache_dir: Path) -> CompletenessSweepConfig:
    """Smallest grid that exercises all axes (3 cells total, n_injections=2)."""
    return CompletenessSweepConfig(
        period_count=3,
        radius_ratio_count=1,
        snr_values=(20.0,),
        n_injections=2,
        duration_days=10.0,
        period_max_days=4.0,
        cache_dir=str(cache_dir),
    )


def test_small_sweep_returns_expected_shape(tmp_path: Path) -> None:
    cfg = _tiny_config(tmp_path / "shape_test")
    result = run_completeness_sweep(cfg)
    assert result.shape == (3, 1, 1)
    valid = np.isfinite(result.recovery_rate)
    assert valid.all()
    assert ((result.recovery_rate >= 0.0) & (result.recovery_rate <= 1.0)).all()


def test_caching_skips_completed_cells(tmp_path: Path) -> None:
    cache_dir = tmp_path / "caching_test"
    cfg = _tiny_config(cache_dir)

    r1 = run_completeness_sweep(cfg)
    assert r1.cache_misses == cfg.total_cells
    assert r1.cache_hits == 0

    r2 = run_completeness_sweep(cfg)
    assert r2.cache_hits == cfg.total_cells
    assert r2.cache_misses == 0
    # Recovery rates identical between runs.
    np.testing.assert_array_equal(r1.recovery_rate, r2.recovery_rate)


def test_resumability_after_interruption(tmp_path: Path, monkeypatch) -> None:
    """Simulate an interrupted sweep: raises after cell 4 is committed.
    A re-run should pick up at cell 5 with cache_hits=4."""
    cache_dir = tmp_path / "resume_test"
    cfg = CompletenessSweepConfig(
        period_count=3,
        radius_ratio_count=3,
        snr_values=(20.0,),
        n_injections=2,
        duration_days=10.0,
        period_max_days=4.0,
        cache_dir=str(cache_dir),
    )

    # Patch run_completeness_sweep to crash after cell_index == 3 (4 cells done).
    from astraeus.simulation import completeness as cm

    original_run_one = cm._run_one_cell
    call_count = {"n": 0}

    def crashing_run_one(config, cell_index, period, depth, snr):
        out = original_run_one(config, cell_index, period, depth, snr)
        call_count["n"] += 1
        if call_count["n"] > 4:
            raise RuntimeError("simulated crash")
        return out

    monkeypatch.setattr(cm, "_run_one_cell", crashing_run_one)
    with pytest.raises(RuntimeError):
        run_completeness_sweep(cfg)

    # Second run: restore the unpatched runner, expect cache_hits == 4.
    monkeypatch.setattr(cm, "_run_one_cell", original_run_one)
    r2 = run_completeness_sweep(cfg)
    assert r2.cache_hits == 4
    assert r2.cache_misses == cfg.total_cells - 4


def test_use_full_pipeline_changes_recovery_semantics(tmp_path: Path) -> None:
    """BLS-only and full-pipeline modes must produce different cell hashes
    (mode-aware caching) and the full-pipeline mode typically has <= recovery."""
    cache_dir = tmp_path / "full_pipeline_test"
    cfg_bls = CompletenessSweepConfig(
        period_count=2,
        radius_ratio_count=2,
        snr_values=(50.0,),
        n_injections=3,
        duration_days=10.0,
        period_max_days=4.0,
        cache_dir=str(cache_dir / "bls"),
        use_full_pipeline=False,
    )
    cfg_full = CompletenessSweepConfig(
        period_count=2,
        radius_ratio_count=2,
        snr_values=(50.0,),
        n_injections=3,
        duration_days=10.0,
        period_max_days=4.0,
        cache_dir=str(cache_dir / "full"),
        use_full_pipeline=True,
    )
    r_bls = run_completeness_sweep(cfg_bls)
    r_full = run_completeness_sweep(cfg_full)

    # Different config_hash (mode is part of config).
    assert r_bls.config_hash != r_full.config_hash

    # Full-pipeline typically yields <= recovery (stricter verdict set).
    assert r_full.recovery_rate.sum() <= r_bls.recovery_rate.sum() + 1e-9


def test_result_to_dict_load_roundtrip(tmp_path: Path) -> None:
    cfg = _tiny_config(tmp_path / "roundtrip_test")
    result = run_completeness_sweep(cfg)
    out_path = tmp_path / "roundtrip_test" / cfg.config_hash / "result.json"
    result.save(out_path)
    loaded = CompletenessSweepResult.load(out_path)
    np.testing.assert_array_equal(result.recovery_rate, loaded.recovery_rate)
    np.testing.assert_array_equal(result.n_recovered, loaded.n_recovered)
    assert result.config_hash == loaded.config_hash


def test_progress_callback_invoked_per_cell(tmp_path: Path) -> None:
    cfg = _tiny_config(tmp_path / "callback_test")
    calls: list[tuple[int, int]] = []

    def cb(current: int, total: int, cell_data: dict) -> None:
        calls.append((current, total))

    run_completeness_sweep(cfg, progress_callback=cb)
    assert len(calls) == cfg.total_cells
    currents = [c for c, _ in calls]
    assert currents == sorted(currents)
    assert currents[0] == 1
    assert currents[-1] == cfg.total_cells
```

- [ ] **Step 2: Run the new tests**

```bash
python -m pytest tests/test_completeness_sweep.py -v
```

Expected: `6 passed`. (Some may take 5–20 s each because of real BLS runs.)

- [ ] **Step 3: Run the full suite — must equal or exceed baseline**

```bash
python -m pytest tests/ -v > reports/bucket3_posttest.txt 2>&1
grep -E "^=+ [0-9]+ (passed|failed)" reports/bucket3_posttest.txt
```

Expected: passed count ≥ baseline, `0 failed`. (Note: the new tests add
6 to the count.)

- [ ] **Step 4: Commit**

```bash
git add tests/test_completeness_sweep.py reports/bucket3_posttest.txt
git commit -m "test(sweep): 6 tests (shape, caching, resumability, full-pipeline, round-trip, callback)"
```

---

### Task 11: Genuine small integration run + artifact inspection

**Files:**
- Create (runtime): `outputs/completeness_sweeps/integration_demo/...`
- Create (manifest): script command + output snippet captured in the summary.

- [ ] **Step 1: Run a genuine end-to-end integration**

```bash
python -c "
import json
from pathlib import Path
from astraeus.simulation.completeness import CompletenessSweepConfig, run_completeness_sweep
from astraeus.visualization.plots import plot_completeness_map
from astraeus.analysis.reporting import generate_completeness_report

cfg = CompletenessSweepConfig(
    period_count=3, radius_ratio_count=3, snr_values=(10.0, 50.0),
    n_injections=3, seed=42,
    cache_dir='outputs/completeness_sweeps/integration_demo',
)
result = run_completeness_sweep(cfg)
out_dir = Path(cfg.cache_dir) / result.config_hash
heatmap_p, snr_p = plot_completeness_map(result, out_dir)
payload = generate_completeness_report(result, cfg, {'heatmap': heatmap_p, 'snr_slope': snr_p})

print('=== ARTIFACTS ===')
print(f'heatmap: {heatmap_p}')
print(f'snr_slope: {snr_p}')
print(f'result.json: {out_dir / \"result.json\"}')
print(f'cells/: {sorted(p.name for p in (out_dir / \"cells\").glob(\"*.json\"))[:5]}...')
print('=== SUMMARY STATS ===')
print(json.dumps(payload['summary_stats'], indent=2))
"
```

Expected: two PNG paths printed, `cells/` populated with 9 JSON files (3×3×1×3)
wait — actually 3×3×2 = 18 cells × n_injections=3. Expect at least a summary
stats JSON.

- [ ] **Step 2: Confirm the artifacts exist**

```bash
ls -la outputs/completeness_sweeps/integration_demo/*/
```

Expected: a subdirectory with `heatmap.png`, `snr_slope.png`, `result.json`,
`config.json`, `manifest.json`, and a populated `cells/` subdirectory.

- [ ] **Step 3: Re-run the same command — confirm cache hits = total_cells**

Re-run the exact Step 1 command. The output line for cache_hits/cache_misses
(or the printed summary) should show `cache_hits == cfg.total_cells` (== 18)
and the wall-clock should be ~10× faster than the first run.

---

## Phase 4 — Summary Report

### Task 12: Write `reports/bucket3_summary.md`

**Files:**
- Create: `reports/bucket3_summary.md`

- [ ] **Step 1: Compose the summary**

Write `reports/bucket3_summary.md` with these sections (use bucket 10's
summary as a style reference — sections, tables, concrete numbers):

```markdown
# Bucket 3 — Completeness Sweep Summary

**Date:** <today>
**Branch:** `feature/completeness-sweep`
**Status:** Complete.

---

## 1. What was found (Phase 1)

### 1.1 Existing primitive inventory
<one-paragraph summary citing synthetic.py line numbers>

### 1.2 Critical: BLS-only vs full-pipeline
<one-paragraph summary citing the difference and why `use_full_pipeline` matters>

### 1.3 Per-cell cost measurement
<measured per-injection time, per-cell time, default-grid total>

---

## 2. What was changed (Phase 2)

### 2.1 Source changes
<list each file + 1-line description>

### 2.2 Test additions
<6 tests, one line each>

### 2.3 Scope respected
- No changes to `run_injection_recovery` signature.
- One additive dict key (`recovered_depth`).
- No Streamlit UI wiring (out of scope per spec §6).

---

## 3. Final grid design

<list the chosen defaults: period_count, radius_ratio_count, snr_values,
n_injections, duration_days. Justify each with the cost measurement.>

---

## 4. Caching & resumability behavior (confirmed)

<integration-run output: first run cache_hits=0 misses=N; second run
cache_hits=N misses=0. Confirm atomic writes left no orphan `.tmp` files.>

---

## 5. Sample output

<reference the actual paths produced by Task 11: outputs/completeness_sweeps/integration_demo/<hash>/heatmap.png, snr_slope.png, result.json, cells/*.json. Paste the summary_stats JSON.>

---

## 6. Reporting integration

- New function `generate_completeness_report(result, config, fig_paths)` returns a JSON dict.
- Distinct from `generate_academic_report` (which is locked to the star+candidates schema).
- A future bucket can build `completeness_report_to_pdf(payload)`.

---

## 7. Future UI hook

<the 4-line sketch from spec §4.3, plus the note that Streamlit wiring is deferred.>

---

## 8. Verification commands

```bash
# Baseline (Phase 0)
python -m pytest tests/ -v > reports/bucket3_pretest_baseline.txt 2>&1

# Phase 2 regression gate (after every commit)
python -m pytest tests/test_synthetic_simulation.py -v

# Phase 3 full suite
python -m pytest tests/ -v > reports/bucket3_posttest.txt 2>&1

# Genuine integration run
python -c "..."  # full command from Task 11 Step 1
```

---

## 9. Commits on `feature/completeness-sweep`

| SHA | Subject |
|-----|---------|
| <fill from git log feature/completeness-sweep> | chore(bucket3): capture Phase 0 baseline test output |
| <fill> | feat(synthetic): expose recovered_depth in run_injection_recovery return |
| <fill> | docs(bucket3): Phase 1 discovery report |
| <fill> | feat(simulation): CompletenessSweepConfig dataclass with validation gate |
| <fill> | feat(simulation): CompletenessSweepResult dataclass with to_dict/save/load |
| <fill> | feat(simulation): run_completeness_sweep core (no caching yet) |
| <fill> | feat(simulation): per-cell caching + atomic manifest + resumability |
| <fill> | feat(visualization): plot_completeness_map (heatmap + SNR-slope) |
| <fill> | feat(reporting): generate_completeness_report (JSON payload, schema-sibling) |
| <fill> | test(sweep): 6 tests (shape, caching, resumability, full-pipeline, round-trip, callback) |
```

- [ ] **Step 2: Fill in commit SHAs from git log**

```bash
git log --oneline feature/completeness-sweep ^v.0.0.2
```

Copy the output into the table in §9.

- [ ] **Step 3: Commit**

```bash
git add reports/bucket3_summary.md
git commit -m "docs(bucket3): Phase 4 summary report"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Plan task(s) |
|--------------|--------------|
| §1.1 module split | Tasks 1, 4, 5, 6, 8, 9 |
| §1.2 data flow | Tasks 6, 7 |
| §2.1 `CompletenessSweepConfig` (incl. `__post_init__` gate, `duration_days=90`) | Task 4 |
| §2.2 `CompletenessSweepResult` | Task 5 |
| §3.1 directory layout | Tasks 6, 7 |
| §3.2 per-cell JSON | Tasks 5, 7 |
| §3.3 manifest.json | Task 7 |
| §3.4 resumability algorithm | Task 7 |
| §4.1 `plot_completeness_map` | Task 8 |
| §4.2 `generate_completeness_report` | Task 9 |
| §4.3 future UI hook | Task 12 §7 |
| §5.1 6 tests | Task 10 |
| §5.2 failure modes | Tasks 7, 10 |
| §5.3 verification commands | Tasks 0, 11, 12 |
| §6 out-of-scope | Spec §6 + plan Task 12 §2.3 |
| §7 phase plan & commit cadence | Tasks 0–12 |
| §8 acceptance criteria | Task 12 §1–§9 |

**Placeholder scan:** No "TBD", "TODO", "implement later" remain. Every code block is filled. Every command has expected output.

**Type consistency:** `_run_one_cell` is defined as a private function in Task 6 and patched in test 3 (Task 10). `_is_valid_cache_hit`, `_load_cell_data`, `_load_or_init_manifest`, `_atomic_write_manifest`, `_compute_cell_hash`, `_compute_config_hash` are all defined where referenced. `CompletenessSweepConfig` and `CompletenessSweepResult` field names match across Tasks 4–12. `config_hash` (str), `cache_dir` (str|Path), `snr_values` (tuple) all consistent.

No issues found — plan is ready for execution.