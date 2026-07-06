"""I0 end-to-end: real Kepler-90 download + orchestrator run with the
post-I1-patch classifier. Reports both:
  - baseline / starvation numbers (already captured in i0_kepler90_2026-07-06.log)
  - planets-recovered through the full orchestrator pipeline

The download uses the same temp cache as the h1_kepler90_measurement.py
script (TEMP/astraeus_h1_kepler90_measurement/download_all) so the FITS
files are cached and only the orchestrator call costs fresh CPU.
"""

import json
import os
import sys
import time as _t

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
print(f"[I0-e2e] reading FITS from: {_TEMP_CACHE}", flush=True)

# Read all 12 FITS files directly. This is what `lc = search[:12].download_all()`
# returned in the h1 measurement; we re-read locally to avoid a re-download.
import glob
fits_files = sorted(glob.glob(os.path.join(_TEMP_CACHE, "**", "*.fits"), recursive=True))
print(f"[I0-e2e] found {len(fits_files)} FITS files", flush=True)
if not fits_files:
    print("[I0-e2e] no FITS files found; re-run scratch/h1_kepler90_measurement.py first", flush=True)
    sys.exit(1)

lcs = []
for fp in fits_files:
    try:
        lc = lk.read(fp)
        if hasattr(lc, "PDCSAP_FLUX") and lc.PDCSAP_FLUX is not None:
            lcs.append(lc.PDCSAP_FLUX)
        elif hasattr(lc, "SAP_FLUX") and lc.SAP_FLUX is not None:
            lcs.append(lc.SAP_FLUX)
        else:
            lcs.append(lc)
    except Exception as exc:
        print(f"[I0-e2e] failed to read {fp}: {exc!r}", flush=True)

# Use the stitched curve from the h1 measurement log (post-remove_nans).
# We rebuild it to be safe.
try:
    lc_collection = lk.LightCurveCollection(lcs)
    stitched = lc_collection.stitch()
    flat = stitched.remove_nans()
except Exception as exc:
    print(f"[I0-e2e] stitch failed: {exc!r}", flush=True)
    sys.exit(2)

t_arr = np.asarray(flat.time.value, dtype=np.float64)
t_arr = t_arr[np.isfinite(t_arr)]
f_arr = np.asarray(flat.flux.value, dtype=np.float64)
f_arr = f_arr[np.isfinite(t_arr)]
print(f"[I0-e2e] stitched baseline: {t_arr.max() - t_arr.min():.2f} d, n_cadences={len(t_arr)}", flush=True)
print(f"[I0-e2e] time[0]={t_arr.min():.4f}, time[-1]={t_arr.max():.4f}", flush=True)

# Run the orchestrator.
from astraeus.core import orchestrator as _orch

lc = {
    "time": t_arr,
    "flux": f_arr,
    "target_name": "Kepler-90",
    "data_source": "MAST-stitch-12quarters",
    "metadata": {},
}

t0 = _t.time()
discovered = _orch.run_multi_planet_search(lc, max_signals=8, snr_floor=7.1)
wall = _t.time() - t0
print(f"\n[I0-e2e] wall_s={wall:.1f}", flush=True)
print(f"[I0-e2e] === DISCOVERED ({len(discovered)} candidates) ===", flush=True)

KNOWN_PERIODS = {
    "Kepler-90b": 7.0085, "Kepler-90c": 8.7194, "Kepler-90d": 59.7367,
    "Kepler-90e": 91.9391, "Kepler-90f": 124.9144, "Kepler-90g": 210.6069,
    "Kepler-90h": 331.6453, "Kepler-90i": 14.4491,
}
recovered = []
for idx, prop in enumerate(discovered):
    period = float(prop.get('period', 0.0))
    snr = float(prop.get('snr', 0.0))
    status = prop.get('vetting_status', '?')
    matched = None
    for planet, kp in KNOWN_PERIODS.items():
        if abs(period - kp) / kp <= 0.05:  # 5% to be generous on real-data
            matched = planet
            recovered.append(matched)
            break
    print(f"  #{idx+1}: period={period:.4f}d snr={snr:.3f} status={status!r} matched={matched}", flush=True)

print(f"\n[I0-e2e] recovered planets: {recovered}", flush=True)
print(f"[I0-e2e] recovered_count={len(recovered)}/8", flush=True)
