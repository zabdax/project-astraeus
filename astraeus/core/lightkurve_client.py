import os
import sys
import shutil
import tempfile
import threading
import time
import random
import numpy as np
import requests
import lightkurve as lk

_LIGHTKURVE_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")
_ASTRAEUS_LIGHTKURVE_CACHE_DIR = os.environ.get(
    "ASTRAEUS_LIGHTKURVE_CACHE_DIR",
    os.path.join(tempfile.gettempdir(), "astraeus_lightkurve_cache"),
)
_MAX_DOWNLOAD_SEGMENTS = 3

# TESS FFI cutouts can be 10GB+; the default 180s read timeout aborts mid-stream.
# The streaming helper stages files directly into lightkurve's mastDownload cache
# layout so row.download() finds them on the local-cache branch (no HTTP).
_MAST_DOWNLOAD_URL = "https://mast.stsci.edu/api/v0/Download/file"
_TESS_READ_TIMEOUT = 600.0       # ≥600s per FIX 2.3
_KEPLER_READ_TIMEOUT = 180.0     # Kepler LC files are small; keep legacy budget
_CONNECT_TIMEOUT = 10.0
_STREAM_CHUNK_BYTES = 1 << 20    # 1 MiB chunks keep peak memory flat
_STREAM_MAX_ATTEMPTS = 3
_STREAM_BACKOFF_BASE = 2.0       # 2s, 4s, 8s with full jitter

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
    def _row_cache_path(row, download_dir: str) -> str:
        """Reproduces lightkurve's hard-coded mastDownload cache layout.

        lightkurve's `_download_one` checks this exact path on its local-cache
        branch before issuing any HTTP request, so a file staged here makes the
        subsequent `row.download()` a zero-network operation.
        """
        table = row.table[:1]
        return os.path.join(
            download_dir.rstrip("/"),
            "mastDownload",
            table["obs_collection"][0],
            table["obs_id"][0],
            table["productFilename"][0],
        )

    @staticmethod
    def _classify_stream_failure(exc: Exception) -> str:
        """Maps an exception to a coarse, loggable failure reason tag."""
        msg = str(exc).lower()
        # Message-based checks first: a truncated read is more actionable than
        # the generic connection-error bucket it arrived in.
        if "404" in msg or "not found" in msg:
            return "Target not observed"
        if "truncated" in msg or "incomplete read" in msg:
            return "Stream truncated"
        if "metadata mismatch" in msg or "metadata" in msg:
            return "Metadata mismatch"
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return "Network Timeout"
        return f"Download error: {msg[:120]}"

    @staticmethod
    def _stream_mast_download(row, download_dir: str, read_timeout: float = _TESS_READ_TIMEOUT) -> tuple[str | None, str | None]:
        """Stream a MAST data product straight to disk with exponential backoff.

        Streams the file in fixed-size chunks so a 10GB+ TESS FFI cutout never
        has to fit in memory. On success the file is atomic-renamed into the
        lightkurve `mastDownload/<obs_collection>/<obs_id>/<productFilename>`
        cache slot so the downstream `row.download()` finds it locally and skips
        its own HTTP fetch entirely.

        Returns:
            (staged_path, None) on success, (None, reason_tag) on failure.
        """
        table = row.table[:1]
        data_uri = table["dataURI"][0]
        if not data_uri or data_uri.startswith("mast:TESS"):
            # TESSCut products are synthesized on the fly by the TESSCut service,
            # not served as static files — let lightkurve's own cutout path handle them.
            return None, "TESSCut product (deferred to lightkurve cutout path)"

        final_path = LightkurveClient._row_cache_path(row, download_dir)
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            # Already staged by a prior run / attempt — treat as a cache hit.
            return final_path, None

        os.makedirs(os.path.dirname(final_path), exist_ok=True)

        url = f"{_MAST_DOWNLOAD_URL}?uri={data_uri}"
        last_reason = None

        for attempt in range(_STREAM_MAX_ATTEMPTS):
            tmp_path = f"{final_path}.part.{attempt}.{os.getpid()}"
            try:
                # stream=True keeps the response body out of memory until iterated.
                with requests.get(
                    url,
                    stream=True,
                    timeout=(_CONNECT_TIMEOUT, read_timeout),
                ) as resp:
                    if resp.status_code == 404:
                        # Permanent — no point retrying.
                        last_reason = "Target not observed"
                        print(f"[LightkurveClient] STREAM: 404 for {data_uri} — Target not observed.", file=sys.stderr)
                        return None, last_reason
                    if resp.status_code >= 500:
                        last_reason = f"HTTP {resp.status_code} (server error, retryable)"
                        print(f"[LightkurveClient] STREAM: {last_reason} for {data_uri} (attempt {attempt + 1}/{_STREAM_MAX_ATTEMPTS}).", file=sys.stderr)
                        raise requests.HTTPError(last_reason, response=resp)
                    if resp.status_code >= 400:
                        last_reason = f"HTTP {resp.status_code} (client error)"
                        print(f"[LightkurveClient] STREAM: {last_reason} for {data_uri}.", file=sys.stderr)
                        return None, last_reason

                    expected = resp.headers.get("Content-Length")
                    bytes_written = 0
                    truncated = False
                    with open(tmp_path, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=_STREAM_CHUNK_BYTES):
                            if chunk:
                                fh.write(chunk)
                                bytes_written += len(chunk)
                        # Flush + fsync on the WRITE handle so a crash leaves a
                        # complete file on disk (re-opening read-only would be EBADF).
                        fh.flush()
                        try:
                            os.fsync(fh.fileno())
                        except OSError:
                            pass

                    if expected is not None:
                        try:
                            expected_n = int(expected)
                            if bytes_written != expected_n:
                                truncated = True
                                last_reason = f"Stream truncated ({bytes_written}/{expected_n} bytes)"
                        except ValueError:
                            pass

                    if truncated:
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                        print(f"[LightkurveClient] STREAM: {last_reason} for {data_uri} (attempt {attempt + 1}/{_STREAM_MAX_ATTEMPTS}).", file=sys.stderr)
                        raise requests.ConnectionError(last_reason)

                    os.replace(tmp_path, final_path)
                    print(
                        f"[LightkurveClient] STREAM: staged {data_uri} -> {final_path} "
                        f"({bytes_written >> 20} MiB, attempt {attempt + 1}/{_STREAM_MAX_ATTEMPTS}).",
                        file=sys.stderr,
                    )
                    return final_path, None

            except Exception as exc:
                if last_reason is None:
                    last_reason = LightkurveClient._classify_stream_failure(exc)
                # Clean up any partial file from this attempt.
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
                if attempt < _STREAM_MAX_ATTEMPTS - 1:
                    # Exponential backoff with full jitter (FIX 2.2).
                    delay = _STREAM_BACKOFF_BASE * (2 ** attempt) * random.random()
                    print(
                        f"[LightkurveClient] STREAM: {last_reason} for {data_uri} "
                        f"(attempt {attempt + 1}/{_STREAM_MAX_ATTEMPTS}); backing off {delay:.1f}s.",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                else:
                    print(
                        f"[LightkurveClient] STREAM: giving up on {data_uri} after "
                        f"{_STREAM_MAX_ATTEMPTS} attempts ({last_reason}).",
                        file=sys.stderr,
                    )

        return None, last_reason or "Stream download exhausted retries"

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
                    kwargs={"mission": "TESS", "author": "SPOC"}, timeout=90.0,
                    label="search_lightcurve(TESS/SPOC)"
                )
            elif mission_type == "Kepler":
                search = LightkurveClient._call_with_timeout(
                    lk.search_lightcurve, args=(t_name,),
                    kwargs={"mission": "Kepler", "author": "Kepler"}, timeout=90.0,
                    label="search_lightcurve(Kepler)"
                )
            else:
                return None, "Invalid mission_type"

            if search is None or len(search) == 0:
                return None, None

            search = LightkurveClient._prioritize_search_results(search, mission_type)

            # TESS products can be multi-GB; allow the larger read budget there.
            row_read_timeout = _TESS_READ_TIMEOUT if mission_type == "TESS" else _KEPLER_READ_TIMEOUT

            lc_list = []
            last_download_error = None
            for row in search[:_MAX_DOWNLOAD_SEGMENTS]:
                # FIX 2: stream the product to the mastDownload cache slot before
                # invoking row.download(). When the staged file exists, the
                # download() call hits its local-cache branch (zero HTTP) and we
                # sidestep the 180s in-memory timeout entirely. Falls through to
                # the legacy _download_with_timeout path if streaming fails.
                staged_path, stage_reason = LightkurveClient._stream_mast_download(
                    row, download_dir=download_dir, read_timeout=row_read_timeout,
                )
                if staged_path is None and stage_reason not in (
                    None, "TESSCut product (deferred to lightkurve cutout path)",
                ):
                    last_download_error = stage_reason

                for attempt in range(3):
                    try:
                        lc = LightkurveClient._download_with_timeout(
                            row,
                            timeout=row_read_timeout,
                            download_dir=download_dir,
                        )
                        if lc is not None:
                            lc_list.append(lc)
                            break
                        else:
                            last_download_error = "row.download() timed out or returned no light curve"
                        break
                    except Exception as e:
                        last_download_error = LightkurveClient._classify_stream_failure(e)
                        if LightkurveClient._is_fits_corruption(e):
                            LightkurveClient._wipe_download_dir(download_dir)
                if lc_list:
                    break
            
            if not lc_list:
                return None, last_download_error
            
            lc_collection = lk.LightCurveCollection(lc_list)
            stitched = lc_collection.stitch()
            flat = stitched.normalize().remove_nans()
            
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
            k_time = kep_res['time'] + (2454833.0 - _UNIFIED_EPOCH)
            k_med = np.nanmedian(kep_res['flux'])
            k_flux = kep_res['flux'] / k_med
            k_err = kep_res['flux_err'] / k_med
            
            valid = ~np.isnan(k_flux)
            unified_t.append(k_time[valid])
            unified_f.append(k_flux[valid])
            unified_e.append(k_err[valid])
        
        if tess_res:
            t_time = tess_res['time'] + (2457000.0 - _UNIFIED_EPOCH)
            t_med = np.nanmedian(tess_res['flux'])
            t_flux = tess_res['flux'] / t_med
            t_err = tess_res['flux_err'] / t_med
            
            valid = ~np.isnan(t_flux)
            unified_t.append(t_time[valid])
            unified_f.append(t_flux[valid])
            unified_e.append(t_err[valid])

        if not unified_t:
            return None, "No valid data points remain after normalization."

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
