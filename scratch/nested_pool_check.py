"""
nested_pool_check.py
====================

Replicates the J2 production call stack on Windows:
  Streamlit UI  ->  submit_multi_planet_search (orchestrator.py)
  ->  multiprocessing.Process(target=_subprocess_search_worker)
  ->  detect_transit_candidate
  ->  tls.transitleastsquares(t, y)  with TLS defaults (use_threads=cpu_count())
  ->  TLS internally spawns multiprocessing.Pool(processes=use_threads)

The reviewer flagged that on Windows, a spawn-launched multiprocessing.Process
that then spawns its own multiprocessing.Pool can deadlock or hit a
"bootstrap phase" RuntimeError. This script measures whether the suspected
failure mode is real, with a hard kill timer so it cannot hang the harness.

Controls
--------
  CONTROL: worker process, TLS use_threads=1 (in-process single-threaded TLS,
           no nested pool).
  NESTED:  worker process, TLS use_threads=8 (TLS spawns its own pool from
           inside the worker — the suspected-broken configuration).

Both arms use the same synthetic 45,853-cadence curve at the same period
range that the J2c profile used (best_period=210.6 d, window
[200.077, 221.137] d). The only difference is the threading setting.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# -- Hard ceiling so a deadlock cannot hang the harness ---------------------
ARM_TIMEOUT_S = 600          # 10 min per arm
RESULT_TIMEOUT_S = ARM_TIMEOUT_S + 60

# -- Same parameters as j2c_tls_profiling ---------------------------------
N_CADENCES = 45_853
CADENCE_D = 29.4 / 60.0 / 24.0   # Kepler long cadence ~29.4 min in days
BEST_PERIOD_D = 210.6069
PERIOD_MIN = BEST_PERIOD_D * 0.95
PERIOD_MAX = BEST_PERIOD_D * 1.05


def make_synthetic_curve(n_cadences: int) -> tuple[np.ndarray, np.ndarray]:
    """Reproducible synthetic curve: constant flux + small noise, NO injected
    transit. We are not measuring detection quality, only call-stack
    completeness. A flat curve still drives TLS through the full grid; the
    inner Pool does the same work regardless."""
    rng = np.random.default_rng(seed=20260706)
    t = np.arange(n_cadences) * CADENCE_D
    y = 1.0 + 1e-4 * rng.standard_normal(n_cadences)
    return t, y


def worker_entry(q: "multiprocessing.Queue", use_threads: int) -> None:
    """Module-level worker — must be picklable on Windows (spawn)."""
    try:
        import transitleastsquares as tls
        q.put({"event": "imported_tls", "use_threads": use_threads})
        t, y = make_synthetic_curve(N_CADENCES)
        q.put({"event": "made_curve", "n": int(t.size)})
        model = tls.transitleastsquares(t, y)
        q.put({"event": "construct_ready"})
        t0 = time.perf_counter()
        # `show_progress_bar=False` matches detection.py. NO use_threads kwarg
        # so TLS picks its default (cpu_count()) — exactly what detection.py
        # does in production.
        results = model.power(
            period_min=PERIOD_MIN,
            period_max=PERIOD_MAX,
            show_progress_bar=False,
            use_threads=use_threads,
        )
        elapsed = time.perf_counter() - t0
        q.put({
            "event": "done",
            "elapsed_s": elapsed,
            "sde": float(results.SDE),
            "tls_period": float(results.period),
        })
    except Exception as exc:
        q.put({
            "event": "error",
            "type": type(exc).__name__,
            "message": str(exc)[:1000],
            "traceback": traceback.format_exc()[:4000],
        })


def run_arm(use_threads: int) -> dict:
    """Spawn a multiprocessing.Process that runs worker_entry, mirroring the
    orchestrator's submit_multi_planet_search call shape."""
    q: "multiprocessing.Queue" = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=worker_entry,
        args=(q, use_threads),
        daemon=True,
    )
    started = time.perf_counter()
    proc.start()
    events: list[dict] = []
    terminal = None
    deadline = started + ARM_TIMEOUT_S

    while True:
        if time.perf_counter() > deadline:
            # Hard kill — this is exactly the failure mode we are checking for
            proc.terminate()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
            terminal = {
                "event": "timed_out",
                "elapsed_s": ARM_TIMEOUT_S,
                "killed": True,
            }
            break
        try:
            msg = q.get(timeout=1.0)
        except Exception:
            if not proc.is_alive():
                # Process exited without a terminal message
                break
            continue
        events.append(msg)
        if msg["event"] in ("done", "error"):
            terminal = msg
            break

    proc.join(timeout=5)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=2)

    wall = time.perf_counter() - started
    return {
        "use_threads": use_threads,
        "wall_s": wall,
        "proc_alive_at_return": proc.is_alive(),
        "events": events,
        "terminal": terminal,
    }


