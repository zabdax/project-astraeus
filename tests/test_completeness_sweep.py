"""Tests for the completeness sweep layer (bucket 3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from astraeus.simulation.completeness import (
    CompletenessSweepConfig,
    CompletenessSweepResult,
    run_completeness_sweep,
)


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
    np.testing.assert_array_equal(r1.recovery_rate, r2.recovery_rate)


def test_resumability_after_interruption(tmp_path: Path, monkeypatch) -> None:
    """Simulate an interrupted sweep: raises after 4 cells are committed.

    A re-run should pick up at cell 5 with cache_hits=4.
    """
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

    monkeypatch.setattr(cm, "_run_one_cell", original_run_one)
    r2 = run_completeness_sweep(cfg)
    assert r2.cache_hits == 4
    assert r2.cache_misses == cfg.total_cells - 4


def test_use_full_pipeline_changes_recovery_semantics(tmp_path: Path) -> None:
    """BLS-only and full-pipeline modes must produce different config hashes
    (mode-aware caching) and full-pipeline typically yields <= recovery."""
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

    assert r_bls.config_hash != r_full.config_hash
    assert r_full.recovery_rate.sum() <= r_bls.recovery_rate.sum() + 1e-9


def test_result_to_dict_load_roundtrip(tmp_path: Path) -> None:
    cfg = _tiny_config(tmp_path / "roundtrip_test")
    result = run_completeness_sweep(cfg)
    out_path = tmp_path / "roundtrip_test" / result.config_hash / "result.json"
    result.save(out_path)
    loaded = CompletenessSweepResult.load(out_path)
    np.testing.assert_array_equal(result.recovery_rate, loaded.recovery_rate)
    np.testing.assert_array_equal(result.n_recovered, loaded.n_recovered)
    assert result.config_hash == loaded.config_hash


def test_progress_callback_invoked_per_cell(tmp_path: Path, monkeypatch) -> None:
    cfg = CompletenessSweepConfig(
        period_count=2, radius_ratio_count=2, snr_values=(10.0,),
        n_injections=1, seed=42, cache_dir=str(tmp_path / "callback_test"),
    )
    canned_cell = {
        "config_hash": "fake",
        "cell": {"period_days": 1.0, "radius_ratio": 0.05, "snr": 10.0,
                 "n_injections": 1, "mode": "bls_only"},
        "result": {"recovery_rate": 1.0, "period_err_median": 0.0,
                   "period_err_std": 0.0, "depth_err_median": 0.0,
                   "depth_err_std": 0.0, "n_recovered": 1,
                   "runtime_seconds": 0.001,
                   "injection_records": [{"seed": 42, "recovered": True,
                                          "recovered_period": 1.0,
                                          "recovered_depth": 0.0025,
                                          "recovered_snr": 10.0,
                                          "vetting_status": "n/a"}]},
        "schema_version": 1,
        "written_at_iso": "2026-06-23T00:00:00Z",
    }
    import astraeus.simulation.completeness as mod
    monkeypatch.setattr(mod, "_run_one_cell", lambda *a, **kw: canned_cell)
    
    calls: list[tuple[int, int]] = []

    def cb(current: int, total: int, cell_data: dict) -> None:
        calls.append((current, total))

    result = run_completeness_sweep(cfg, progress_callback=cb)
    
    assert result.cache_misses == 4  # 2x2x1 = 4 cells
    assert len(calls) == 4
    assert all(calls[i][0] == i + 1 for i in range(4))
    assert all(calls[i][1] == 4 for i in range(4))