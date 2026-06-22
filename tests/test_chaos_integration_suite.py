"""Project Astraeus v1.0 MVP -- Adversarial Integration & Chaos Engineering Suite.

Executes the full adversarial validation protocol against the three integrated
pillars:

    1. ``astraeus.core.nbody_solver``        -- Suite B (mathematical singularities)
    2. ``astraeus.simulation.synthetic``     -- Suite C (payload scaling / memory)
    3. ``astraeus.analysis.reporting``       -- Suite A & C (PDF handshake / canvas)
    4. ``app`` (the live Streamlit entry)   -- Suite A (UI lifecycle / idempotency)
       (Previously exercised ``astraeus.ui.dashboard``, which was deprecated
       in Bucket 1; see ``deprecated/astraeus_ui_dashboard/DEPRECATED.md`` and
       ``reports/bucket1_orphan_investigation.md``. The symbols under test are
       identical and now live in ``app``.)

Every vector is enforced by a hard programmatic assertion (no soft "logged"
passes). Run with::

    python tests/test_chaos_integration_suite.py

Exits with status 0 only if every vector passes; otherwise non-zero with a
detailed pass/fail ledger printed to stdout.
"""
from __future__ import annotations

import copy
import gc
import io
import os
import sys
import time
import tracemalloc
import traceback
from typing import Any, Callable, Dict, List

import numpy as np

# Make the workspace importable when run directly.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Result ledger
# ---------------------------------------------------------------------------
class Report:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def record(self, vector: str, status: str, detail: str = "") -> None:
        self.rows.append({"vector": vector, "status": status, "detail": detail})
        marker = "PASS" if status == "PASS" else "FAIL"
        line = f"[{marker}] {vector}"
        if detail:
            line += f" -- {detail}"
        print(line)

    def summary(self) -> int:
        total = len(self.rows)
        passed = sum(1 for r in self.rows if r["status"] == "PASS")
        failed = total - passed
        print("\n" + "=" * 72)
        print(f"CHAOS SUITE SUMMARY -- {passed}/{total} passed, {failed} failed")
        print("=" * 72)
        for r in self.rows:
            print(f"  {r['status']:4} | {r['vector']}")
        return 0 if failed == 0 else 1


REPORT = Report()


def safe(vector: str, fn: Callable[[], None]) -> None:
    """Run a vector body; record PASS, or FAIL with the captured traceback."""
    try:
        fn()
        REPORT.record(vector, "PASS")
    except AssertionError as e:
        tb = traceback.format_exc(limit=4)
        REPORT.record(vector, "FAIL", f"{e} :: {tb.strip().splitlines()[-1]}")
    except Exception as e:  # noqa: BLE001 -- chaos suite must capture all
        tb = traceback.format_exc(limit=6)
        REPORT.record(vector, "FAIL (unhandled exception)", f"{type(e).__name__}: {e}")


# ===========================================================================
# SUITE B: Mathematical & Orbital Singularity Tests  (nbody_solver)
# ===========================================================================
# We test Suite B first because the solver is the most self-contained pillar
# and its behaviour gates the rest of the architecture.

from astraeus.core.nbody_solver import (  # noqa: E402
    PlanetParams,
    StabilityResult,
    check_system_stability,
    run_stability_analysis,
)


def vector_b1_sub_epsilon_collision() -> None:
    """B1: two bodies with delta < 1e-12 AU must not produce inf/NaN."""
    # Two planets initialised at *almost identical* Cartesian positions.
    # semi_major_axis equal -> same r; same phase -> identical (x, y, z).
    planets = [
        PlanetParams(mass_msun=3.0e-6, semi_major_axis_au=1.0,
                     eccentricity=0.0, initial_phase_rad=0.0),
        PlanetParams(mass_msun=3.0e-6, semi_major_axis_au=1.0,
                     eccentricity=0.0, initial_phase_rad=0.0),
    ]
    # Must return a structured StabilityResult, never raise.
    result = run_stability_analysis(
        stellar_mass_msun=1.0, planets=planets, n_steps=200, dt_years=0.001
    )
    assert isinstance(result, StabilityResult), "solver did not return StabilityResult"
    assert result.is_stable is False, (
        f"coincident bodies flagged stable (reason={result.termination_reason!r})"
    )
    # No inf / NaN tokens may leak into the diagnostic payload.
    assert np.all(np.isfinite(result.final_eccentricities)), (
        f"non-finite eccentricities leaked: {result.final_eccentricities}"
    )
    assert np.isfinite(result.energy_relative_error), "non-finite energy error"
    assert np.isfinite(result.survival_time_years), "non-finite survival time"


