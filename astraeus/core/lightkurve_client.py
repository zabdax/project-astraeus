"""lightkurve_client — MAST data acquisition layer.

Precision policy
~~~~~~~~~~~~~~~~
All time, flux, and flux_err arrays MUST be stored as ``np.float64``.
Shallow transit dips (< 400 ppm) occupy the 4th–5th decimal digit of
normalised flux; float32 provides only ~7 significant digits, which is
insufficient to preserve these signals through downstream BLS and
trapezoid fitting.  Every extraction and concatenation site in this
module therefore carries an explicit ``dtype=np.float64`` guard.
"""

import os
import re
import sys
import shutil
import tempfile
import threading
import time
import random
import numpy as np
import requests
import lightkurve as lk

from astraeus.core.time_units import bjd_offset_for_mission

_LIGHTKURVE_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")
_ASTRAEUS_LIGHTKURVE_CACHE_DIR = os.environ.get(
    "ASTRAEUS_LIGHTKURVE_CACHE_DIR",
    os.path.join(tempfile.gettempdir(), "astraeus_lightkurve_cache"),
)
# Kepler row-by-row fallback limit. Evidence-driven (see logs/diagnostic_run_*.json, H1):
# A cap of 3 yielded a stitched baseline of ~218d for Kepler-90, starving 4/8 known
# planets (e, f, g, h with periods 91-331d) below the BLS 2.5x-period minimum.
# Longest known Kepler-90 period = 331.6d -> 2.5*period = 829d. At ~88d/quarter
# for long-cadence Kepler, 12 quarters gives ~1056d baseline, which exceeds
# 2.5 * longest_target_period with margin. Bounded (not "delete the cap") to
# keep download time predictable for the multi-target matrix.
_MAX_DOWNLOAD_SEGMENTS = 12         # Kepler row-by-row fallback limit (H1 patch 2026-07-06)

# Audit fix 3 (2026-08-21): _call_with_timeout previously returned None both
# for a genuine empty result and for a worker-thread overrun, so ingestion
# reported "Target not observed" for network stalls. Timeouts now return this
# sentinel; download_pipeline translates it into (None, "Network Timeout").
_TIMEOUT_SENTINEL = object()

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

# AWS S3 anonymous fallback for when MAST HTTPS gateway is unreachable.
_S3_PUBLIC_BUCKET = "stpubdata"
_S3_TESS_KEY_PREFIX = "tess/public"
_S3_KEPLER_KEY_PREFIX = "kepler/public"

# Multi-sector TESS SPOC light curve download budget.
# SPOC LCs are ~1-2 MB each; 300s is generous for download_all() but guards
# against MAST hangs.  Replaces per-row streaming for TESS LC products.
_TESS_LC_DOWNLOAD_TIMEOUT = 300.0
_TESS_LC_MAX_RETRIES = 3
_TESS_LC_RETRY_BACKOFF = 4.0     # 4s, 8s, 16s with jitter

# Curated well-known target → TIC/KIC lookup table. Lets the cache-first
# fallback resolve a human-readable target name to its numeric ID without
# any MAST query. Limited to targets that recur in the QA suite and the
# science-paper case studies; the table is intentionally small.
_TARGET_TIC_TABLE: dict[str, str] = {
    "TRAPPIST-1": "278892590",
    "AU Mic": "441420236",
    "TOI-700": "150428135",
    "WASP-12 b": "86396382",
    "HD 80606 b": "79075148",
    # KIC IDs for Kepler / K2 targets (9-digit, zero-padded).
    # R8 fix (2026-07-12): the previous table had Kepler-11 and Kepler-90
    # swapped AND Kepler-90's KIC was wrong (7 digits, off by one digit).
    # The real KIC for Kepler-90 is 11442793 (the leading zero pads to 9
    # digits as "011442793", the same digits the previous table had under
    # the wrong key "Kepler-11"). The cache-first FITS path at line ~628
    # rejects any resolved KIC shorter than 9 digits, so the wrong
    # resolution silently returned (None, None) and the orchestrator fell
    # back to live MAST downloads (slow) for every Kepler-90 run.
    # Audit fix C2 (2026-08-21, SIMBAD-verified): that same R8 rewrite left
    # "Kepler-4" pointing at 006541920 — which is KEPLER-11's real KIC —
    # and invented a nonexistent KIC 010209133 for Kepler-11. Real IDs:
    # Kepler-4 = KIC 11853905, Kepler-11 = KIC 6541920.
    "Kepler-4": "011853905",
    "Kepler-11": "006541920",   # real KIC for Kepler-11 (6-planet transiting system)
    "Kepler-20": "006850504",
    "Kepler-90": "011442793",   # real KIC for Kepler-90 (8-planet transiting system, KOI-351)
    "K2-138": "211315939",
}


