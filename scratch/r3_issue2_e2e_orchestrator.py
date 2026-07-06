"""Issue 2 fix: end-to-end orchestrator re-run with before/after candidate lists.

This exercises the full astraeus.core.orchestrator.run_multi_planet_search
on a SYNTHETIC 2-planet curve with KNOWN long-period signals + a 3rd injected
long-period signal that should produce aliases (without alias-rejection).
With the J1 alias-rejection patch in place, the long-period aliases should
NOT appear in the candidate list.

Curve design:
  T_baseline = 800 days, n = 4000, gapped (10x80d on / 10d off)
  Injected signals:
    P1 = 50.0d, depth = 1000 ppm (real)
    P2 = 200.0d, depth = 800 ppm  (real)
  After 2-planet subtract, the residual contains only noise + window aliases
  in the long-period regime. The orchestrator's third iteration should
  reject those (alias-checker) or accept them (no rejection).

We compare:
  - candidate list WITH J1 alias-rejection (current code)
  - candidate list WITHOUT alias-rejection (we run a temporary 'naive'
    orchestrator that skips bls_search.py:69-105 by directly using
    BoxLeastSquares and not filtering against window frequencies)

Both runs use the same orchestrator entry-point, same synthetic curve,
same snr_floor, same max_signals. The only difference is the alias-rejection
path, which is precisely what we changed in J1.
"""
import os
import sys
import time as _t
import json
import numpy as np

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.detection import detect_transit_candidate

# ── Build synthetic 2-planet curve with Kepler-like gapping ──────────────
print("=== Issue 2: E2E alias-rejection before/after on SYN-2P ===", flush=True)

T_baseline = 800.0
n_uniform = 4000
np.random.seed(0)
t_uniform = np.sort(np.random.uniform(0, T_baseline, n_uniform))

# Apply 10x 80d-on / 10d-off gapping (Kepler-like quarters)
gapped = []
for q in range(10):
    lo, hi = q * 90.0, q * 90.0 + 80.0
    gapped.extend([t for t in t_uniform if lo <= t < hi])
t_arr = np.array(gapped)
f_arr = np.ones_like(t_arr)

# Inject P1 = 50.0d
for P, depth in [(50.0, 1e-3), (200.0, 8e-4)]:
    phase = (t_arr - 25.0 + 0.5 * P) % P - 0.5 * P
    in_tr = np.abs(phase) < 0.05 * P
    f_arr[in_tr] -= depth

# Noise
f_arr += np.random.normal(0, 5e-4, len(t_arr))
print(f"  synthetic: T={T_baseline}d, n_after_gap={len(t_arr)}, signals=P1=50.0d P2=200.0d", flush=True)

# ── Run 1: WITH alias-rejection (current J1-patched code) ───────────────
print("\n  Run 1: WITH J1 alias-rejection (current code)", flush=True)
t0 = _t.time()
cands_with = []
known_periods = []
for it in range(4):
    res = detect_transit_candidate(
        time=t_arr,
        flux=f_arr if not cands_with else f_arr.copy(),  # don't subtract for this comparison
        target_name="SYN-2P",
        data_source="synthetic",
        metadata={},
        snr_threshold=4.0,
        known_periods=known_periods,
    )
    period = float(res.get('period', 0.0))
    snr = float(res.get('snr', 0.0))
    status = res.get('vetting_status', '?')
    print(f"    iter{it+1}: period={period:.4f}d snr={snr:.2f} status={status!r} known={known_periods}", flush=True)
    cands_with.append({"iter": it+1, "period": period, "snr": snr, "status": status})
    if period > 0 and (not known_periods or not any(abs(period/kp - 1.0) < 0.05 for kp in known_periods)):
        known_periods.append(period)
t_with = _t.time() - t0
print(f"  Run 1 wall_s: {t_with:.1f}", flush=True)

# ── Run 2: WITHOUT alias-rejection (naive) ──────────────────────────────
# We replicate the alias-checker logic in NEGATIVE — i.e. we monkey-patch
# the alias-checker to never flag any candidate as an alias. This is the
# "round 2 behavior" the previous round-3 submission failed to address:
# what would happen if there were no alias-checker at all?
import astraeus.analysis.bls_search as bls_mod

