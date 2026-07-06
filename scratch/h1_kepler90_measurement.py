"""H1 — Baseline starvation measurement for Kepler-90.

This is a *measurement-only* script. It reproduces the search + prioritize
+ download path used by `astraeus.core.lightkurve_client.LightkurveClient`
and reports the actual time span of the resulting `lc.time` after stitching.

Hard rules:
  - No astraeus/ source files are modified.
  - All exceptions are caught and logged, not raised.
  - At most 3 download attempts per file.
"""

import os
import sys
import tempfile
import traceback
import time as time_mod

import numpy as np
import lightkurve as lk

# Use the same cache dir LightkurveClient uses, but in a fresh temp subdir so
# we do not perturb any prior cache state.
_TEMP_CACHE = os.path.join(
    tempfile.gettempdir(),
    "astraeus_h1_kepler90_measurement",
)
os.makedirs(_TEMP_CACHE, exist_ok=True)
# Honour the env var if it's already set, but the download_dir below overrides
# where the FITS files end up locally.
print(f"[H1] Using temp download_dir: {_TEMP_CACHE}", flush=True)
print(f"[H1] ASTRAEUS_LIGHTKURVE_CACHE_DIR = {os.environ.get('ASTRAEUS_LIGHTKURVE_CACHE_DIR')}", flush=True)

# Import the live prioritizer (no source modification — just an import).
from astraeus.core.lightkurve_client import LightkurveClient  # noqa: E402

T_NAME = "Kepler-90"
MISSION = "Kepler"
N_PRIORITIZE = 12  # cap=12 (H1 patch 2026-07-06, lightkurve_client.py:36)

KNOWN_PERIODS = {
    "Kepler-90b": 7.0085,
    "Kepler-90c": 8.7194,
    "Kepler-90d": 59.7367,
    "Kepler-90e": 91.9391,
    "Kepler-90f": 124.9144,
    "Kepler-90g": 210.6069,
    "Kepler-90h": 331.6453,
    "Kepler-90i": 14.4491,
}


def _report_lc(label: str, lc) -> None:
    """Print time-min, time-max, span-days, and # of cadences for one LC."""
    try:
        t = np.asarray(lc.time.value, dtype=np.float64)
        t = t[np.isfinite(t)]
        if len(t) == 0:
            print(f"[H1] {label}: <empty time array>", flush=True)
            return
        tmin, tmax = float(t.min()), float(t.max())
        print(
            f"[H1] {label}: time.min={tmin:.4f}  time.max={tmax:.4f}  "
            f"span={tmax - tmin:.4f} d  n_cadences={len(t)}",
            flush=True,
        )
    except Exception as exc:
        print(f"[H1] {label}: <error measuring> {exc}", flush=True)


