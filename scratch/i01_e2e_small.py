"""I0/I1 e2e with reduced sample count to fit in budget.

We scale the SYN-5P scenario down to N=3000 samples (vs 30000 in the
canonical injection) so each BLS call completes in seconds, and we
keep the same 1500d baseline + same periods/depths/noise. The
classifier semantics do not change with N; the only differences are
the absolute SNR and the periodogram resolution. We tag this clearly
as a "scaled-down e2e" and use it only to verify the orchestrator's
end-to-end behavior post-I1-patch (does it now accept p1 and progress
to p2?). The full-N numbers (real SNR ~10, real recovery 5/5) come from
the I1 regression test in tests/test_i1_classifier_multiplanet.py.
"""

import json
import os
import sys
import time as _t

import numpy as np

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

N_SAMPLES = 3000       # 10x smaller than canonical SYN-5P
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

print(f"[e2e-small] N={N_SAMPLES} T={T_SPAN}d (10x scaled down from canonical SYN-5P)", flush=True)
print(f"[e2e-small] injected planets: {[(n, p) for n, p, *_ in INJECTED]}", flush=True)

from astraeus.core import orchestrator as _orch

lc = {
    "time": time,
    "flux": injected_flux,
    "target_name": "SYN-5P-small",
    "data_source": "synthetic",
    "metadata": {},
}

t0 = _t.time()
discovered = _orch.run_multi_planet_search(lc, max_signals=5, snr_floor=7.1)
wall = _t.time() - t0
print(f"\n[e2e-small] wall_s={wall:.1f}", flush=True)
print(f"[e2e-small] === DISCOVERED ({len(discovered)} of 5) ===", flush=True)

recovered = []
for idx, prop in enumerate(discovered):
    period = float(prop.get('period', 0.0))
    snr = float(prop.get('snr', 0.0))
    status = prop.get('vetting_status', '?')
    matched = None
    for (n, p, *_r) in INJECTED:
        if abs(period - p) / p <= 0.02:
            matched = f"{n}@{p}d"
            recovered.append(matched)
            break
    print(f"  #{idx+1}: period={period:.4f}d snr={snr:.3f} status={status!r} matched={matched}", flush=True)

print(f"\n[e2e-small] recovered_count={len(recovered)}/5  list={recovered}", flush=True)