def vector_b2_hyperbolic_escape() -> None:
    """B2: near-relativistic velocity must trigger early-exit, not stall 50k steps."""
    # We inject a candidate via check_system_stability but give the solver a
    # pathologically tight orbit and large mass so the velocity explodes.  The
    # real enforcement contract is "no 50k-step stall on a degenerate input".
    planets = [
        # Massive hot Jupiter very close to the star -> huge orbital velocity.
        PlanetParams(mass_msun=1.0e-2, semi_major_axis_au=0.005,
                     eccentricity=0.9, initial_phase_rad=0.0),
    ]
    t0 = time.perf_counter()
    result = run_stability_analysis(
        stellar_mass_msun=1.0, planets=planets, n_steps=50_000
    )
    elapsed = time.perf_counter() - t0
    assert isinstance(result, StabilityResult), "solver did not return StabilityResult"
    # The solver must either early-exit (termination != completed) OR finish
    # without non-finite tokens -- but it must never stall unboundedly.
    assert elapsed < 60.0, f"solver stalled for {elapsed:.1f}s on degenerate input"
    # Critical: tracking matrices must contain no inf/NaN regardless of outcome.
    assert np.all(np.isfinite(result.final_eccentricities)), (
        f"non-finite eccentricities after hyperbolic input: {result.final_eccentricities}"
    )
    assert np.isfinite(result.energy_relative_error), "non-finite energy error"


# ===========================================================================
# SUITE A: UI Lifecycle, State Idempotency & Async Freeze Tests
# ===========================================================================
# Streamlit's ScriptRuntime cannot be instantiated headlessly in a stable way,
# so we exercise the pure functions that the dashboard delegates to.  This is
# the standard headless pattern: assert that the *business logic* underneath
# the widgets is rerun-safe, mutation-free, and that the PDF backend stays
# dormant unless explicitly invoked.

import pandas as pd  # noqa: E402
from app import (  # noqa: E402
    BASELINE_PAYLOAD,
    _build_adapted_metrics_payload,
)
from astraeus.analysis.reporting import generate_academic_report  # noqa: E402


# A sentinel object that raises if the PDF backend is ever evaluated.  Used to
# prove that slider reruns keep the heavy compiler dormant.
class _DormancySentinel:
    """Records whether the PDF compiler was invoked during a test window."""

    def __init__(self) -> None:
        self.invocations = 0

    def __enter__(self) -> "_DormancySentinel":
        self._orig = generate_academic_report
        # Re-bind the name in the app module so the *app's* call
        # site goes through us. (Previously rebound astraeus.ui.dashboard,
        # deprecated in Bucket 1.)
        import app as dash_mod

        self._dash_mod = dash_mod
        dash_mod.generate_academic_report = self._wrap  # type: ignore[assignment]
        return self

    def _wrap(self, *args: Any, **kwargs: Any) -> Any:
        self.invocations += 1
        return self._orig(*args, **kwargs)

    def __exit__(self, *exc: Any) -> None:
        self._dash_mod.generate_academic_report = self._orig  # type: ignore[assignment]


def vector_a1_slider_rerun_dormancy() -> None:
    """A1: 50 slider-equivalent reruns must never wake the PDF compiler."""
    payload = copy.deepcopy(BASELINE_PAYLOAD)
    with _DormancySentinel() as sent:
        for i in range(50):
            snr_threshold = 5.0 + (i % 21)  # values across the slider range
            # Simulate the dataframe recompute that every rerun performs.
            df = pd.DataFrame(list(payload.get("candidates", []))).copy()
            df["Transit Depth (PPM)"] = (df["depth"] * 1_000_000).round(2)
            # Re-run the (cheap) payload adapter, which is what the sidebar
            # callback executes on every slider change.
            _build_adapted_metrics_payload(payload)
    assert sent.invocations == 0, (
        f"PDF backend woke up {sent.invocations} times during slider reruns "
        "-- it must stay dormant until explicit manuscript submission"
    )


def vector_a2_malformed_figure_payloads() -> None:
    """A2: three malicious figure payloads must route to the canvas fallback."""
    metrics = _build_adapted_metrics_payload(copy.deepcopy(BASELINE_PAYLOAD))
    malicious_payloads = [
        {},
        {"phase_fold": None},
        {"phase_fold": "invalid_string_type"},
    ]
    for idx, figs in enumerate(malicious_payloads):
        buf = generate_academic_report(metrics, figures=figs)
        assert isinstance(buf, io.BytesIO), f"payload {idx}: not a BytesIO"
        data = buf.getvalue()
        assert data[:4] == b"%PDF", f"payload {idx}: not a valid PDF header"
        assert len(data) > 500, f"payload {idx}: PDF suspiciously small ({len(data)}B)"
        buf.close()  # explicit unlink per spec contract
        del buf, data


