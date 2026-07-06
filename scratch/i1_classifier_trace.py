"""I1 — Trace why the vetting_status classifier rejects exact matches.

Per the round-2 protocol: take the SYN-5P scenario's p1 (12.0d, SNR 10.84,
matched to 0.002%) and p2 (45.0d, SNR 8.48) and run them through
`astraeus.analysis.detection.detect_transit_candidate` in isolation.

For each, log:
  - the full result dict (snr, vetting_status, confidence_score, depth,
    duration, secondary_eclipse_detected, flat_bottom_fraction,
    vetting_metrics, v_shape_metric),
  - which decision branch in detection.py:132-166 actually fired,
  - the raw internal state of the classifier at the moment of decision.

The script does NOT modify any astraeus/ source. It only runs
`detect_transit_candidate` and reports what it returns.
"""

import json
import os
import sys

import numpy as np

# Make sure we can import astraeus from the project root.
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

print(f"[I1] project_root={_PROJ_ROOT}")
print(f"[I1] python={sys.version.split()[0]} numpy={np.__version__}")

# Probe environment
try:
    import batman  # noqa: F401
    _BATMAN_AVAILABLE = True
except Exception:
    _BATMAN_AVAILABLE = False
print(f"[I1] batman_available={_BATMAN_AVAILABLE}")

# Reuse the SYN-5P setup from h23_5planet_injection.py verbatim.
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

# Now mask out everything EXCEPT one planet at a time, so the classifier
# sees a curve with a single strong signal at the planet's known period.
def isolate_planet(name, period, depth_ppm, t0, dur):
    """Return (time, flux_isolated) with ONLY `name` visible.

    Strategy: keep the planet's transit dip; remove the other 4 planets
    by re-adding their dip back to the flux.
    """
    isolated = injected_flux.copy()
    for (n2, p2, d2, t0_2, dur2) in INJECTED:
        if n2 == name:
            continue
        # Re-add the dip (i.e., remove the planet) to flatten it.
        phase2 = ((time - t0_2) % p2) - p2 / 2.0
        in_tr2 = np.abs(phase2) < dur2 / 2.0
        isolated[in_tr2] += d2 / 1e6
    return isolated


from astraeus.analysis import detection as _det
from astraeus.core.constants import (
    VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION,
    VETTING_VSHAPE_LOW_SNR_GATE,
    VETTING_ULTRA_SHORT_PERIOD_DAYS,
    DETECTION_CONFIDENCE_FLOOR,
    DETECTION_SNR_THRESHOLD_DEFAULT,
)