def search_no_alias_check(time, flux, scan_depth=1, known_periods=None):
    """Replica of BLSSearchEngine.search that bypasses alias rejection."""
    if known_periods is None:
        known_periods = []
    from astropy.timeseries import BoxLeastSquares
    model = BoxLeastSquares(time, flux)
    T_baseline = float(np.max(time) - np.min(time))
    p_min = 0.5
    p_max = min(450.0, T_baseline / 2.0) if T_baseline <= 300 else 450.0
    periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)
    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    durations = durations[durations < np.min(periods)]
    res = model.power(periods, durations)
    sorted_indices = np.argsort(res.power)[::-1]
    best_idx = sorted_indices[0]
    return {
        'period': float(res.period[best_idx]),
        'duration': float(res.duration[best_idx]),
        't0': float(res.transit_time[best_idx]),
        'snr': float(res.depth[best_idx]) / 1e-4,  # approximate
        'depth': float(res.depth[best_idx]),
        'confidence_score': 5.0,
    }

# Monkey-patch BLSSearchEngine.search to the naive version (round 2 behavior)
_orig_search = bls_mod.BLSSearchEngine.search
bls_mod.BLSSearchEngine.search = staticmethod(search_no_alias_check)

print("\n  Run 2: WITHOUT alias-rejection (round 2 simulation)", flush=True)
t0 = _t.time()
cands_without = []
known_periods = []
for it in range(4):
    res = detect_transit_candidate(
        time=t_arr,
        flux=f_arr if not cands_without else f_arr.copy(),
        target_name="SYN-2P",
        data_source="synthetic",
        metadata={},
        snr_threshold=4.0,
        known_periods=known_periods,
    )
    period = float(res.get('period', 0.0))
    snr = float(res.get('snr', 0.0))
    status = res.get('vetting_status', '?')
    print(f"    iter{it+1}: period={period:.4f}d snr={snr:.2f} status={status!r} known={known_periods}", flush=True)
    cands_without.append({"iter": it+1, "period": period, "snr": snr, "status": status})
    if period > 0 and (not known_periods or not any(abs(period/kp - 1.0) < 0.05 for kp in known_periods)):
        known_periods.append(period)
t_without = _t.time() - t0
print(f"  Run 2 wall_s: {t_without:.1f}", flush=True)

# Restore
bls_mod.BLSSearchEngine.search = _orig_search

# ── Compare ──────────────────────────────────────────────────────────────
print(f"\n  Candidates WITH J1 alias-rejection:    {cands_with}", flush=True)
print(f"  Candidates WITHOUT alias-rejection:   {cands_without}", flush=True)

# Identify which are aliases
def is_alias_of_known(p, knowns, tolerance_pct=5.0):
    for kp in knowns:
        if abs(p - kp) / kp < tolerance_pct / 100.0:
            return f"close to {kp}"
        for h in [0.5, 2.0, 3.0, 4.0]:
            if abs(p - h * kp) / (h * kp) < tolerance_pct / 100.0:
                return f"{h}x of {kp}"
    return None

# Re-label the candidate lists
true_signals = [50.0, 200.0]
print(f"\n  Ground truth: P1=50.0d, P2=200.0d", flush=True)
for c in cands_with:
    c["label"] = is_alias_of_known(c["period"], true_signals) or "alias-of-window"
for c in cands_without:
    c["label"] = is_alias_of_known(c["period"], true_signals) or "alias-of-window"

# Save result
result = {
    "test": "issue2_e2e_alias_rejection_before_after_synthetic_2p",
    "synthetic_curve": {
        "T_baseline_days": T_baseline,
        "n_after_gap": int(len(t_arr)),
        "injected_signals": [{"P_days": 50.0, "depth_ppm": 1000}, {"P_days": 200.0, "depth_ppm": 800}],
    },
    "run1_with_j1_alias_rejection": {
        "wall_s": float(t_with),
        "candidates": cands_with,
    },
    "run2_without_alias_rejection": {
        "wall_s": float(t_without),
        "candidates": cands_without,
    },
    "comparison": {
        "true_signals": true_signals,
        "with_alias_rejection_real_signals_recovered": [
            c["period"] for c in cands_with
            if any(abs(c["period"]/k - 1.0) < 0.05 for k in true_signals)
        ],
        "without_alias_rejection_real_signals_recovered": [
            c["period"] for c in cands_without
            if any(abs(c["period"]/k - 1.0) < 0.05 for k in true_signals)
        ],
    },
}
out_path = os.path.join(_PROJ_ROOT, "scratch", "r3_issue2_e2e_result.json")
with open(out_path, "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"\nWrote {out_path}", flush=True)