def main():
    print("=" * 78, flush=True)
    print("[H1] Phase 1, H1 — Kepler-90 baseline starvation measurement", flush=True)
    print("=" * 78, flush=True)

    # ── 1. Search ───────────────────────────────────────────────────────
    print(f"[H1] lk.search_lightcurve({T_NAME!r}, mission={MISSION!r}) ...", flush=True)
    try:
        search = lk.search_lightcurve(T_NAME, mission=MISSION)
    except Exception as exc:
        print(f"[H1] SEARCH FAILED: {exc!r}", flush=True)
        traceback.print_exc()
        return
    print(f"[H1] rows_total = {len(search)}", flush=True)
    try:
        print(f"[H1] columns = {search.table.colnames}", flush=True)
    except Exception:
        pass

    # ── 2. Prioritize (long-cadence, size-ascending) ─────────────────────
    print("[H1] Calling LightkurveClient._prioritize_search_results(...) ...", flush=True)
    try:
        prioritized = LightkurveClient._prioritize_search_results(search, MISSION)
        rows_prioritized = len(prioritized)
    except Exception as exc:
        print(f"[H1] PRIORITIZE FAILED: {exc!r}", flush=True)
        traceback.print_exc()
        prioritized = search
        rows_prioritized = len(search)
    print(f"[H1] rows_prioritized = {rows_prioritized}", flush=True)

    # ── 3. Top-3 size-sorted rows ────────────────────────────────────────
    try:
        top3 = prioritized[:N_PRIORITIZE]
        table = top3.table
        print(f"[H1] Top-{N_PRIORITIZE} size-sorted rows:", flush=True)
        for i in range(len(top3)):
            try:
                fn = str(table["productFilename"][i])
            except Exception:
                fn = "?"
            try:
                size = float(table["size"][i])
            except Exception:
                size = float("nan")
            try:
                t_min_val = float(table["t_min"][i])
                t_max_val = float(table["t_max"][i])
            except Exception:
                t_min_val = float("nan")
                t_max_val = float("nan")
            print(
                f"[H1]   #{i+1}: productFilename={fn}  size={size:.1f} "
                f"t_min={t_min_val:.4f}  t_max={t_max_val:.4f}",
                flush=True,
            )
    except Exception as exc:
        print(f"[H1] Top-3 inspection failed: {exc!r}", flush=True)
        traceback.print_exc()
        return

    # ── 4. Download those 3 FITS files via lightkurve ────────────────────
    print(f"[H1] Downloading top-{N_PRIORITIZE} FITS files via search[:{N_PRIORITIZE}].download_all() ...", flush=True)
    lcs = []
    rows_to_stitcher = 0
    last_dl_err = None
    try:
        # download_all into a clean per-run temp dir
        per_run_dl = os.path.join(_TEMP_CACHE, "download_all")
        os.makedirs(per_run_dl, exist_ok=True)
        downloaded = top3.download_all(download_dir=per_run_dl)
        # `downloaded` may be a LightCurveFileCollection or a list of LCs
        try:
            n_downloaded = len(downloaded)
        except Exception:
            n_downloaded = -1
        print(f"[H1] download_all returned {n_downloaded} item(s)", flush=True)
        rows_to_stitcher = n_downloaded if n_downloaded >= 0 else 0

        # Normalize to a list of LightCurves
        for i, item in enumerate(downloaded):
            try:
                # LightCurveFileCollection item is a KeplerLightCurveFile; .PDCSAP_FLUX is the flux
                lc = item
                # Try to extract SAP/PDC flux
                if hasattr(lc, "PDCSAP_FLUX") and lc.PDCSAP_FLUX is not None:
                    lc_use = lc.PDCSAP_FLUX
                elif hasattr(lc, "SAP_FLUX") and lc.SAP_FLUX is not None:
                    lc_use = lc.SAP_FLUX
                else:
                    lc_use = lc
                _report_lc(f"lc[{i}] (per-quarter)", lc_use)
                lcs.append(lc_use)
            except Exception as item_exc:
                print(f"[H1] item[{i}] post-process failed: {item_exc!r}", flush=True)
                traceback.print_exc()
    except Exception as exc:
        last_dl_err = repr(exc)
        print(f"[H1] DOWNLOAD FAILED: {last_dl_err}", flush=True)
        traceback.print_exc()

    if not lcs:
        print("[H1] No light curves were successfully downloaded.", flush=True)
        return

    # ── 5. Stitch ───────────────────────────────────────────────────────
    print("[H1] Building LightCurveCollection and stitching ...", flush=True)
    try:
        lc_collection = lk.LightCurveCollection(lcs)
        stitched = lc_collection.stitch()
        flat = stitched.remove_nans()
        _report_lc("stitched (post remove_nans)", flat)
        t_arr = np.asarray(flat.time.value, dtype=np.float64)
        t_arr = t_arr[np.isfinite(t_arr)]
        if len(t_arr) == 0:
            print("[H1] stitched time array is empty after remove_nans()", flush=True)
            return
        stitched_baseline_days = float(t_arr.max() - t_arr.min())
        t_min = float(t_arr.min())
        t_max = float(t_arr.max())
        n_cadences = int(len(t_arr))
    except Exception as exc:
        print(f"[H1] STITCH FAILED: {exc!r}", flush=True)
        traceback.print_exc()
        return

    # ── 6. Planet-period starvation check ────────────────────────────────
    print("=" * 78, flush=True)
    print(f"[H1] STITCHED BASELINE: {stitched_baseline_days:.4f} d  "
          f"(t_min={t_min:.4f}, t_max={t_max:.4f}, n_cadences={n_cadences})", flush=True)
    print("=" * 78, flush=True)
    print("[H1] Planet-starvation check (ratio = baseline / (2.5 * period)):", flush=True)
    below_count = 0
    for planet, period in KNOWN_PERIODS.items():
        ratio = stitched_baseline_days / (2.5 * period)
        flag = " <-- BELOW 2.5x MIN" if ratio < 1.0 else ""
        if ratio < 1.0:
            below_count += 1
        print(
            f"[H1]   {planet:14s} period={period:9.4f} d  "
            f"2.5*period={2.5*period:9.4f} d  "
            f"ratio={ratio:7.4f}{flag}",
            flush=True,
        )

    # ── 7. Final summary lines ──────────────────────────────────────────
    print("=" * 78, flush=True)
    print(
        f"[H1] SUMMARY: rows_total={len(search)} / "
        f"rows_prioritized={rows_prioritized} / "
        f"rows_to_stitcher={rows_to_stitcher} / "
        f"stitched_baseline_days={stitched_baseline_days:.4f} / "
        f"planets_below_2.5x={below_count}/{len(KNOWN_PERIODS)}",
        flush=True,
    )
    print(
        f"[H1] Protocol example claim was 91.2 d; measured baseline = "
        f"{stitched_baseline_days:.4f} d  "
        f"(delta = {stitched_baseline_days - 91.2:+.4f} d)",
        flush=True,
    )
    print("=" * 78, flush=True)


if __name__ == "__main__":
    t0 = time_mod.time()
    try:
        main()
    except Exception as exc:
        print(f"[H1] TOP-LEVEL EXCEPTION: {exc!r}", flush=True)
        traceback.print_exc()
    print(f"[H1] Wall time: {time_mod.time() - t0:.1f} s", flush=True)
