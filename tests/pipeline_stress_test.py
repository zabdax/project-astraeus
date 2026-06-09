#!/usr/bin/env python3
"""
================================================================================
  ASTRAEUS 6-LAYER PIPELINE STRESS TEST
  Target:  WASP-12 b
  Profiles:  RUN 1 – TESS-Only  |  RUN 2 – Kepler+TESS Fusion
================================================================================
Executes the full 6-layer artifact-verification pipeline *without* initialising
the Streamlit UI, using the raw ``_fetch_data_impl`` entry point.

Fail-safe tracing:
  • ``faulthandler`` enabled at script entry.
  • 90-second outer ``TimeoutEnforcer`` around Layer 1 (MAST is slow).
  • 25-second ``TimeoutEnforcer`` around Layers 2-6 (CPU-bound).
  • Full interpreter thread-stack dump on timeout.
"""

import gc
import os
import sys
import shutil
import time
import datetime
import threading
import _thread
import traceback
import faulthandler

# ── Activate faulthandler immediately ─────────────────────────────────────────
faulthandler.enable()

# ── Add project root to sys.path ──────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np


# ---------------------------------------------------------------------------
#  TimeoutEnforcer context manager (25-second hard ceiling)
# ---------------------------------------------------------------------------
class TimeoutEnforcer:
    """
    Context manager that forcefully dumps all interpreter thread stacks and
    interrupts the main thread if the enclosed block exceeds *timeout* seconds.
    """

    def __init__(self, timeout: float = 25.0, label: str = "Component"):
        self.timeout = timeout
        self.label = label
        self._timer: threading.Timer | None = None
        self._t0 = 0.0

    # -- timeout callback (runs on Timer thread) --
    def _on_timeout(self):
        print(
            f"\n{'='*72}\n"
            f"[FAIL-SAFE TIMEOUT] {self.label} exceeded {self.timeout:.1f}s!\n"
            f"Dumping active interpreter thread stacks…\n"
            f"{'='*72}",
            file=sys.stderr, flush=True,
        )
        faulthandler.dump_traceback(file=sys.stderr)
        # Interrupt main thread → raises KeyboardInterrupt there
        _thread.interrupt_main()

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._timer = threading.Timer(self.timeout, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._timer is not None:
            self._timer.cancel()
        elapsed = time.perf_counter() - self._t0
        if exc_type is KeyboardInterrupt:
            raise TimeoutError(
                f"[TIMEOUT] {self.label} was stuck for >{self.timeout:.1f}s "
                f"(elapsed {elapsed:.2f}s). Likely network/IO hang."
            )
        return False   # do not suppress other exceptions


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _banner(title: str):
    w = 72
    print(f"\n{'='*w}", file=sys.__stdout__)
    print(f"  {title}", file=sys.__stdout__)
    print(f"{'='*w}", file=sys.__stdout__)


def _layer_enter(n: int, name: str):
    print(f"[{_ts()}] [LAYER {n} ENTERING] {name}…", file=sys.__stdout__)


def _layer_ok(n: int, name: str, elapsed: float, detail: str = ""):
    extra = f" — {detail}" if detail else ""
    print(f"[{_ts()}] [LAYER {n} SUCCESS]  {name} completed in {elapsed:.3f}s{extra}", file=sys.__stdout__)


def _layer_fail(n: int, name: str, reason: str):
    print(f"[{_ts()}] [LAYER {n} FAILED]   {name}: {reason}", file=sys.__stdout__)


# ---------------------------------------------------------------------------
#  run_pipeline  –  single execution path for one mission profile
# ---------------------------------------------------------------------------
def run_pipeline(target_name: str, run_label: str, mission_profile: str):
    """Execute all 6 layers sequentially and print layer-by-layer telemetry."""

    _banner(f"{run_label}  |  Target: {target_name}  |  Profile: {mission_profile}")

    # Lazy-import to avoid touching Streamlit at module level
    from astraeus.core.ingestion import RemoteDiscoveryEngine
    from astraeus.analysis.detection import detect_transit_candidate

    # ── Pre-emptive cache wipe to remove truncated FITS left by prior ──
    #    timed-out daemon threads that may still hold file locks.
    _cache = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")
    if os.path.exists(_cache):
        try:
            shutil.rmtree(_cache)
            print(f"[{_ts()}] Pre-emptive cache wipe: removed '{_cache}'")
        except Exception as e:
            print(f"[{_ts()}] Pre-emptive cache wipe failed (non-fatal): {e}")

    # ══════════════════════════════════════════════════════════════════════
    #  LAYER 1 — Multi-Mission Ingestion & Stitching
    # ══════════════════════════════════════════════════════════════════════
    _layer_enter(1, "Multi-Mission Ingestion & Stitching")
    try:
        with TimeoutEnforcer(90.0, f"Layer 1 ({run_label})"):
            t0 = time.perf_counter()
            data = RemoteDiscoveryEngine._fetch_data_impl(target_name, mission_profile)
            elapsed_l1 = time.perf_counter() - t0
    except TimeoutError as te:
        _layer_fail(1, "Ingestion", str(te))
        return
    except Exception as exc:
        _layer_fail(1, "Ingestion", f"Exception: {exc}")
        traceback.print_exc()
        return

    status = data.get("status", "unknown")
    if status != "success":
        _layer_fail(1, "Ingestion", f"Non-success status '{status}'. "
                    f"archive_error={data.get('archive_error')}  "
                    f"mast_error={data.get('mast_error')}")
        return

    time_arr = data["time"]
    flux_arr = data["flux"]
    flux_err = data.get("flux_err", np.zeros_like(time_arr))
    metadata = data.get("metadata", {})

    # Validate chronological sorting & finite values
    assert np.all(np.isfinite(time_arr)), "LAYER 1 ASSERT: time contains non-finite values"
    assert np.all(np.isfinite(flux_arr)), "LAYER 1 ASSERT: flux contains non-finite values"
    assert np.all(np.diff(time_arr) >= 0), "LAYER 1 ASSERT: timestamps not monotonically sorted"

    st_rad = metadata.get("st_rad", metadata.get("stellar_radius", "?"))
    _layer_ok(1, "Ingestion & Stitching", elapsed_l1,
              f"{len(time_arr)} points | st_rad={st_rad}")

    # ══════════════════════════════════════════════════════════════════════
    #  LAYERS 2-6 — Analysis sweep (executed inside detect_transit_candidate)
    #  The function itself chains:
    #     L2  Lomb-Scargle + Wotan/median detrend
    #     L3  BLS multi-planet masking loop (up to 3 passes)
    #     L4  V-Shape metric + secondary eclipse vetting
    #     L5  Physical Mandel-Agol sizing + JWST TSM
    #     L6  TTV O-C residual engine
    # ══════════════════════════════════════════════════════════════════════
    _layer_enter(2, "Lomb-Scargle Adaptive Windows & Detrending")
    _layer_enter(3, "Multi-Planet Masking Iteration (BLS × 3)")
    _layer_enter(4, "Geometric V-Shape & Secondary Eclipse Vetting")
    _layer_enter(5, "Physical Mandel-Agol Sizing & JWST TSM Scales")
    _layer_enter(6, "Timing Variation Tracking (TTV)")

    try:
        with TimeoutEnforcer(25.0, f"Layers 2-6 ({run_label})"):
            t0 = time.perf_counter()
            candidates = detect_transit_candidate(
                time=time_arr,
                flux=flux_arr,
                target_name=target_name,
                data_source=mission_profile,
                metadata=metadata,
                snr_threshold=5.0,
            )
            elapsed_analysis = time.perf_counter() - t0
    except TimeoutError as te:
        _layer_fail(2, "Analysis Sweep", str(te))
        return
    except Exception as exc:
        _layer_fail(2, "Analysis Sweep", f"Exception: {exc}")
        traceback.print_exc()
        return

    # ── Post-analysis layer-by-layer validation ───────────────────────────
    if not candidates:
        _layer_ok(2, "Detrending", elapsed_analysis, "completed (no candidates found)")
        _layer_ok(3, "BLS Search", 0.0, "no signal above threshold")
        _layer_ok(4, "Vetting", 0.0, "skipped — no candidates")
        _layer_ok(5, "Physical Sizing", 0.0, "skipped — no candidates")
        _layer_ok(6, "TTV Engine", 0.0, "skipped — no candidates")
        return

    for idx, entry in enumerate(candidates):
        cand = entry.get(f"candidate_{idx+1}", {})
        label = f"Candidate {idx+1}"
        print(f"\n{'─'*60}")
        print(f"  {label}")
        print(f"{'─'*60}")

        # LAYER 2 — detrending produced cleaned flux (implicit if we got here)
        rot_period = cand.get("stellar_rotation_period_days", 0)
        _layer_ok(2, "Lomb-Scargle Detrending", elapsed_analysis,
                  f"stellar rotation ≈ {rot_period:.4f} d")

        # LAYER 3 — BLS period detection
        period = cand.get("period_days", 0)
        depth  = cand.get("transit_depth", 0)
        snr    = cand.get("snr", 0)
        _layer_ok(3, "BLS Multi-Planet Search", 0.0,
                  f"P={period:.5f} d | depth={depth:.6f} | SNR={snr:.2f}")

        # LAYER 4 — geometric vetting
        v_shape = cand.get("v_shape_metric", 0)
        flat_frac = cand.get("flat_bottom_fraction", 0)
        sec_det = cand.get("secondary_eclipse_detected", False)
        sec_snr = cand.get("secondary_eclipse_snr", 0)
        vet_status = cand.get("vetting_status", "unknown")
        _layer_ok(4, "V-Shape & Secondary Vetting", 0.0,
                  f"V={v_shape:.4f} | flatFrac={flat_frac:.4f} | "
                  f"secEcl={'YES' if sec_det else 'NO'} (SNR {sec_snr:.2f}) | "
                  f"status='{vet_status}'")

        # LAYER 5 — physical sizing & TSM
        rp = cand.get("planet_radius_earth", 0)
        teq = cand.get("equilibrium_temp_k", 0)
        tsm = cand.get("jwst_tsm_score", 0)
        _layer_ok(5, "Mandel-Agol + JWST TSM", 0.0,
                  f"Rp={rp:.4f} R⊕ | Teq={teq:.1f} K | TSM={tsm:.4f}")

        # LAYER 6 — TTV
        ttv = cand.get("ttv_data", [])
        if ttv:
            residuals = [e["ttv_residual_min"] for e in ttv]
            _layer_ok(6, "TTV Wobble Engine", 0.0,
                      f"{len(ttv)} epochs | O-C range [{min(residuals):.2f}, "
                      f"{max(residuals):.2f}] min")
        else:
            _layer_ok(6, "TTV Wobble Engine", 0.0, "0 epochs (data gaps)")

    print(f"\n[{_ts()}] ✔ Full 6-layer sweep for {run_label} completed in "
          f"{elapsed_l1 + elapsed_analysis:.2f}s total "
          f"(L1={elapsed_l1:.2f}s  L2-6={elapsed_analysis:.2f}s)")


# ---------------------------------------------------------------------------
#  Main entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[{_ts()}] Pipeline Stress Test initialising…")
    print(f"[{_ts()}] faulthandler: enabled")
    print(f"[{_ts()}] Python {sys.version}")

    target = "WASP-12 b"

    # ── RUN 1 — Single-Mission Baseline (TESS-Only) ──────────────────────
    try:
        run_pipeline(target, "RUN 1: Single-Mission Baseline (TESS-Only)", "TESS")
    except Exception as e:
        print(f"\n[FATAL] RUN 1 aborted: {e}")
        traceback.print_exc()

    # Force-release any daemon thread resources before RUN 2
    gc.collect()
    time.sleep(2.0)

    # ── RUN 2 — Multi-Mission Fusion (Kepler + TESS) ─────────────────────
    try:
        run_pipeline(target, "RUN 2: Multi-Mission Fusion (Kepler+TESS)",
                     "Combined Baseline (Kepler + TESS)")
    except Exception as e:
        print(f"\n[FATAL] RUN 2 aborted: {e}")
        traceback.print_exc()

    _banner("ALL PIPELINE STRESS TESTS COMPLETED")
