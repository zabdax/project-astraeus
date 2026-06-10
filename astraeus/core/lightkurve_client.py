import os
import sys
import shutil
import tempfile
import threading
import numpy as np
import lightkurve as lk

_LIGHTKURVE_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")
_ASTRAEUS_LIGHTKURVE_CACHE_DIR = os.environ.get(
    "ASTRAEUS_LIGHTKURVE_CACHE_DIR",
    os.path.join(tempfile.gettempdir(), "astraeus_lightkurve_cache"),
)
_MAX_DOWNLOAD_SEGMENTS = 3

class LightkurveClient:
    """Handles interactions with LightKurve and MAST."""

    @staticmethod
    def _wipe_lightkurve_cache() -> None:
        cache_dir = _LIGHTKURVE_CACHE_DIR
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
            except Exception as rm_err:
                print(f"[LightkurveClient] CACHE WIPER: Failed to remove '{cache_dir}': {rm_err}", file=sys.stderr)

    @staticmethod
    def _wipe_download_dir(download_dir: str) -> None:
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)
        os.makedirs(download_dir, exist_ok=True)

    @staticmethod
    def _download_cache_dir() -> str:
        os.makedirs(_ASTRAEUS_LIGHTKURVE_CACHE_DIR, exist_ok=True)
        return _ASTRAEUS_LIGHTKURVE_CACHE_DIR

    @staticmethod
    def _call_with_timeout(fn, args=(), kwargs=None, timeout: float = 15.0, label: str = "operation"):
        if kwargs is None: kwargs = {}
        result_box = []
        error_box = []

        def _worker():
            try:
                result_box.append(fn(*args, **kwargs))
            except Exception as exc:
                error_box.append(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            print(f"[LightkurveClient] TIMEOUT: {label} exceeded {timeout:.0f}s — skipping.", file=sys.stderr)
            return None

        if error_box:
            raise error_box[0]

        return result_box[0] if result_box else None

    @staticmethod
    def _download_with_timeout(row, timeout: float = 12.0, download_dir: str | None = None):
        kwargs = {"download_dir": download_dir} if download_dir else {}
        return LightkurveClient._call_with_timeout(
            row.download,
            kwargs=kwargs,
            timeout=timeout,
            label="row.download()",
        )

    @staticmethod
    def _is_fits_corruption(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in ("truncated", "corrupt", "not a fits", "end-of-file", "header missing", "block does not begin"))

    @staticmethod
    def _prioritize_search_results(search, mission_type: str):
        if search is None or len(search) == 0:
            return search

        table = search.table
        try:
            if mission_type == "Kepler" and "exptime" in table.colnames:
                exposure = np.asarray(table["exptime"], dtype=float)
                long_cadence = np.isfinite(exposure) & (exposure >= 1000.0)
                if np.any(long_cadence):
                    search = search[long_cadence]
                    table = search.table

            if "size" in table.colnames:
                sizes = np.asarray(table["size"], dtype=float)
                sizes = np.where(np.isfinite(sizes), sizes, np.inf)
                return search[np.argsort(sizes)]
        except Exception:
            return search

        return search

    @staticmethod
    def download_pipeline(t_name, mission_type: str) -> tuple[dict | None, str | None]:
        mast_error = None
        download_dir = LightkurveClient._download_cache_dir()
        try:
            if mission_type == "TESS":
                search = LightkurveClient._call_with_timeout(
                    lk.search_lightcurve, args=(t_name,),
                    kwargs={"mission": "TESS", "author": "SPOC"}, timeout=60.0,
                    label="search_lightcurve(TESS/SPOC)"
                )
            elif mission_type == "Kepler":
                search = LightkurveClient._call_with_timeout(
                    lk.search_lightcurve, args=(t_name,),
                    kwargs={"mission": "Kepler", "author": "Kepler"}, timeout=60.0,
                    label="search_lightcurve(Kepler)"
                )
            else:
                return None, "Invalid mission_type"

            if search is None or len(search) == 0:
                return None, None

            search = LightkurveClient._prioritize_search_results(search, mission_type)
            
            lc_list = []
            last_download_error = None
            for row in search[:_MAX_DOWNLOAD_SEGMENTS]:
                for attempt in range(3):
                    try:
                        lc = LightkurveClient._download_with_timeout(
                            row,
                            timeout=180.0,
                            download_dir=download_dir,
                        )
                        if lc is not None:
                            lc_list.append(lc)
                            break
                        else:
                            last_download_error = "row.download() timed out or returned no light curve"
                        break
                    except Exception as e:
                        last_download_error = str(e)
                        if LightkurveClient._is_fits_corruption(e):
                            LightkurveClient._wipe_download_dir(download_dir)
                if lc_list:
                    break
            
            if not lc_list:
                return None, last_download_error
            
            lc_collection = lk.LightCurveCollection(lc_list)
            stitched = lc_collection.stitch()
            try:
                flat = stitched.flatten()
            except Exception:
                flat = stitched.normalize()
            flat = flat.remove_nans()
            
            t = np.asarray(flat.time.value, dtype=np.float64)
            f = np.asarray(flat.flux.value, dtype=np.float64)
            e = np.asarray(flat.flux_err.value, dtype=np.float64)
            
            valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
            t, f, e = t[valid], f[valid], e[valid]
            
            if len(t) == 0:
                return None, None
                
            sort_idx = np.argsort(t)
            return {"time": t[sort_idx], "flux": f[sort_idx], "flux_err": e[sort_idx]}, None
            
        except Exception as exc:
            mast_error = str(exc)
            return None, mast_error

    @staticmethod
    def download_combined_fusion(safe_canonical) -> tuple[dict | None, str | None]:
        # Skipping combined fusion implementation for brevity in the new SRP model
        # unless absolutely required. We will call the underlying TESS + Kepler logic.
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        import requests
        import time

        query = f"SELECT ra, dec FROM pscomppars WHERE pl_name = '{safe_canonical}'"
        url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
        params = {"query": query, "format": "json"}

        target_coords = safe_canonical
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                if data and len(data) > 0:
                    ra_val = float(data[0]['ra'])
                    dec_val = float(data[0]['dec'])
                    target_coords = SkyCoord(ra=ra_val*u.deg, dec=dec_val*u.deg, frame='icrs')
                break
            except Exception:
                time.sleep(2.0)

        # Simply download both separately and return a unified format
        tess_res, _ = LightkurveClient.download_pipeline(target_coords, "TESS")
        kep_res, _ = LightkurveClient.download_pipeline(target_coords, "Kepler")

        if not tess_res and not kep_res:
            return None, "Both Kepler and TESS searches failed."

        # Simplistic concat (time alignment may be required in advanced fusion)
        _UNIFIED_EPOCH = 2454833.0
        
        unified_t = []
        unified_f = []
        unified_e = []

        if kep_res:
            unified_t.append(kep_res['time'] + (2454833.0 - _UNIFIED_EPOCH))
            unified_f.append(kep_res['flux'])
            unified_e.append(kep_res['flux_err'])
        
        if tess_res:
            unified_t.append(tess_res['time'] + (2457000.0 - _UNIFIED_EPOCH))
            unified_f.append(tess_res['flux'])
            unified_e.append(tess_res['flux_err'])

        t_out = np.concatenate(unified_t)
        f_out = np.concatenate(unified_f)
        e_out = np.concatenate(unified_e)

        idx = np.argsort(t_out)
        return {
            "time": t_out[idx],
            "flux": f_out[idx],
            "flux_err": e_out[idx],
            "baseline": "unified",
            "kepler_segments": 1 if kep_res else 0,
            "tess_segments": 1 if tess_res else 0
        }, None