def main() -> None:
    out_dir = PROJECT_ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_path = out_dir / f"nested_pool_check_{stamp}.json"

    print(f"[nested_pool_check] platform={platform.system()} python={sys.version.split()[0]}")
    print(f"[nested_pool_check] cpu_count={multiprocessing.cpu_count()}")
    print(f"[nested_pool_check] n_cadences={N_CADENCES} period_window=[{PERIOD_MIN:.3f}, {PERIOD_MAX:.3f}] d")
    print(f"[nested_pool_check] arm_timeout={ARM_TIMEOUT_S}s per arm\n")

    report: dict = {
        "experiment": "nested_pool_check — replicates J2 production call stack (multiprocessing.Process + TLS multiprocessing.Pool) on Windows",
        "platform": platform.platform(),
        "python": sys.version,
        "cpu_count": multiprocessing.cpu_count(),
        "n_cadences": N_CADENCES,
        "period_window_d": [PERIOD_MIN, PERIOD_MAX],
        "arm_timeout_s": ARM_TIMEOUT_S,
        "arms": [],
    }

    # Control first (use_threads=1) — should always complete quickly
    print("[arm CONTROL] multiprocessing.Process + TLS use_threads=1 ...")
    control = run_arm(use_threads=1)
    report["arms"].append(control)
    ct = control["terminal"] or {}
    if ct.get("event") == "done":
        print(f"  -> completed in {ct['elapsed_s']:.1f}s, SDE={ct['sde']:.3f}\n")
    else:
        print(f"  -> TERMINAL={ct}\n")

    # Nested (use_threads=8) — the suspected-broken configuration
    nested_threads = multiprocessing.cpu_count()
    print(f"[arm NESTED ] multiprocessing.Process + TLS use_threads={nested_threads} ...")
    nested = run_arm(use_threads=nested_threads)
    report["arms"].append(nested)
    nt = nested["terminal"] or {}
    if nt.get("event") == "done":
        print(f"  -> completed in {nt['elapsed_s']:.1f}s, SDE={nt['sde']:.3f}\n")
    else:
        print(f"  -> TERMINAL={nt}\n")

    # Verdict
    control_ok = control["terminal"] and control["terminal"].get("event") == "done"
    nested_ok = nested["terminal"] and nested["terminal"].get("event") == "done"
    if not control_ok:
        verdict = "INCONCLUSIVE — control arm failed; environment broken at a more basic level"
    elif nested_ok:
        # Both completed: nested-pool works on this Windows box; reviewer's
        # hypothesis is wrong, the original J2 hang is a different bug.
        speedup = control["terminal"]["elapsed_s"] / nested["terminal"]["elapsed_s"]
        verdict = (
            f"NESTED POOL WORKS on this Windows box. nested/control speedup={speedup:.2f}x. "
            f"Reviewer's hypothesis is falsified. The original J2 hang is NOT a nested-pool "
            f"bootstrap deadlock. Proceed to investigate other causes (CPU contention, "
            f"i/o, lock contention in queue/registry)."
        )
    else:
        # Control works, nested fails: reviewer's hypothesis is confirmed.
        verdict = (
            "NESTED POOL BROKEN on this Windows box — control arm completed, nested arm "
            f"terminated with {nt.get('event', 'unknown')}: {nt.get('message', '')}. "
            "This is the exact failure mode the reviewer predicted. The fix is forcing "
            "use_threads=1 inside the worker (or restructuring so TLS's pool is not nested "
            "inside another Process), NOT picking a faster duration-grid config. Options 1-3 "
            "must NOT proceed until the call path is fixed."
        )
    report["verdict"] = verdict
    print("[verdict]", verdict)

    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[nested_pool_check] wrote {out_path}")


if __name__ == "__main__":
    main()