def _resolve_target_to_tic(t_name: str) -> str:
    """Return the cached TIC digits for a known target name, else empty string."""
    if not t_name:
        return ""
    # Direct hit.
    if t_name in _TARGET_TIC_TABLE:
        return _TARGET_TIC_TABLE[t_name]
    # Substring match for planets whose host name is the key (e.g. "WASP-12 b").
    # Audit fix M6 (2026-08-21): the match must end at a name boundary so
    # "Kepler-9" cannot resolve to "Kepler-90"'s entry (or "Kepler-1" to
    # "Kepler-11"/"Kepler-90") — the previous bare startswith() silently
    # served the WRONG STAR's cached FITS files from the cache fallback.
    for host, tic in _TARGET_TIC_TABLE.items():
        longer, shorter = (t_name, host) if len(t_name) >= len(host) else (host, t_name)
        if not longer.startswith(shorter):
            continue
        rest = longer[len(shorter):]
        if rest == "" or re.fullmatch(r"\s+[a-z]{1,2}\b", rest):
            return tic
    return ""

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
            # Audit fix 3: distinguishable timeout signal (never None, which
            # means "genuine empty result" elsewhere).
            return _TIMEOUT_SENTINEL

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
    def _s3_key_from_uri(data_uri: str) -> str | None:
        """Map a MAST dataURI to an S3 object key on the stpubdata bucket.

        Examples::

            mast:HLSP/url/tess/public/tid/.../file.fits -> tess/public/tid/.../file.fits
            mast:Kepler/url/kepler/public/lightcurves/... -> kepler/public/lightcurves/...

        Returns ``None`` for TESSCut products or unrecognized URI formats.
        """
        if not data_uri:
            return None
        # TESSCut products are synthesized on the fly — not available on S3.
        if "TESSCut" in data_uri or "tesscut" in data_uri.lower():
            return None
        import re
        m = re.match(r"mast:TESS/product/(tess\d+-(s\d+)-(\d{16})-.*)", data_uri)
        if m:
            filename, sector, tic = m.group(1), m.group(2), m.group(3)
            return f"tess/public/tid/{sector}/{tic[0:4]}/{tic[4:8]}/{tic[8:12]}/{tic[12:16]}/{filename}"

        # Anchor on the known public prefixes inside the URI.
        for prefix in (_S3_TESS_KEY_PREFIX, _S3_KEPLER_KEY_PREFIX):
            marker = f"/{prefix}/"
            idx = data_uri.find(marker)
            if idx != -1:
                return data_uri[idx + 1:]  # strip the leading '/'
        return None

    @staticmethod
    def _s3_download(s3_key: str, final_path: str) -> bool:
        """Download a public MAST file from the stpubdata S3 bucket anonymously.

        Uses an unsigned (no-credential) request to the ``us-east-1`` region.
        The file is written to a temporary path first and atomically renamed
        on success so a crash never leaves a partial file in the cache.

        Returns ``True`` on success, ``False`` on any failure.
        """
        tmp_path = final_path + ".s3.tmp"
        try:
            import boto3
            from botocore import UNSIGNED
            from botocore.client import Config

            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            s3 = boto3.client(
                "s3",
                config=Config(signature_version=UNSIGNED),
                region_name="us-east-1",
            )
            s3.download_file(_S3_PUBLIC_BUCKET, s3_key, tmp_path)
            os.replace(tmp_path, final_path)
            print(
                f"[LightkurveClient] S3 FALLBACK: downloaded {s3_key}",
                file=sys.stderr,
            )
            return True
        except Exception as e:
            print(
                f"[LightkurveClient] S3 FALLBACK FAILED: {e}",
                file=sys.stderr,
            )
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
            return False

    @staticmethod
    def _is_valid_fits(path: str) -> bool:
        """Cheap FITS validity probe — read the first 80 bytes and confirm the
        standard FITS magic header is present.

        FITS files always start with a 2880-byte fixed-length header whose
        first 30 bytes are the literal ``SIMPLE  =`` (or ``XTENSION=``)
        keyword. Anything else means the file is a partial/truncated stub,
        an HTTP error page, or a corrupt download. We never want such a
        file to short-circuit downstream ``row.download()`` into returning
        an empty light curve.
        """
        try:
            with open(path, "rb") as fh:
                head = fh.read(80)
            if not head:
                return False
            # The first 9 bytes are the keyword token; pad-compare against
            # both the byte and str forms so we work in either Python mode.
            token = head[:9]
            return token in (b"SIMPLE  =", b"XTENSION=", "SIMPLE  =", "XTENSION=")
        except OSError:
            return False

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
        if not data_uri:
            return None, "Empty data_uri"
        if "tesscut" in data_uri.lower():
            # TESSCut products are synthesized on the fly by the TESSCut service,
            # not served as static files — let lightkurve's own cutout path handle them.
            return None, "TESSCut product (deferred to lightkurve cutout path)"

        final_path = LightkurveClient._row_cache_path(row, download_dir)
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            if LightkurveClient._is_valid_fits(final_path):
                # Already staged by a prior run / attempt — treat as a cache hit.
                return final_path, None
            # Corrupt/partial stub left by a crashed run — evict and re-download.
            try:
                os.unlink(final_path)
                print(
                    f"[LightkurveClient] CACHE EVICT: removed corrupt stub {final_path}",
                    file=sys.stderr,
                )
            except OSError:
                pass

        os.makedirs(os.path.dirname(final_path), exist_ok=True)

        s3_key = LightkurveClient._s3_key_from_uri(data_uri)
        if s3_key:
            if LightkurveClient._s3_download(s3_key, final_path):
                return final_path, None
            print(f"[LightkurveClient] S3 direct download failed, falling back to MAST HTTP for {data_uri}", file=sys.stderr)

        url = f"{_MAST_DOWNLOAD_URL}?uri={data_uri}"
        last_reason = None

        for attempt in range(_STREAM_MAX_ATTEMPTS):
            tmp_path = None
            try:
                tmp_fd = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".fits.tmp",
                    dir=os.path.dirname(final_path),
                )
                tmp_path = tmp_fd.name
                tmp_fd.close()  # reopen below in binary-write mode
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
                            if expected_n > 0 and abs(bytes_written - expected_n) / expected_n > 0.01:
                                truncated = True
                                last_reason = f"Size mismatch: got {bytes_written}, expected {expected_n}"
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
                if tmp_path:
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

        # ── S3 anonymous fallback (post-MAST-retry) ─────────────────
        # The S3 path was attempted first at the top of this function. If MAST
        # exhausts its retries, try S3 one more time — this catches the case
        # where the first S3 attempt transient-failed (e.g. AWS throttling).
        if s3_key:
            print(
                f"[LightkurveClient] S3 FALLBACK: post-MAST retry of "
                f"s3://stpubdata/{s3_key}",
                file=sys.stderr,
            )
            if LightkurveClient._s3_download(s3_key, final_path):
                return final_path, None

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

            # TESS SPOC: keep only short-cadence products (≤30-min). 30-min
            # FFI rows are dominated by systematics and frequently have
            # very different NaN patterns than 2-min SPOC, which makes
            # `stitch()` return an empty array after `remove_nans()`.
            if mission_type == "TESS" and "exptime" in table.colnames:
                exposure = np.asarray(table["exptime"], dtype=float)
                short_cadence = np.isfinite(exposure) & (exposure <= 1800.0)
                if np.any(short_cadence):
                    dropped = int(np.sum(~short_cadence))
                    if dropped:
                        print(
                            f"[LightkurveClient] TESS: dropping {dropped} "
                            f"long-cadence rows (exptime > 1800s) to keep "
                            f"short-cadence stitch clean.",
                            file=sys.stderr,
                        )
                    search = search[short_cadence]
                    table = search.table

            if "size" in table.colnames:
                sizes = np.asarray(table["size"], dtype=float)
                sizes = np.where(np.isfinite(sizes), sizes, np.inf)
                return search[np.argsort(sizes)]
        except Exception:
            return search

        return search

    @staticmethod
    def _download_tess_lightcurves(search_result, download_dir: str) -> tuple[list, str | None]:
        """Download all TESS SPOC light curves with retry and per-sector validation.

        Uses ``search_result.download_all()`` instead of per-row streaming to
        avoid the heavyweight ``_stream_mast_download`` path (designed for
        10 GB+ FFI cutouts) on ~1–2 MB SPOC products.  Each sector is
        validated individually: empty, all-NaN, or otherwise corrupt sectors
        are dropped so that a single bad sector cannot poison the stitch.

        Mixed cadences (e.g. 2-min and 10-min SPOC products) are detected and
        logged; ``stitch()`` handles the resampling transparently.

        Returns
        -------
        lc_list : list[lightkurve.LightCurve]
            Validated per-sector light curves ready for stitching.
        error : str | None
            Human-readable error message if *all* attempts failed.
        """
        lc_list = []
        last_error = None
        cadences_seen: set[int] = set()

        row_read_timeout = 120.0  # bumped from 60s: fresh-FITS parse can be slow

        for idx, row in enumerate(search_result):
            staged_path, stage_reason = LightkurveClient._stream_mast_download(
                row, download_dir=download_dir, read_timeout=row_read_timeout
            )

            if staged_path is None and stage_reason not in (
                None, "TESSCut product (deferred to lightkurve cutout path)",
            ):
                print(
                    f"[LightkurveClient] TESS sector {idx}: "
                    f"download failed — {stage_reason}",
                    file=sys.stderr,
                )
                last_error = stage_reason
                continue

            try:
                # It's already in the cache layout, so download() is local.
                lc = LightkurveClient._download_with_timeout(
                    row, timeout=30.0, download_dir=download_dir
                )

                # Audit fix 3: a timed-out sector download must not be fed
                # into the validation path (sentinel has no .flux).
                if lc is _TIMEOUT_SENTINEL:
                    print(
                        f"[LightkurveClient] TESS sector {idx}: "
                        f"download timed out — skipped.",
                        file=sys.stderr,
                    )
                    last_error = "row.download() timed out"
                    continue

                if lc is None or len(lc.flux) == 0:
                    print(
                        f"[LightkurveClient] TESS sector {idx}: "
                        f"empty — skipped.",
                        file=sys.stderr,
                    )
                    continue

                flux_arr = np.asarray(lc.flux.value, dtype=np.float64)
                if np.all(~np.isfinite(flux_arr)):
                    print(
                        f"[LightkurveClient] TESS sector {idx}: "
                        f"all-NaN flux — skipped.",
                        file=sys.stderr,
                    )
                    continue

                # Track cadence for mixed-cadence warning.
                if hasattr(lc, "meta") and lc.meta and "TIMEDEL" in lc.meta:
                    cadences_seen.add(
                        round(float(lc.meta["TIMEDEL"]) * 86400)
                    )  # seconds

                lc_list.append(lc)
            except Exception as sec_exc:
                print(
                    f"[LightkurveClient] TESS sector {idx}: "
                    f"validation error — {sec_exc}",
                    file=sys.stderr,
                )

        if cadences_seen and len(cadences_seen) > 1:
            print(
                f"[LightkurveClient] TESS: mixed cadences detected "
                f"{cadences_seen}s — stitch() will handle resampling.",
                file=sys.stderr,
            )

        if lc_list:
            print(
                f"[LightkurveClient] TESS: {len(lc_list)}/"
                f"{len(search_result)} sectors validated.",
                file=sys.stderr,
            )
            return lc_list, None

        if last_error is None:
            last_error = f"All {len(search_result)} downloaded sectors failed validation"
            
        return [], last_error

    @staticmethod
    def _try_serve_from_cache(t_name: str, mission_type: str, download_dir: str) -> tuple[dict | None, str | None]:
        """Cache-first fallback for when MAST search is unreachable.

        If any valid FITS files matching the target's TIC/KIC are already
        on disk (e.g. from a prior successful run), assemble a stitched
        light curve from them without ever touching the network.

        The matcher scans the MAST-download layout for files whose TIC or
        KIC appears in their path. The target name's embedded digits (e.g.
        ``441420236`` from ``TIC 441420236``) are used as a fallback
        identifier when the search is unreachable.

        Returns ``(lc_dict, None)`` on cache hit, ``(None, None)`` on miss.
        """
        try:
            # QA mode: honour ASTRAEUS_FORCE_NETWORK=1 by skipping the cache
            # lookup entirely. This lets the QA harness exercise the dynamic
            # MAST/S3 path on every run, even for targets that already have
            # files on disk. Default behaviour (env var unset) is unchanged.
            if os.environ.get("ASTRAEUS_FORCE_NETWORK") == "1":
                print(
                    f"[LightkurveClient] cache bypass: ASTRAEUS_FORCE_NETWORK=1; "
                    f"skipping cache lookup for {t_name}",
                    file=sys.stderr,
                )
                return None, None

            mission_subdir = "TESS" if mission_type == "TESS" else "Kepler"
            mast_root = os.path.join(download_dir, "mastDownload", mission_subdir)
            if not os.path.isdir(mast_root):
                return None, None

            target_digits = "".join(ch for ch in t_name if ch.isdigit())
            # TESS/KIC identifiers are 16-digit TICs or 9-digit KICs embedded
            # in the sector directory name (e.g. "0000000441420236-0120-s").
            fits_files: list[str] = []
            matched_ids: set[str] = set()
            # Resolve to a full TIC/KIC if the target name is a friendly name
            # (e.g. "TRAPPIST-1" → "278892590"). A naive embedded-digits pull
            # would only see "1" from "TRAPPIST-1" and never match.
            resolved_tic = _resolve_target_to_tic(t_name)
            if resolved_tic:
                target_digits = resolved_tic
            if not target_digits or len(target_digits) < 9:
                return None, None

            for dirpath, _, filenames in os.walk(mast_root):
                for fn in filenames:
                    if not fn.endswith(".fits"):
                        continue
                    full = os.path.join(dirpath, fn)
                    if not LightkurveClient._is_valid_fits(full):
                        continue
                    # Extract the 16-digit TIC or 9-digit KIC token.
                    id_tokens: list[str] = []
                    for chunk in fn.replace("-", "_").split("_"):
                        chunk_digits = "".join(ch for ch in chunk if ch.isdigit())
                        if len(chunk_digits) >= 9:
                            id_tokens.append(chunk_digits)
                    if not id_tokens:
                        continue
                    # Right-aligned numeric match: strip leading zeros from
                    # BOTH the target and the token before comparing. This
                    # handles both 16-digit TICs (e.g. "0000000278892590")
                    # and 9-digit KICs (e.g. "011442793") uniformly.
                    target_stripped = target_digits.lstrip("0") or "0"
                    matched = any(
                        target_stripped == tk.lstrip("0") or target_stripped == "0"
                        for tk in id_tokens
                    )
                    if not matched:
                        continue
                    matched_ids.add(target_digits)
                    fits_files.append(full)

            if not fits_files:
                return None, None

            import lightkurve as lk
            lcs = []
            for path in fits_files:
                try:
                    lc = lk.read(path)
                    if lc is None or len(lc.flux) == 0:
                        continue
                    lcs.append(lc)
                except Exception as exc:
                    print(
                        f"[LightkurveClient] CACHE: failed to read {path}: {exc}",
                        file=sys.stderr,
                    )

            if not lcs:
                return None, None

            print(
                f"[LightkurveClient] CACHE HIT: assembled {len(lcs)} sectors "
                f"for {t_name} ({mission_type}) from local cache "
                f"(matched ids: {sorted(matched_ids)[:3]}).",
                file=sys.stderr,
            )
            stitched = lk.LightCurveCollection(lcs).stitch()
            flat = stitched.normalize().remove_nans()
            t = np.asarray(flat.time.value, dtype=np.float64)
            # I2 fix (round-2 diagnostic 2026-07-06, see
            # logs/diagnostic_run_round2_*.json): lightkurve returns the
            # time array in mission-specific offset units (BKJD for
            # Kepler = BJD - 2454833, BTJD for TESS = BJD - 2457000).
            # Downstream consumers in this codebase (orchestrator, NASA
            # archive comparison, reporting) historically compared
            # `lc.time` directly to NASA `pl_tranmid` values, which are
            # in BJD full — silently producing offsets of ~2454833 days
            # with no error signal. Convert to BJD full at the
            # ingestion boundary and tag the dict so this class of
            # bug cannot recur silently.
            # Audit fix 4 (2026-08-21): the offset must come from the single
            # source of truth in time_units — the previous inline ternary
            # applied the TESS (BTJD) offset to every non-Kepler mission,
            # which would mis-scale K2 (BKJD) by 2167 days.
            bjd_epoch_offset = bjd_offset_for_mission(mission_type)
            t = t + bjd_epoch_offset
            f = np.asarray(flat.flux.value, dtype=np.float64)
            e = np.asarray(flat.flux_err.value, dtype=np.float64)
            valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
            t, f, e = t[valid], f[valid], e[valid]
            if len(t) == 0:
                return None, None
            sort_idx = np.argsort(t)
            return {
                "time": t[sort_idx],
                "flux": f[sort_idx],
                "flux_err": e[sort_idx],
                "time_unit": "BJD",
                "bjd_epoch_offset_applied": bjd_epoch_offset,
            }, None
        except Exception as exc:
            print(
                f"[LightkurveClient] CACHE FALLBACK: error scanning cache — {exc}",
                file=sys.stderr,
            )
            return None, None

    @staticmethod
    def download_pipeline(t_name, mission_type: str) -> tuple[dict | None, str | None]:
        """Download and stitch light-curve data for a target.

        For **TESS** targets the method downloads *all* available SPOC
        sectors via ``download_all()`` with per-sector validation and
        per-sector median-normalization before stitching, eliminating
        baseline cliffs between sectors.

        For **Kepler** targets the legacy row-by-row streaming path is
        retained (single-quarter files are well-behaved).
        """
        mast_error = None
        download_dir = LightkurveClient._download_cache_dir()

        # Cache-first: if MAST/Search is unreachable but we already have valid
        # FITS files on disk for this target, assemble a stitched light curve
        # without touching the network at all. This is what makes offline
        # replays of the QA harness fast and deterministic.
        cached, _ = LightkurveClient._try_serve_from_cache(t_name, mission_type, download_dir)
        if cached is not None:
            return cached, None

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

            if search is _TIMEOUT_SENTINEL:
                # Audit fix 3: a 90s search stall must surface as a network
                # timeout, not as "Target not observed" ((None, None)).
                return None, "Network Timeout"

            if search is None or len(search) == 0:
                return None, None

            search = LightkurveClient._prioritize_search_results(search, mission_type)

            # ── TESS: multi-sector download_all() path ─────────────────
            if mission_type == "TESS":
                lc_list, last_download_error = (
                    LightkurveClient._download_tess_lightcurves(search, download_dir)
                )

                if not lc_list:
                    return None, last_download_error

                # Per-sector normalization eliminates baseline cliffs
                # between sectors with different instrumental zero-points.
                lc_collection = lk.LightCurveCollection(lc_list)
                stitched = lc_collection.stitch(
                    corrector_func=lambda lc: lc.normalize()
                )
                flat = stitched.remove_nans()

            # ── Kepler: legacy row-by-row path (unchanged) ─────────────
            else:
                row_read_timeout = _KEPLER_READ_TIMEOUT

                lc_list = []
                last_download_error = None
                for row in search[:_MAX_DOWNLOAD_SEGMENTS]:
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
                            # Audit fix 3: timeout now arrives as the
                            # sentinel (never None) and must be retried.
                            if lc is _TIMEOUT_SENTINEL:
                                last_download_error = "row.download() timed out"
                                continue
                            if lc is not None:
                                lc_list.append(lc)
                                break
                            else:
                                last_download_error = "row.download() timed out or returned no light curve"
                            # Audit fix 2 (2026-08-21): the unconditional
                            # `break` that used to sit here killed the 3-attempt
                            # retry loop on the timeout branch — timeouts were
                            # never retried. Falling through now re-enters the
                            # attempt loop.
                        except Exception as e:
                            last_download_error = LightkurveClient._classify_stream_failure(e)
                            if LightkurveClient._is_fits_corruption(e):
                                bad_path = LightkurveClient._row_cache_path(row, download_dir)
                                if os.path.exists(bad_path):
                                    try:
                                        os.remove(bad_path)
                                        print(f"[LightkurveClient] CACHE EVICT: removed corrupt file {bad_path}", file=sys.stderr)
                                    except OSError:
                                        pass
                    # Audit fix 1 (2026-08-21): no early exit after the first
                    # successful quarter. The documented baseline (module
                    # header, H1 evidence) needs up to _MAX_DOWNLOAD_SEGMENTS
                    # quarters stitched; the old `if lc_list: break` here
                    # silently truncated the Kepler baseline to ONE quarter.

                if not lc_list:
                    return None, last_download_error

                lc_collection = lk.LightCurveCollection(lc_list)
                stitched = lc_collection.stitch()
                flat = stitched.normalize().remove_nans()

            # ── Common: extract float64 arrays ─────────────────────────
            t = np.asarray(flat.time.value, dtype=np.float64)
            f = np.asarray(flat.flux.value, dtype=np.float64)
            e = np.asarray(flat.flux_err.value, dtype=np.float64)

            # I2 fix (round-2 diagnostic 2026-07-06): convert the
            # mission-specific time offset (BKJD for Kepler, BTJD for
            # TESS) to BJD full at the ingestion boundary so every
            # downstream consumer — orchestrator, NASA archive
            # comparison, reporting — gets a consistent, explicitly
            # labeled epoch. The conversion was previously done nowhere,
            # so any t0/epoch value compared to NASA `pl_tranmid` (BJD
            # full) was silently off by ~2454833 days. The dict also
            # carries `time_unit` / `bjd_epoch_offset_applied` so this
            # class of bug cannot recur silently elsewhere later.
            # Audit fix 4 (2026-08-21): use the time_units single source of
            # truth (Kepler/K2 = BKJD 2454833, TESS = BTJD 2457000) instead
            # of an inline ternary that applied the TESS offset to every
            # non-Kepler mission (K2 would be wrong by 2167 days).
            bjd_epoch_offset = bjd_offset_for_mission(mission_type)
            t = t + bjd_epoch_offset

            valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
            t, f, e = t[valid], f[valid], e[valid]

            if len(t) == 0:
                return None, None

            sort_idx = np.argsort(t)
            return {
                "time": t[sort_idx],
                "flux": f[sort_idx],
                "flux_err": e[sort_idx],
                "time_unit": "BJD",
                "bjd_epoch_offset_applied": bjd_epoch_offset,
            }, None

        except Exception as exc:
            mast_error = str(exc)
            print(
                f"[LightkurveClient] MAST path failed ({mast_error}); "
                f"attempting cache fallback.",
                file=sys.stderr,
            )
            cached, _ = LightkurveClient._try_serve_from_cache(t_name, mission_type, download_dir)
            if cached is not None:
                return cached, None
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
                resp = requests.get(url, params=params, timeout=30.0)
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
        #
        # I2 fix (round-2 diagnostic 2026-07-06): download_pipeline
        # already converts BKJD/BTJD to BJD full at the ingestion
        # boundary, so both `kep_res['time']` and `tess_res['time']`
        # are already in BJD full. The previous code added an extra
        # `(mission_epoch - _UNIFIED_EPOCH)` offset on top, which was a
        # no-op for Kepler (both = 2454833) and wrong for TESS (the
        # fused time was offset by 2457000 - 2454833 = 2167 days).
        # Drop the extra offset; both arrays are already in BJD full.

        unified_t = []
        unified_f = []
        unified_e = []

        if kep_res:
            k_time = np.asarray(kep_res['time'], dtype=np.float64)
            k_flux_raw = np.asarray(kep_res['flux'], dtype=np.float64)
            k_err_raw = np.asarray(kep_res['flux_err'], dtype=np.float64)
            k_med = np.float64(np.nanmedian(k_flux_raw))
            k_flux = k_flux_raw / k_med
            k_err = k_err_raw / k_med

            valid = ~np.isnan(k_flux)
            unified_t.append(k_time[valid])
            unified_f.append(k_flux[valid])
            unified_e.append(k_err[valid])

        if tess_res:
            t_time = np.asarray(tess_res['time'], dtype=np.float64)
            t_flux_raw = np.asarray(tess_res['flux'], dtype=np.float64)
            t_err_raw = np.asarray(tess_res['flux_err'], dtype=np.float64)
            t_med = np.float64(np.nanmedian(t_flux_raw))
            t_flux = t_flux_raw / t_med
            t_err = t_err_raw / t_med

            valid = ~np.isnan(t_flux)
            unified_t.append(t_time[valid])
            unified_f.append(t_flux[valid])
            unified_e.append(t_err[valid])

        if not unified_t:
            return None, "No valid data points remain after normalization."

        # Final dtype guard: np.concatenate preserves input dtype when all
        # inputs match, but an explicit cast is cheap insurance against any
        # future code-path that feeds non-float64 arrays into unified_*.
        t_out = np.concatenate(unified_t).astype(np.float64, copy=False)
        f_out = np.concatenate(unified_f).astype(np.float64, copy=False)
        e_out = np.concatenate(unified_e).astype(np.float64, copy=False)

        idx = np.argsort(t_out)
        return {
            "time": t_out[idx],
            "flux": f_out[idx],
            "flux_err": e_out[idx],
            "baseline": "unified",
            "kepler_segments": 1 if kep_res else 0,
            "tess_segments": 1 if tess_res else 0
        }, None
