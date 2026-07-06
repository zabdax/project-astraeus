"""I0/I1 end-to-end check: run the actual `run_multi_planet_search` on the
5-planet synthetic (no monkey-patch recursion) and report the
iter-by-iter verdict. This is the script that the protocol asks for:
  "actual planets-recovered count after the change" (I0)
  "Run the SYN-5P scenario's p1 ... through the classifier in
   isolation and log exactly which criterion it fails" (I1)
"""

import json
import os
import sys

import numpy as np

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

print(f"[I0/I1] project_root={_PROJ_ROOT}", flush=True)

# Same SYN-5P setup
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

print(f"[I0/I1] injected planets: {[(n, p) for n, p, *_ in INJECTED]}", flush=True)

# Run the orchestrator directly. No monkey-patching.
from astraeus.core import orchestrator as _orch
from astraeus.analysis.bls_search import BLSSearchEngine

lc = {
    "time": time,
    "flux": injected_flux,
    "target_name": "SYN-5P",
    "data_source": "synthetic",
    "metadata": {},
}

import time as _t
t0 = _t.time()
print(f"[I0/I1] calling _orch.run_multi_planet_search(max_signals=5, snr_floor=7.1) ...", flush=True)
discovered = _orch.run_multi_planet_search(lc, max_signals=5, snr_floor=7.1)
wall = _t.time() - t0
print(f"[I0/I1] wall_s={wall:.1f}", flush=True)

print(f"\n[I0/I1] === DISCOVERED ({len(discovered)} of 5) ===", flush=True)
recovered = []
for idx, prop in enumerate(discovered):
    period = float(prop.get('period', 0.0))
    snr = float(prop.get('snr', 0.0))
    status = prop.get('vetting_status', '?')
    # Match against injected
    matched = None
    for (n, p, d, t0_p, dur) in INJECTED:
        if abs(period - p) / p <= 0.02:
            matched = f"{n}@{p}d"
            recovered.append(matched)
            break
    print(f"  #{idx+1}: period={period:.4f}d snr={snr:.3f} status={status!r} matched={matched}", flush=True)

print(f"\n[I0/I1] recovered planets: {recovered}", flush=True)
print(f"[I0/I1] recovered_count={len(recovered)}/5", flush=True)