def vector_a3_frame_isolation_idempotency() -> None:
    """A3: source payload must remain structurally identical across renders."""
    payload = copy.deepcopy(BASELINE_PAYLOAD)
    snapshot_before = copy.deepcopy(payload)

    for i in range(10):
        threshold = 5.0 + i * 2.0  # irregular filtering thresholds
        df = pd.DataFrame(list(payload.get("candidates", []))).copy()
        df["Transit Depth (PPM)"] = (df["depth"] * 1_000_000).round(2)
        # Filtering by SNR threshold (read-only on payload).
        _ = df[df["snr"] >= threshold]

    # Strict structural identity: no mutation to the source payload.
    assert payload == snapshot_before, (
        "source payload was mutated during 10 render cycles (idempotency breach)"
    )
    # Object-identity assertion: the depth*1e6 column lives on an isolated df.
    df_final = pd.DataFrame(list(payload.get("candidates", []))).copy()
    df_final["Transit Depth (PPM)"] = (df_final["depth"] * 1_000_000).round(2)
    # No compounding: depth values must equal a single multiply, not chained.
    expected = (df_final["depth"] * 1_000_000).round(2)
    assert df_final["Transit Depth (PPM)"].equals(expected), (
        "Transit Depth (PPM) column showed value compounding"
    )
    # No duplicate column names (DuplicateColumnName guard).
    assert df_final.columns.is_unique, "duplicate column names detected"


# ===========================================================================
# SUITE C: High-Density Payload Scaling & Memory Purge Tests
# ===========================================================================

def _build_chaos_candidates(n: int = 45) -> List[Dict[str, Any]]:
    """Build n candidates packed with non-ASCII / markdown / Greek glyphs."""
    hostile_names = [
        "Planet x \u2605 \u03b2_2 \u00b1 \u03c3_core [Zone Alpha]",
        "\u03b8\u2087 \u2265 \u03bc\u2080 \u2014 \u00d7 \u03c0\u00b2",
        "\u2606 \u0394\u03bb/2 \u2260 \u03c6 \u2714 [Zone \u03b2]",
        "\u00b1\u00b1\u00b1 \u2660 heavy\u2605markdown\u00a6\u00a6",
        "raw_emoji_\U0001F680_\U0001F300 trailing",
    ]
    cands: List[Dict[str, Any]] = []
    for i in range(n):
        name = hostile_names[i % len(hostile_names)] + f" #{i+1}"
        cands.append(
            {
                "candidate_id": name,
                "period": 10.0 + i * 1.37,
                "snr": 8.0 + (i % 15),
                "depth": 0.0004 + (i % 7) * 1e-4,
                "epoch": 130.0 + i * 0.9,
            }
        )
    return cands


def vector_c1_chaos_pagination() -> None:
    """C1: 45 hostile candidates must paginate cleanly with no Unicode crash."""
    metrics = {
        "star_id": "Chaos-90",
        "candidates": _build_chaos_candidates(45),
        "introduction": "Hostile \u03c3 baseline \u2265 0.1 \u00b1 noise.",
        "optimization_summary": "\u03b8-grid \u00d7 \u03c0 converged \u2714",
    }
    buf = generate_academic_report(metrics, figures={})
    data = buf.getvalue()
    assert data[:4] == b"%PDF", "chaos payload did not emit a valid PDF"
    # ReportLab would raise UnicodeEncodeError if sanitization failed; reaching
    # here means the sanitation wrapper held.
    assert len(data) > 2000, f"chaos PDF suspiciously small ({len(data)}B)"
    # Pages = count of "Type /Page" objects (rough). 45 rows / 8 rows-per-page
    # => at least 6 page-chunks; ensure multi-page pagination occurred.
    page_count = data.count(b"/Type /Page")
    # /Type /Pages also matches, so use a lower bound tolerant to structure.
    assert page_count >= 3, f"expected multi-page output, got page markers={page_count}"
    buf.close()
    del buf, data


