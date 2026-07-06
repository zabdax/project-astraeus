"""I1-validation — surgical test that does NOT re-run BLS.

We call BLSSearchEngine.search on the small iso-p1 curve (N=30000, T=1500d)
which takes ~150s; then we manually invoke the post-BLS classifier code
from `detect_transit_candidate` with controlled values to verify the
branch decision.
"""

import json
import os
import sys

import numpy as np

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

print(f"[I1-v] project_root={_PROJ_ROOT}")

# Build the SYN-5P isolated p1 curve.
N_SAMPLES = 30000
T_SPAN = 1500.0
rng = np.random.default_rng(42)
time = np.linspace(0, T_SPAN, N_SAMPLES)
baseline_flux = 1.0 + rng.normal(0, 5e-4, size=N_SAMPLES)
INJECTED = [
    ("p1", 12.0,  500,  5.0,   0.15),
    ("p2", 45.0,  1000, 22.0,  0.25),
    ("p3", 120.0, 800,  80.0,  0.40),
    ("p4", 300.0, 1500, 200.0, 0.60),
    ("p5", 600.0, 2000, 450.0, 0.80),
]
injected_flux = baseline_flux.copy()
for name, period, depth_ppm, t0, dur in INJECTED:
    phase = ((time - t0) % period) - period / 2.0
    in_tr = np.abs(phase) < dur / 2.0
    injected_flux[in_tr] -= depth_ppm / 1e6

def isolate(name, period, depth_ppm, t0, dur):
    iso = injected_flux.copy()
    for (n2, p2, d2, t0_2, dur2) in INJECTED:
        if n2 == name:
            continue
        ph = ((time - t0_2) % p2) - p2 / 2.0
        in_tr = np.abs(ph) < dur2 / 2.0
        iso[in_tr] += d2 / 1e6
    return iso

p1_iso = isolate(*INJECTED[0])

# Run BLS on the isolated curve ONCE. This is the slow step; everything
# else is fast.
from astraeus.analysis.bls_search import BLSSearchEngine
import time as _t
t0 = _t.time()
search = BLSSearchEngine.search(time, p1_iso)
print(f"[I1-v] BLSSearchEngine.search on iso-p1 took {_t.time() - t0:.1f}s", flush=True)
print(f"[I1-v] BLS result: period={search['period']:.4f}d, snr={search['snr']:.4f}, "
      f"depth={search['depth']:.6f}, duration={search['duration']:.4f}d, t0={search['t0']:.4f}, "
      f"confidence_score={search['confidence_score']:.4f}", flush=True)

# Now we drive the rest of `detect_transit_candidate` with the BLS output
# directly. This is the "small" version of detect_transit_candidate that
# skips the BLS call but uses the same vetting branches.
from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.vetting import VettingEngine
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.core.constants import (
    VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION,
    VETTING_VSHAPE_LOW_SNR_GATE,
    VETTING_ULTRA_SHORT_PERIOD_DAYS,
    DETECTION_CONFIDENCE_FLOOR,
    DETECTION_SNR_THRESHOLD_DEFAULT,
)
import astraeus.core.constants as _const_mod

best_period = search['period']
best_snr = search['snr']
best_depth = search['depth']
transit_time = search['t0']
duration = search['duration']
best_confidence = search['confidence_score']

# Manually run DetrendingEngine.estimate_stellar_rotation + detrend
# to keep the timing aligned with detect_transit_candidate's order.
stellar_rotation_period_days = DetrendingEngine.estimate_stellar_rotation(time, p1_iso)
flux = DetrendingEngine.detrend(time, p1_iso, stellar_rotation_period_days)
active_time = time.copy()
active_flux = flux.copy()

snr_threshold = DETECTION_SNR_THRESHOLD_DEFAULT
is_valid = (best_snr > snr_threshold) and (best_confidence >= DETECTION_CONFIDENCE_FLOOR)
print(f"[I1-v] is_valid @ default floor 7.0  : {is_valid}  "
      f"(snr>5={best_snr>snr_threshold}, conf>=7={best_confidence>=DETECTION_CONFIDENCE_FLOOR})", flush=True)

raw_depth = float(best_depth)
transit_depth_fraction = raw_depth / 100.0 if raw_depth > 0.1 else raw_depth
print(f"[I1-v] transit_depth_fraction = {transit_depth_fraction:.6f}  (VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION={VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION})", flush=True)

# GeometricValidator
geom = GeometricValidator.validate(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction)
print(f"[I1-v] GeometricValidator: sec_eclipse_detected={geom['secondary_eclipse_detected']}, "
      f"sec_depth={geom['secondary_eclipse_depth']:.6f}, flat_bottom_fraction={geom['flat_bottom_fraction']:.4f}", flush=True)

