"""I5 — re-profile BLSSearchEngine.search at the actual Kepler-90
baseline that I0 measured (1239.81d, 45853 cadences). Round 1 measured
BLS at 365d/17520 = 136.4s (the H5 evidence). The I0 e2e orchestrator
run on the real Kepler-90 12-quarter stitch took 1796s wall for 4
iterations, of which most is BLS + classify + subtract — we want a
clean BLS-only number for the 1239.81d / 45853 case.
"""

import os
import sys
import time as _t
import glob

import numpy as np
import lightkurve as lk

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

_TEMP_CACHE = os.path.join(
    os.environ.get("TEMP", "/tmp"),
    "astraeus_h1_kepler90_measurement",
    "download_all",
)
fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
print(f"[I5] found {len(fits_files)} FITS files", flush=True)
assert len(fits_files) >= 12, f"expected >= 12 FITS files, got {len(fits_files)}"

lcs = []
for fp in fits_files[:12]:
    lc = lk.read(fp)
    if hasattr(lc, "PDCSAP_FLUX") and lc.PDCSAP_FLUX is not None:
        lcs.append(lc.PDCSAP_FLUX)
    elif hasattr(lc, "SAP_FLUX") and lc.SAP_FLUX is not None:
        lcs.append(lc.SAP_FLUX)
    else:
        lcs.append(lc)

stitched = lk.LightCurveCollection(lcs).stitch()
flat = stitched.remove_nans()
t = np.asarray(flat.time.value, dtype=np.float64)
f = np.asarray(flat.flux.value, dtype=np.float64)
print(f"[I5] stitched baseline: {t.max() - t.min():.2f} d  n_cadences={len(t)}", flush=True)

# Now run BLSSearchEngine.search.
from astraeus.analysis.bls_search import BLSSearchEngine
t0 = _t.time()
result = BLSSearchEngine.search(t, f)
wall = _t.time() - t0
print(f"\n[I5] BLSSearchEngine.search wall_s = {wall:.2f}", flush=True)
print(f"[I5]   best_period = {result['period']:.4f} d", flush=True)
print(f"[I5]   best_snr    = {result['snr']:.3f}", flush=True)
print(f"[I5]   best_depth  = {result['depth']:.6f}", flush=True)
print(f"[I5]   duration    = {result['duration']:.4f} d", flush=True)
print(f"[I5]   confidence  = {result['confidence_score']:.4f}", flush=True)
print(f"[I5]   seconds_per_sample = {wall / len(t):.4e}", flush=True)
print(f"\n[I5] COMPARISON WITH ROUND 1 (H5):", flush=True)
print(f"  365d  / 17520 samples : 136.4s  (7.79e-3 s/sample)  -- T_baseline>300 branch fires", flush=True)
print(f"  1460d / 70080 samples : 113.8s  (1.62e-3 s/sample)", flush=True)
print(f"  {t.max()-t.min():.0f}d / {len(t)} samples: {wall:.1f}s ({wall/len(t):.2e} s/sample)", flush=True)

# Multi-iteration projection: orchestrator typically runs 4-6 iterations
# for multi-planet searches. We do not propose a specific number of
# iterations because the cap=12 baseline now allows Kepler-90h (P=331d)
# to be reached, and a 6-iter search on a 1239.81d curve is plausible.
print(f"\n[I5] PROJECTION (round 1 H5: cost is linear in N):", flush=True)
for n_iters in (3, 4, 6):
    print(f"  {n_iters} iters * {wall:.0f}s/iter = {n_iters*wall:.0f}s = {n_iters*wall/60:.1f}min wall", flush=True)
