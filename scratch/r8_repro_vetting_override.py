"""R8 — Reproduce the vetting-override bypass on a minimal input.

Round 7's J7c run hit this on the real Kepler-90 curve: iter 1's
489.13d spurious peak was correctly rejected by TLS (tls_sde=4.22 < 5.0,
tls_valid=False), but VettingEngine then set vetting_status =
'Verified Planet Candidate (Likely Planet)' (detection.py:328-329),
and the orchestrator's GUARDRAIL 1 string-prefix check
(vetting_status.startswith('Verified Planet Candidate')) accepted it
anyway. The TLS gate was bypassed for the structural reason that the
classifier can override the gate's outcome via a string that the
orchestrator reads with .startswith().

This script reproduces the bypass on a minimal synthetic input so the
bug is observable without needing the full real-curve stack, and so a
regression test can lock the fix in round 8.

Repro strategy:
  1. Build a synthetic curve with a single planet (the 'real' signal).
  2. Patch detection.detect_transit_candidate's TLS branch to force
     tls_valid=False and tls_sde=4.0 (the exact scenario from J7c iter 1).
  3. Call detect_transit_candidate and observe:
       - is_valid:  should be False (since tls_valid is False)
       - vetting_status: starts as 'rejected' (from line 198 default)
       - VettingEngine override: sets it to 'Verified Planet Candidate
         (Likely Planet)' via line 329 (Likely Planet override)
       - final vetting_status: starts with 'Verified Planet Candidate'
  4. Simulate the orchestrator's GUARDRAIL 1 check: print whether the
     string-prefix check would have accepted this rejected-by-TLS
     candidate.
  5. Report whether the orchestrator's accept path WOULD proceed to
     subtract this candidate and consume an iteration slot — yes, in
     J7c's actual run it did.

The fix (round 8) is to either:
  (a) prevent VettingEngine from setting 'Verified Planet Candidate*'
      strings when tls_valid is False (preserve the load-bearing TLS
      gate at the classifier level), or
  (b) make the orchestrator's GUARDRAIL 1 check both
      vetting_status.startswith('Verified Planet Candidate') AND
      tls_valid is True (preserve the load-bearing TLS gate at the
      orchestrator level).

Either is a one-line change; (b) is the safer defense-in-depth because
it doesn't depend on every VettingEngine override respecting the TLS
gate, only on the orchestrator's accept path. This script does NOT
implement the fix — it just proves the bypass exists so the fix has
a clear contract to satisfy.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# --- Minimal synthetic curve (one planet at 10d, depth 0.1%) -----------
PERIOD_D = 10.0
DUR_D = 0.1
DEPTH = 1e-3
T0 = 5.0
N = 5000
T = np.linspace(0, 200.0, N)  # 200d baseline, 50 transits
rng = np.random.default_rng(seed=20260708)
F = 1.0 + 1e-4 * rng.standard_normal(N)
phase = (T - T0 + 0.5 * PERIOD_D) % PERIOD_D - 0.5 * PERIOD_D
F[np.abs(phase) < DUR_D / 2.0] -= DEPTH


def main() -> int:
    print("=" * 78, flush=True)
    print("[R8] Vetting-override bypass repro — minimal synthetic", flush=True)
    print("=" * 78, flush=True)

    # Patch detect_transit_candidate's TLS branch to return tls_valid=False
    # at SDE=4.0. This is the exact J7c iter-1 shape (tls_sde=4.22).
    # The patch only forces the TLS result; the rest of detect_transit_
    # candidate runs as production.
    from astraeus.analysis import detection

    def _force_tls_fail(model_self, *args, **kwargs):
        class _R:
            SDE = 4.0
            period = PERIOD_D
            FAP = 0.5
        return _R()

    # We need to import transitleastsquares in detection's namespace and
    # patch its .power to return a low-SDE result. Simpler: monkey-patch
    # detection's TLS .power via a context manager.
    import transitleastsquares as tls
    with mock.patch.object(tls.transitleastsquares, "power",
                            side_effect=_force_tls_fail):
        t0 = time.perf_counter()
        result = detection.detect_transit_candidate(
            time=T, flux=F, target_name="R8-bug-repro",
            data_source="synthetic", snr_threshold=7.1,
        )
        wall = time.perf_counter() - t0

    print(f"[R8] detect_transit_candidate wall: {wall:.2f}s", flush=True)
    print(f"[R8] result.period         = {result.get('period'):.4f}d", flush=True)
    print(f"[R8] result.snr            = {result.get('snr'):.2f}", flush=True)
    print(f"[R8] result.tls_valid      = {result.get('tls_valid')}", flush=True)
    print(f"[R8] result.tls_sde        = {result.get('tls_sde')}", flush=True)
    print(f"[R8] result.is_candidate   = {result.get('is_candidate')}", flush=True)
    print(f"[R8] result.candidate_found = {result.get('candidate_found')}", flush=True)
    print(f"[R8] result.vetting_status = {result.get('vetting_status')!r}", flush=True)
    print(f"[R8] result.confidence_score = {result.get('confidence_score')}", flush=True)

    # The critical observation
    is_valid = result.get("is_candidate")
    vetting = result.get("vetting_status", "")
    tls_valid = result.get("tls_valid")
    string_prefix_passes = (
        isinstance(vetting, str) and vetting.startswith("Verified Planet Candidate")
    )
    load_bearing_tls_gate = is_valid is True  # production emission gate

    print()
    print("=" * 78, flush=True)
    print("[R8] ORCHESTRATOR GUARDRAIL 1 (orchestrator.py:168-170):", flush=True)
    print(
        f"     if snr < snr_floor OR NOT vetting_status.startswith("
        f"'Verified Planet Candidate')"
    )
    print("=" * 78, flush=True)
    print(f"[R8]   snr < snr_floor?                = {result.get('snr') < 7.1}")
    print(f"[R8]   vetting.startswith('Verified...')? = {string_prefix_passes}")
    print(f"[R8]   ORCHESTRATOR HALTS?              = "
          f"{result.get('snr') < 7.1 or not string_prefix_passes}")
    print()
    print("=" * 78, flush=True)
    print("[R8] LOAD-BEARING TLS GATE (detection.py:164-168 emission gate):", flush=True)
    print("     is_valid = (snr > snr_threshold AND confidence >= floor AND tls_valid)", flush=True)
    print("=" * 78, flush=True)
    print(f"[R8]   tls_valid?                       = {tls_valid}")
    print(f"[R8]   is_valid (emission gate)?        = {is_valid}")
    print()
    print("=" * 78, flush=True)
    print("[R8] BUG:", flush=True)
    if string_prefix_passes and is_valid is False and tls_valid is False:
        print("[R8]   BUG CONFIRMED: orchestrator's string-prefix check ACCEPTS a")
        print("[R8]   candidate that the production emission gate REJECTED for")
        print("[R8]   failing the TLS gate. The TLS gate is bypassed at the")
        print("[R8]   orchestrator level by the VettingEngine's 'Likely Planet'")
        print("[R8]   override (detection.py:328-329).")
    elif string_prefix_passes and is_valid is True:
        print("[R8]   Bypass not reproduced in this minimal case: the candidate")
        print("[R8]   passed BOTH the emission gate and the string-prefix check.")
        print("[R8]   J7c's real-curve scenario may require the real 45,853-")
        print("[R8]   cadence stitch to trigger the override; investigate the")
        print("[R8]   VettingEngine branch path that fired in J7c (likely the")
        print("[R8]   geometric vet cleared for the 489d spurious peak).")
    else:
        print(f"[R8]   Unexpected state: vetting={vetting!r}  is_valid={is_valid}  "
              f"tls_valid={tls_valid}")
    print("=" * 78, flush=True)

    out = {
        "experiment": "r8_repro_vetting_override — minimal repro of orchestrator TLS-gate bypass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "result": {
            "period": result.get("period"),
            "snr": result.get("snr"),
            "tls_valid": tls_valid,
            "tls_sde": result.get("tls_sde"),
            "is_candidate": is_valid,
            "vetting_status": vetting,
            "confidence_score": result.get("confidence_score"),
        },
        "diagnostic": {
            "string_prefix_passes": string_prefix_passes,
            "load_bearing_tls_gate": load_bearing_tls_gate,
            "bypass_reproduced": (
                string_prefix_passes and is_valid is False and tls_valid is False
            ),
        },
        "round7_origin": {
            "j7c_iter_1_period_d": 489.13,
            "j7c_iter_1_snr": 16.37,
            "j7c_iter_1_tls_sde": 4.22,
            "j7c_iter_1_vetting_status": "Verified Planet Candidate (Likely Planet)",
        },
    }
    out_path = _SCRIPT_DIR / "r8_repro_vetting_override_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[R8] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