def _report(label, result):
    print("=" * 78, flush=True)
    print(f"[I1] {label}", flush=True)
    print("=" * 78, flush=True)
    if not result:
        print(f"[I1] {label}: detect_transit_candidate returned empty dict", flush=True)
        return
    keys_of_interest = [
        'candidate_found', 'is_candidate', 'vetting_status',
        'snr', 'confidence_score', 'period', 'period_days', 'orbital_period',
        'depth', 'transit_depth', 'duration', 't0',
        'v_shape_metric', 'flat_bottom_fraction',
        'secondary_eclipse_detected', 'secondary_eclipse_depth', 'secondary_eclipse_snr',
        'secondary_eclipse_threshold_ppm', 'secondary_eclipse_threshold_mode',
        'stellar_rotation_period_days',
        'vetting_confidence', 'u_shape_chi2', 'v_shape_chi2',
        'delta_chi2_u', 'delta_chi2_v',
        'equilibrium_temp_k', 'planet_radius_earth',
    ]
    for k in keys_of_interest:
        if k in result:
            v = result[k]
            try:
                if isinstance(v, float):
                    print(f"  {k:36s} = {v:.6f}", flush=True)
                else:
                    print(f"  {k:36s} = {v!r}", flush=True)
            except Exception:
                print(f"  {k:36s} = {v!r}", flush=True)
    # Decision branch analysis
    snr = float(result.get('snr', 0.0))
    confidence = float(result.get('confidence_score', 0.0))
    is_valid = (snr > DETECTION_SNR_THRESHOLD_DEFAULT) and (confidence >= DETECTION_CONFIDENCE_FLOOR)
    raw_depth = float(result.get('transit_depth', 0.0) or 0.0)
    sec_eclipse_detected = bool(result.get('secondary_eclipse_detected', False))
    sec_depth = float(result.get('secondary_eclipse_depth', 0.0) or 0.0)
    sec_threshold_ppm = float(result.get('secondary_eclipse_threshold_ppm', 800.0))
    sec_threshold_fraction = sec_threshold_ppm / 1.0e6
    vshape_status = None
    if 'vetting_status' in result:
        # We don't have the raw vetting_metrics in the result — fetch them
        # by reading the most-recent call (detection.py populates them on
        # the result dict). They are:
        #   vetting_status (overridden), vetting_confidence, u_shape_chi2,
        #   v_shape_chi2, delta_chi2_u, delta_chi2_v
        vshape_status = None  # only the OVERRIDDEN vetting_status is in the result
    print(f"  ---  decision-branch analysis  ---", flush=True)
    _snr_gt = snr > DETECTION_SNR_THRESHOLD_DEFAULT
    _conf_ge = confidence >= DETECTION_CONFIDENCE_FLOOR
    print(f"  is_valid emission gate        : {is_valid}  (snr>{DETECTION_SNR_THRESHOLD_DEFAULT}={_snr_gt}, conf>={DETECTION_CONFIDENCE_FLOOR}={_conf_ge})", flush=True)
    print(f"  transit_depth_fraction        : {raw_depth:.6f}  (max for planet: {VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION})", flush=True)
    print(f"  depth<max?                    : {raw_depth < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION}", flush=True)
    print(f"  secondary_eclipse_detected    : {sec_eclipse_detected}  (depth={sec_depth:.6f}, threshold={sec_threshold_fraction:.6f})", flush=True)
    print(f"  snr<=VSHAPE_LOW_SNR_GATE      : {snr <= VETTING_VSHAPE_LOW_SNR_GATE}  (gate={VETTING_VSHAPE_LOW_SNR_GATE})", flush=True)
    print(f"  ultra_short_period            : {float(result.get('period', 0.0)) < VETTING_ULTRA_SHORT_PERIOD_DAYS}", flush=True)
    # Determine the actual branch the classifier fell through.
    # Branches in priority order from detection.py:132-166:
    #   1. depth < max -> "Verified Planet Candidate"
    #   2. vetting was "Ambiguous/False Positive" AND sec_eclipse AND (snr<=gate or sec_depth>=thresh) -> "Eclipsing Binary Detected"
    #   3. snr<=gate AND NOT ultra_short AND vetting=="Ambiguous/False Positive" -> "V-Shaped False Positive Risk"
    #   4. sec_eclipse AND sec_depth<thresh -> "Verified Planet Candidate (Atmospheric Occultation Detected)"
    #   4'. sec_eclipse AND sec_depth>=thresh -> "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
    #   5. vetting_status=='Likely Planet' -> "Verified Planet Candidate"
    # (no branch -> result remains 'candidate' from the line-79 initialization)
    final_status = result.get('vetting_status', '?')
    print(f"  FINAL vetting_status          : {final_status!r}", flush=True)


print("[I1] ---- per-planet isolated runs ----", flush=True)
for (name, period, depth_ppm, t0, dur) in INJECTED:
    isolated = isolate_planet(name, period, depth_ppm, t0, dur)
    lc = {
        "time": time,
        "flux": isolated,
        "target_name": f"SYN-5P-iso-{name}",
        "data_source": "synthetic",
        "metadata": {},
    }
    result = _det.detect_transit_candidate(
        time=time, flux=isolated,
        target_name=f"SYN-5P-iso-{name}",
        data_source="synthetic",
        metadata={},
        snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT,
    )
    _report(f"SYN-5P iso {name}  (period={period}d, depth_ppm={depth_ppm}, t0={t0}, dur={dur})", result)

# And one full-SYN-5P run to confirm what the orchestrator sees at the end
# of each iteration. (Just diagnostic; this matches what the orchestrator's
# detect_transit_candidate call returns in its loop.)
print("[I1] ---- full SYN-5P (5 planets) run ----", flush=True)
try:
    result = _det.detect_transit_candidate(
        time=time, flux=injected_flux,
        target_name="SYN-5P-full",
        data_source="synthetic",
        metadata={},
        snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT,
    )
    _report("SYN-5P full  (all 5 planets visible)", result)
except Exception as exc:
    print(f"[I1] full-SYN-5P run raised: {exc!r}", flush=True)