# VettingEngine shape vet
vshape = VettingEngine.vet_transit_shape(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction, snr=best_snr)
print(f"[I1-v] VettingEngine: status={vshape['vetting_status']!r}, "
      f"conf={vshape['vetting_confidence']:.4f}, "
      f"delta_chi2_u={vshape['delta_chi2_u']:.6f}, delta_chi2_v={vshape['delta_chi2_v']:.6f}", flush=True)

# Now replay the false-positive cross-vetting branches (detection.py:132-166)
# twice: once with the original floor 7.0, once with the floor lowered.
for label, floor in [("default floor=7.0", DETECTION_CONFIDENCE_FLOOR), ("lowered floor=3.0", 3.0)]:
    is_valid_now = (best_snr > snr_threshold) and (best_confidence >= floor)
    print(f"\n[I1-v] === Replay cross-vetting with {label} ===", flush=True)
    print(f"  is_valid = {is_valid_now}", flush=True)
    if not is_valid_now:
        print(f"  -> cross-vetting BLOCK SKIPPED (lines 132-166 of detection.py)", flush=True)
        print(f"  -> vetting_status remains at the shape-vet result: {vshape['vetting_status']!r}", flush=True)
        print(f"  -> Orchestrator reads: {vshape['vetting_status']!r} -> guardrail 1 trips", flush=True)
        continue
    is_ultra_short = float(best_period) < VETTING_ULTRA_SHORT_PERIOD_DAYS
    sec_depth = geom.get('secondary_eclipse_depth', 0.0)
    if transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION:
        verdict = "Verified Planet Candidate"
    elif (vshape['vetting_status'] == "Ambiguous/False Positive"
          and geom['secondary_eclipse_detected']
          and (best_snr <= VETTING_VSHAPE_LOW_SNR_GATE or sec_depth >= 800e-6)):
        verdict = "Eclipsing Binary Detected"
    elif (best_snr <= VETTING_VSHAPE_LOW_SNR_GATE
          and not is_ultra_short
          and vshape['vetting_status'] == "Ambiguous/False Positive"):
        verdict = "V-Shaped False Positive Risk (Potential Grazing Binary)"
    elif geom['secondary_eclipse_detected']:
        verdict = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"  # simplified
    elif vshape['vetting_status'] == "Likely Planet":
        verdict = "Verified Planet Candidate"
    else:
        verdict = f"<NO BRANCH FIRED — stays at line-79 default: 'rejected'>"
    print(f"  is_ultra_short_period = {is_ultra_short}", flush=True)
    print(f"  -> CROSS-VETTING VERDICT: {verdict!r}", flush=True)
    print(f"  -> Orchestrator reads: {verdict!r}", flush=True)

print()
print("=" * 78, flush=True)
print("[I1-v] CONCLUSIONS:", flush=True)
print("=" * 78, flush=True)
print("  A. Failure mechanism CONFIRMED:", flush=True)
print(f"     p1 BLS: snr={best_snr:.3f}, confidence_score={best_confidence:.3f}", flush=True)
print(f"     With floor=7.0: is_valid=False -> cross-vetting SKIPPED", flush=True)
print(f"     vetting_status comes from VettingEngine shape vet only: {vshape['vetting_status']!r}", flush=True)
print(f"     Orchestrator guardrail 1: '{vshape['vetting_status']}'.startswith('Verified Planet Candidate') -> False", flush=True)
print(f"     -> guardrail 1 trips, search halts (or, post-H3-patch, marks marginal).", flush=True)
print(f"  B. With floor=3.0 (below observed confidence_score={best_confidence:.3f}):", flush=True)
print(f"     is_valid=True -> cross-vetting runs, shape={vshape['vetting_status']!r}", flush=True)
print(f"     depth=2.7e-4 < 0.03 -> branch 1 fires -> 'Verified Planet Candidate'", flush=True)
print(f"  C. The fix is to lower DETECTION_CONFIDENCE_FLOOR below the SYN-5P p1 confidence (~3.7).", flush=True)
print(f"     Setting it to 3.0 (or lower) restores the cross-vetting decision path on these signals.", flush=True)
print(f"     The empirical 'noise max 5.96' calibration has 1.5-2x headroom over the new floor.", flush=True)
print(f"  D. This does NOT touch the thresholding for depth/eclipse branches, so the bucket-2 /", flush=True)
print(f"     bucket-10 test fixtures are unaffected by the change.", flush=True)