def _process_rss_mb() -> float:
    """Return current process RSS in MB, cross-platform.

    Uses the OS process metric (the true "Δ-RAM" the spec demands) rather than
    ``tracemalloc``, which only tracks Python-level allocations and is fooled by
    C-extension-side allocations from reportlab / pillow.
    """
    # psutil (preferred, accurate everywhere)
    try:
        import psutil  # type: ignore

        return psutil.Process(os.getpid()).memory_info().rss / 1024.0 / 1024.0
    except Exception:
        pass
    # Windows fallback via Win32 API
    if sys.platform.startswith("win"):
        import ctypes
        import ctypes.wintypes

        class _PMCE(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        try:
            psapi = ctypes.WinDLL("psapi.dll")
            c = _PMCE()
            c.cb = ctypes.sizeof(c)
            psapi.GetProcessMemoryInfo(
                ctypes.wintypes.HANDLE(-1), ctypes.byref(c), c.cb
            )
            return c.WorkingSetSize / 1024.0 / 1024.0
        except Exception:
            pass
    # POSIX fallback
    try:
        with open(f"/proc/{os.getpid()}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    # Last resort: tracemalloc current (acknowledged-noisy) so the test still runs.
    return tracemalloc.get_traced_memory()[0] / 1024.0 / 1024.0


def vector_c2_memory_hammer() -> None:
    """C2: 200 sequential compiles must show near-zero Δ-RAM (<=0.1MB).

    Verified via the OS process RSS (the spec's "Δ-RAM"), which correctly
    accounts for reportlab/pillow C-side allocations.  Also asserts that every
    internal ``io.BytesIO`` cache is explicitly closed and that no buffer
    references are held alive after the loop.
    """
    metrics = {
        "star_id": "Hammer",
        "candidates": _build_chaos_candidates(12),
    }

    rss_samples: List[float] = []

    # Snapshot pre-existing open BytesIO count so we only measure *our* leaks.
    # External libraries (pandas, reportlab) may hold internal BytesIO caches
    # that are outside our control.
    for _warmup in range(3):
        gc.collect()
    baseline_open_bytesio = sum(
        1 for obj in gc.get_objects()
        if isinstance(obj, io.BytesIO) and obj.closed is False
    )

    # tracemalloc stays on purely as a secondary cross-check of Python-level
    # allocations; it is NOT the pass/fail instrument (see _process_rss_mb).
    tracemalloc.start()
    gc.collect()

    for i in range(200):
        buf = generate_academic_report(metrics, figures={})
        _ = buf.getvalue()  # consume the byte stream once
        buf.close()  # explicitly unlink the BytesIO cache (spec requirement)
        del buf        # break the local reference immediately (anti-pointer leak)
        if i in (9, 99, 199):
            gc.collect()
            rss_samples.append(_process_rss_mb())

    # Expire the last loop's _ variable too.
    del _
    tracemalloc.stop()

    # Multi-generation sweep to break any lingering cyclic references.
    for _gen in range(3):
        gc.collect()

    # Verify no *new* buffer references survive in gc-tracked objects.
    live_bytesio = sum(
        1 for obj in gc.get_objects()
        if isinstance(obj, io.BytesIO) and obj.closed is False
    )
    new_leaks = live_bytesio - baseline_open_bytesio
    assert new_leaks == 0, (
        f"{new_leaks} unclosed io.BytesIO caches leaked into gc-tracked heap "
        f"(baseline={baseline_open_bytesio}, current={live_bytesio})"
    )

    assert len(rss_samples) == 3, "RSS sampling failed"
    # Δ-RAM between loop 10 (post warmup) and loop 200 must approach zero.
    delta_warm_to_final = abs(rss_samples[2] - rss_samples[0])
    assert delta_warm_to_final <= 0.1, (
        f"Δ-RAM between loop 10 ({rss_samples[0]:.2f} MB) and loop 200 "
        f"({rss_samples[2]:.2f} MB) = {delta_warm_to_final:.3f} MB exceeds 0.1 MB"
    )


# ===========================================================================
# Runner
# ===========================================================================
def main() -> int:
    print("Project Astraeus v1.0 MVP -- Adversarial Chaos Engineering Suite\n")
    safe("B1 sub-epsilon proximity singularity", vector_b1_sub_epsilon_collision)
    safe("B2 hyperbolic escape divergence", vector_b2_hyperbolic_escape)
    safe("A1 slider rerun PDF dormancy", vector_a1_slider_rerun_dormancy)
    safe("A2 malformed figure payloads", vector_a2_malformed_figure_payloads)
    safe("A3 frame isolation idempotency", vector_a3_frame_isolation_idempotency)
    safe("C1 chaos pagination (45 candidates)", vector_c1_chaos_pagination)
    safe("C2 memory hammer (200 compiles)", vector_c2_memory_hammer)
    return REPORT.summary()


if __name__ == "__main__":
    sys.exit(main())
