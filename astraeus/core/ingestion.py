import io
import os
import re
import shutil
import sys
import threading
import numpy as np
import pandas as pd
from astropy.io import fits
fits.conf.use_memmap = False
import lightkurve as lk
import streamlit as st
import socket
socket.setdefaulttimeout(30.0)

class DataAdapter:
    """
    Format-agnostic adapter to parse CSV and FITS datasets from memory.
    """
    def __init__(self, data_bytes: bytes, filename: str):
        self.data_bytes = data_bytes
        self.filename = filename.lower()
        self.TIME_HEADERS = ['time', 'bjd', 'hjd', 'mjd', 'bjd_tdb']
        self.FLUX_HEADERS = ['flux', 'pdcsap_flux', 'sap_flux', 'intensity', 'counts']
        self.ERR_HEADERS = ['flux_err', 'err', 'error', 'pdcsap_flux_err']

    def parse(self) -> dict:
        is_csv = self.filename.endswith(".csv")
        is_fits = self.filename.endswith(".fits") or self.filename.endswith(".fit")

        if is_csv:
            df = pd.read_csv(io.BytesIO(self.data_bytes))
            # lowercase columns to prevent case-sensitivity tracebacks
            df.columns = [c.lower() for c in df.columns]
            
            t_col = next((c for c in df.columns if c in self.TIME_HEADERS or any(t in c for t in self.TIME_HEADERS)), None)
            f_col = next((c for c in df.columns if (c in self.FLUX_HEADERS or 'flux' in c) and 'err' not in c), None)
            e_col = next((c for c in df.columns if 'err' in c), None)

            if not t_col or not f_col:
                raise ValueError("Could not auto-detect time and flux columns in CSV.")

            t = df[t_col].to_numpy(dtype=np.float64)
            f = df[f_col].to_numpy(dtype=np.float64)
            e = df[e_col].to_numpy(dtype=np.float64) if e_col else np.zeros_like(t)
            
            return self._clean_arrays(t, f, e)

        elif is_fits:
            with fits.open(io.BytesIO(self.data_bytes)) as hdul:
                table_hdu = None
                for hdu in hdul:
                    if isinstance(hdu, fits.BinTableHDU):
                        table_hdu = hdu
                        break
                if table_hdu is None:
                    raise ValueError("No binary table found in FITS file.")
                
                cols = [c.lower() for c in table_hdu.columns.names]
                t_col = next((c for c in cols if c in self.TIME_HEADERS or any(t in c for t in self.TIME_HEADERS)), None)
                f_col = next((c for c in cols if (c in self.FLUX_HEADERS or 'flux' in c) and 'err' not in c), None)
                e_col = next((c for c in cols if 'err' in c), None)

                if not t_col or not f_col:
                    raise ValueError("Could not auto-detect time and flux columns in FITS table.")

                t = np.array(table_hdu.data[table_hdu.columns.names[cols.index(t_col)]], dtype=np.float64)
                f = np.array(table_hdu.data[table_hdu.columns.names[cols.index(f_col)]], dtype=np.float64)
                e = np.array(table_hdu.data[table_hdu.columns.names[cols.index(e_col)]], dtype=np.float64) if e_col else np.zeros_like(t)
                
                return self._clean_arrays(t, f, e)
        else:
            raise ValueError("Unsupported file format. Must be .csv or .fits.")

    def _clean_arrays(self, t, f, e) -> dict:
        valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
        t = t[valid]
        f = f[valid]
        e = e[valid]
        
        sort_idx = np.argsort(t)
        t = t[sort_idx]
        f = f[sort_idx]
        e = e[sort_idx]
        
        return {'time': t, 'flux': f, 'flux_err': e}


# ---------------------------------------------------------------------------
# Lightkurve local cache path (platform-agnostic)
# ---------------------------------------------------------------------------
_LIGHTKURVE_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")


class RemoteDiscoveryEngine:
    """
    Connects to NASA Exoplanet Archive (TAP/pscomppars table) and MAST via
    Lightkurve.  All archive field access uses primary → fallback → derived
    resolution so that coordinate fields are never silently dropped.
    """

    # ------------------------------------------------------------------
    # Archive query configuration
    # ------------------------------------------------------------------
    #: Comprehensive confirmed-planet composite-parameter table (primary).
    _ARCHIVE_TABLE = "pscomppars"

    #: Stable reference table used as the multi-table fallback when the
    #: composite table returns NULL for orbital period.
    _FALLBACK_TABLE = "ps"

    #: All columns fetched in a single round-trip from pscomppars.  Includes
    #: every primary field AND its error-column fallback, plus pl_ratror for
    #: the derived transit-depth calculation, and st_lum as a tertiary
    #: stellar-radius proxy.
    _ARCHIVE_SELECT = (
        "pl_name, "
        "pl_orbper, pl_orbpererr1, "
        "st_rad, st_raderr1, st_lum, "
        "st_teff, st_mass, sy_jmag, "
        "pl_trandep, pl_ratror"
    )

    #: Narrow column set fetched from the fallback ``ps`` table.  We only
    #: need the orbital period and its positive error here.
    _FALLBACK_SELECT = "pl_name, pl_orbper, pl_orbpererr1"

    # ------------------------------------------------------------------
    # Target-name normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_target_name(raw: str) -> str:
        """Return a canonically formatted exoplanet name.

        Handles common malformed variants, for example:

        * ``'Wasp - 12b'``   →  ``'WASP-12 b'``
        * ``'WASP12b'``      →  ``'WASP-12 b'``
        * ``'wasp 12 b'``    →  ``'WASP-12 b'``
        * ``'HAT-P-11b'``    →  ``'HAT-P-11 b'``
        * ``'kepler-10b'``   →  ``'Kepler-10 b'``

        The pipeline is:

        1. Strip leading/trailing whitespace.
        2. Collapse every internal run of whitespace → single space.
        3. Remove spurious spaces surrounding a hyphen
           (``'WASP - 12'`` → ``'WASP-12'``).
        4. For known catalogue prefixes (WASP, HAT-P, Kepler, K2, TOI,
           TrES, XO, GJ, KELT, HD, HIP, TYC) apply a regex that:
           a. Upper-cases / title-cases the prefix correctly.
           b. Ensures a hyphen immediately follows the prefix (no space).
           c. Ensures a single space separates the planet letter suffix
              from the numeric body (``'12b'`` → ``'12 b'``).
        5. Fall back to collapsing whitespace only for any unrecognised
           names so the original casing is preserved.
        """
        name = raw.strip()
        # Step 1-2: normalise internal whitespace
        name = re.sub(r"\s+", " ", name)
        # Step 3: remove spaces that flank a hyphen  (e.g. 'WASP - 12')
        name = re.sub(r"\s*-\s*", "-", name)

        # Step 4: catalogue-prefix canonical form
        # Pattern breakdown:
        #   (PREFIX)   – the catalogue prefix, case-insensitive
        #   [-\s]?     – optional separator between prefix and number
        #   (\d+)      – the numeric system identifier
        #   (?:[-\s]?) – optional separator before planet letter
        #   ([a-zA-Z]) – single-letter planet designator
        #   \b         – word boundary (no trailing digits)
        _PREFIX_PATTERN = re.compile(
            r"^(wasp|hat-?p|kepler|k2|toi|tres|xo|gj|kelt|hd|hip|tyc)"
            r"[-\s]?(\d+)"
            r"(?:[-\s]?([a-zA-Z]))$",
            re.IGNORECASE,
        )

        # Canonical upper-case map for known prefixes
        _PREFIX_CASE: dict = {
            "wasp": "WASP",
            "hatp": "HAT-P",
            "hat-p": "HAT-P",
            "kepler": "Kepler",
            "k2": "K2",
            "toi": "TOI",
            "tres": "TrES",
            "xo": "XO",
            "gj": "GJ",
            "kelt": "KELT",
            "hd": "HD",
            "hip": "HIP",
            "tyc": "TYC",
        }

        m = _PREFIX_PATTERN.match(name)
        if m:
            prefix_raw = m.group(1).lower().replace(" ", "")
            number = m.group(2)
            letter = m.group(3).lower() if m.group(3) else ""
            canonical_prefix = _PREFIX_CASE.get(prefix_raw, prefix_raw.upper())
            if letter:
                return f"{canonical_prefix}-{number} {letter}"
            return f"{canonical_prefix}-{number}"

        # Step 5: fallback – return whitespace-collapsed name unchanged
        return name

    # ------------------------------------------------------------------
    # Field-level value resolver
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_float(row, primary: str, *fallbacks: str) -> float | None:
        """Extract a float from *row*, trying *primary* then each *fallback* in order.

        Accepts an arbitrary number of fallback column names so that multi-level
        resolution chains (e.g. st_rad → st_raderr1 → st_lum) can be expressed
        in a single call.

        Returns ``None`` when every candidate column is masked or absent.
        """
        for col in filter(None, [primary, *fallbacks]):
            try:
                if hasattr(row, 'get'):
                    val = row.get(col)
                else:
                    val = row[col]

                if val is None or np.ma.is_masked(val):
                    continue

                if hasattr(val, 'value'):
                    val = val.value

                if isinstance(val, str):
                    val = val.strip()
                    if " " in val:
                        val = val.split()[0]
                    val = val.replace('%', '')
                    val = re.sub(r'[^\d\.\-eE]', '', val)

                return float(val)
            except Exception as e:
                print(f"[ERROR] CRITICAL PARSING FAILURE for key '{col}': {e}")
                continue
        return None

    # ------------------------------------------------------------------
    # Multi-table fallback: ps table orbital-period probe
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_ps_orbital_period(safe_canonical: str) -> float | None:
        """Fire a secondary query against the ``ps`` (confirmed-planets primary)
        reference table to retrieve the official orbital period when
        ``pscomppars`` returns NULL/masked.

        The ``ps`` table aggregates one row per planet per reference paper;
        we order by ``pl_orbper DESC`` so that the best-documented value
        (largest non-null entry) floats to position 0.

        Parameters
        ----------
        safe_canonical:
            Planet name already stripped and canonicalised.

        Returns
        -------
        float or None
            Orbital period in days, or ``None`` if the fallback table also
            lacks a valid measurement.
        """
        try:
            import requests
            url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
            query = f"select pl_name, pl_orbper, pl_orbpererr1 from ps where pl_name='{safe_canonical}' and pl_orbper is not null order by pl_orbper desc"
            params = {"query": query, "format": "json"}

            try:
                resp = requests.get(url, params=params, timeout=3.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(
                    f"[RemoteDiscoveryEngine] ps-table fallback query timed out for '{safe_canonical}': {e}",
                    file=sys.stderr,
                )
                return None

            if data and len(data) > 0:
                row = data[0]
                period = row.get('pl_orbper')
                if period is None:
                    period = row.get('pl_orbpererr1')
                if period is not None:
                    period = float(period)
                    print(
                        f"[RemoteDiscoveryEngine] ps-table fallback supplied "
                        f"pl_orbper={period:.6f} d for '{safe_canonical}'.",
                        file=sys.stderr,
                    )
                    return period
            print(
                f"[RemoteDiscoveryEngine] ps-table fallback also returned no "
                f"valid orbital period for '{safe_canonical}'.",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[RemoteDiscoveryEngine] ps-table fallback query failed for "
                f"'{safe_canonical}': {exc}",
                file=sys.stderr,
            )
        return None

    # ------------------------------------------------------------------
    # Numeric sanitization layer
    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize_meta(meta: dict) -> dict:
        """Guarantee that every numeric key in the metadata dictionary is a
        clean, strictly-typed float — never ``None``, ``NaN``, or a masked
        scalar.  Downstream metric-card widgets receive safe defaults instead
        of propagating ``NoneType`` errors.

        Default baseline values
        -----------------------
        * ``orbital_period`` / ``pl_orbper``   → ``0.0``   (unknown period)
        * ``transit_depth``  / ``pl_trandep``  → ``0.0``   (unknown depth)
        * ``stellar_radius`` / ``st_rad``      → ``1.0``   (Solar baseline)
        """
        _FLOAT_DEFAULTS: dict[str, float] = {
            "orbital_period": 0.0,
            "pl_orbper":      0.0,
            "transit_depth":  0.0,
            "pl_trandep":     0.0,
            "stellar_radius": 1.0,
            "st_rad":         1.0,
            "st_teff":        5778.0,
            "st_mass":        1.0,
            "sy_jmag":        10.0,
        }

        for key, default in _FLOAT_DEFAULTS.items():
            raw = meta.get(key)
            # Treat None, masked scalars, and IEEE NaN as missing
            if raw is None:
                meta[key] = default
                continue
            try:
                if np.ma.is_masked(raw):
                    meta[key] = default
                    continue
                fval = float(raw)
                meta[key] = default if (np.isnan(fval) or np.isinf(fval)) else fval
            except (TypeError, ValueError):
                meta[key] = default

        return meta

    # ------------------------------------------------------------------
    # FITS corruption cache wiper
    # ------------------------------------------------------------------
    @staticmethod
    def _wipe_lightkurve_cache() -> None:
        """Remove the entire Lightkurve download cache from disk.

        This is invoked automatically when a FITS truncation or corruption
        error is detected during ``download_all()`` or ``stitch()``, allowing
        the pipeline to retry from a clean slate against the live MAST servers.
        """
        cache_dir = _LIGHTKURVE_CACHE_DIR
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                print(
                    f"[RemoteDiscoveryEngine] CACHE WIPER: Removed corrupted "
                    f"cache directory '{cache_dir}'.",
                    file=sys.stderr,
                )
            except Exception as rm_err:
                print(
                    f"[RemoteDiscoveryEngine] CACHE WIPER: Failed to remove "
                    f"'{cache_dir}': {rm_err}",
                    file=sys.stderr,
                )
        else:
            print(
                f"[RemoteDiscoveryEngine] CACHE WIPER: Cache directory "
                f"'{cache_dir}' does not exist; nothing to remove.",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # Thread-guarded callable timeout (prevents SSL-read deadlocks)
    # ------------------------------------------------------------------
    @staticmethod
    def _call_with_timeout(fn, args=(), kwargs=None, timeout: float = 15.0,
                           label: str = "operation"):
        """Run *fn(*args, **kwargs)* inside a daemon thread with a hard
        *timeout* ceiling.

        Returns the callable's result on success, or ``None`` if the thread
        is still alive after *timeout* seconds.  Exceptions raised inside
        the worker are re-raised in the calling thread.
        """
        if kwargs is None:
            kwargs = {}
        result_box: list = []
        error_box: list = []

        def _worker():
            try:
                result_box.append(fn(*args, **kwargs))
            except Exception as exc:
                error_box.append(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            print(
                f"[RemoteDiscoveryEngine] TIMEOUT: {label} "
                f"exceeded {timeout:.0f}s — skipping.",
                file=sys.stderr,
            )
            return None

        if error_box:
            raise error_box[0]

        return result_box[0] if result_box else None

    @staticmethod
    def _download_with_timeout(row, timeout: float = 12.0):
        """Convenience wrapper: download a single Lightkurve search row
        with a per-sector timeout guard."""
        return RemoteDiscoveryEngine._call_with_timeout(
            row.download, timeout=timeout, label="row.download()"
        )

    @staticmethod
    def _is_fits_corruption(exc: Exception) -> bool:
        """Return True if *exc* looks like a FITS file truncation or
        corruption failure that can be healed by clearing the local cache."""
        msg = str(exc).lower()
        return any(kw in msg for kw in ("truncated", "corrupt", "not a fits",
                                         "end-of-file", "header missing",
                                         "block does not begin"))

    # ------------------------------------------------------------------
    # Public entry point (implementation — called by the cached wrapper below)
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_data_impl(target_name: str, mission: str) -> dict:
        """Inner (un-cached) implementation of fetch_data.

        Separated from the public entry point so that ``@st.cache_data`` can be
        applied at *module level* on the wrapper function ``fetch_data``, which
        is the only reliable way to cache a callable that lives inside a class in
        all supported Streamlit versions.
        """
        # ── 0. Normalise the target name before any network call ──────────
        canonical = RemoteDiscoveryEngine._normalize_target_name(target_name)

        # ── 1. Fetch metadata from NASA Exoplanet Archive (TAP) ───────────
        meta: dict = {}
        archive_error: str | None = None
        try:
            # ── Strip the canonical name immediately before embedding it in
            # the TAP WHERE clause.  Trailing whitespace causes partial-row
            # rejections in the NASA Archive matrix even after normalisation.
            safe_canonical = canonical.strip()

            import requests
            import time
            url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
            query = f"select pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror from pscomppars where pl_name='{safe_canonical}'"
            params = {"query": query, "format": "json"}

            data = []
            for attempt in range(3):
                try:
                    resp = requests.get(url, params=params, timeout=15.0)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"[RemoteDiscoveryEngine] Archive query failed or timed out after 3 attempts: {e}", file=sys.stderr)
                    else:
                        time.sleep(2.0)

            print("--- NASA ARCHIVE DIAGNOSTIC AUDIT ---")
            print(f"Payload Type: {type(data)}")

            if data and len(data) > 0:
                row = data[0]
                print(f"Raw Row 0 Content: {row}")

                # ── Orbital Period ─────────────────────────────────────────
                pl_orbper = row.get('pl_orbper')
                if pl_orbper is None:
                    pl_orbper = row.get('pl_period')
                if pl_orbper is None:
                    pl_orbper = row.get('pl_orbpererr1')

                if pl_orbper is not None:
                    pl_orbper = float(pl_orbper)
                else:
                    print(
                        f"[RemoteDiscoveryEngine] pscomppars orbital period masked for "
                        f"'{safe_canonical}'; escalating to ps-table fallback query.",
                        file=sys.stderr,
                    )
                    pl_orbper = RemoteDiscoveryEngine._fetch_ps_orbital_period(safe_canonical)
                    if pl_orbper is None:
                        print(
                            f"[RemoteDiscoveryEngine] Both tables lack orbital period "
                            f"for '{safe_canonical}'; flooring to 0.0.",
                            file=sys.stderr,
                        )
                        pl_orbper = 0.0

                # ── Stellar Radius ─────────────────────────────────────────
                st_rad = row.get('st_rad')
                if st_rad is not None:
                    st_rad = abs(float(st_rad))
                else:
                    st_lum = row.get('st_lum')
                    st_teff = row.get('st_teff')
                    if st_lum is not None and st_teff is not None and float(st_teff) > 0:
                        st_lum = float(st_lum)
                        st_teff = float(st_teff)
                        st_rad = abs(np.sqrt(10.0 ** st_lum) * (5778.0 / st_teff) ** 2)
                        print(
                            f"[RemoteDiscoveryEngine] st_rad derived from "
                            f"st_lum={st_lum:.4f}, "
                            f"st_teff={st_teff:.0f} → {st_rad:.4f} R☉",
                            file=sys.stderr,
                        )

                print(
                    f"[RemoteDiscoveryEngine] STELLAR RADIUS RESOLUTION: "
                    f"st_rad="
                    f"{'ARCHIVE ' + f'{st_rad:.4f}' if st_rad is not None else 'UNRESOLVED → default 1.0'}"
                    f" R☉ for '{safe_canonical}'",
                    file=sys.stderr,
                )

                # ── Stellar Effective Temperature ──────────────────────────
                st_teff = float(row.get('st_teff')) if row.get('st_teff') is not None else 5778.0

                # ── Stellar Mass ───────────────────────────────────────────
                st_mass = float(row.get('st_mass')) if row.get('st_mass') is not None else 1.0

                # ── J-Band Magnitude ───────────────────────────────────────
                sy_jmag = float(row.get('sy_jmag')) if row.get('sy_jmag') is not None else 10.0

                # ── Transit Depth ──────────────────────────────────────────
                pl_trandep = row.get('pl_trandep')
                if pl_trandep is not None:
                    pl_trandep = float(pl_trandep)
                    if pl_trandep < 1.0:
                        pl_trandep = pl_trandep * 1_000_000
                else:
                    pl_ratror = row.get('pl_ratror')
                    if pl_ratror is not None:
                        pl_ratror = float(pl_ratror)
                        pl_trandep = (pl_ratror ** 2) * 1_000_000
                        print(
                            f"[RemoteDiscoveryEngine] pl_trandep derived from "
                            f"pl_ratror ({pl_ratror:.6f}) → {pl_trandep:.2f} ppm",
                            file=sys.stderr,
                        )

                meta = {
                    "pl_name":        safe_canonical,
                    # Keys used by detective.py active_metadata bindings:
                    "orbital_period": pl_orbper,
                    "stellar_radius": st_rad if st_rad is not None else 1.0,
                    "transit_depth":  pl_trandep if pl_trandep is not None else 0.0,
                    # Raw archive names retained for downstream use:
                    "pl_orbper":      pl_orbper,
                    "st_rad":         st_rad if st_rad is not None else 1.0,
                    "pl_trandep":     pl_trandep if pl_trandep is not None else 0.0,
                    # Stellar parameters for physical characterization:
                    "st_teff":        st_teff,
                    "st_mass":        st_mass,
                    "sy_jmag":        sy_jmag,
                    "raw_row_dump":   row,
                }

                # ── NUMERIC SANITIZATION LAYER ─────────────────────────────
                meta = RemoteDiscoveryEngine._sanitize_meta(meta)
            else:
                print(
                    f"[RemoteDiscoveryEngine] No archive rows for '{safe_canonical}'.",
                    file=sys.stderr,
                )

        except Exception as exc:
            archive_error = str(exc)
            print(
                f"[RemoteDiscoveryEngine] Archive query failed for '{canonical}': {exc}",
                file=sys.stderr,
            )
            # safe_canonical may not exist if the exception fired before assignment
            safe_canonical = canonical.strip()

        # ── 2. Fetch photometric time-series from MAST via Lightkurve ─────
        if mission == "NASA Exoplanet Archive":
            print(f"[RemoteDiscoveryEngine] '{mission}' selected: Skipping MAST download, returning metadata only.", file=sys.stderr)
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
            }

        mast_error: str | None = None
        try:
            def download_pure_tess_pipeline(t_name):
                print("[PIPELINE] Entering Pure TESS Download Track...", file=sys.stderr)
                # Use a sharp target name format — guarded against MAST search hangs
                search = RemoteDiscoveryEngine._call_with_timeout(
                    lk.search_lightcurve, args=(t_name,),
                    kwargs={"author": "SPOC"}, timeout=15.0,
                    label="search_lightcurve(TESS/SPOC)"
                )
                if search is None:
                    print("[PIPELINE] TESS search timed out — aborting.", file=sys.stderr)
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                if len(search) == 0:
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                lc_list = []
                for row in search:
                    for attempt in range(3):
                        try:
                            lc = RemoteDiscoveryEngine._download_with_timeout(row, timeout=15.0)
                            if lc is not None:
                                lc_list.append(lc)
                            break
                        except Exception as e:
                            if RemoteDiscoveryEngine._is_fits_corruption(e):
                                RemoteDiscoveryEngine._wipe_lightkurve_cache()
                            if attempt == 2:
                                print(f"Skipping a problematic sector due to network cut: {e}", file=sys.stderr)
                
                if not lc_list:
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                lc_collection = lk.LightCurveCollection(lc_list)
                
                print("[PIPELINE] TESS Download Complete. Processing data arrays...", file=sys.stderr)
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
                sort_idx = np.argsort(t)
                
                return {
                    "status": "success",
                    "metadata": meta,
                    "time": t[sort_idx],
                    "flux": f[sort_idx],
                    "flux_err": e[sort_idx],
                    "archive_error": archive_error,
                }

            def download_pure_kepler_pipeline(t_name):
                print("[PIPELINE] Entering Pure Kepler Download Track...", file=sys.stderr)
                # Use a sharp target name format — guarded against MAST search hangs
                search = RemoteDiscoveryEngine._call_with_timeout(
                    lk.search_lightcurve, args=(t_name,),
                    kwargs={"author": "Kepler"}, timeout=15.0,
                    label="search_lightcurve(Kepler)"
                )
                if search is None:
                    print("[PIPELINE] Kepler search timed out — aborting.", file=sys.stderr)
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                if len(search) == 0:
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                lc_list = []
                for row in search:
                    for attempt in range(3):
                        try:
                            lc = RemoteDiscoveryEngine._download_with_timeout(row, timeout=15.0)
                            if lc is not None:
                                lc_list.append(lc)
                            break
                        except Exception as e:
                            if RemoteDiscoveryEngine._is_fits_corruption(e):
                                RemoteDiscoveryEngine._wipe_lightkurve_cache()
                            if attempt == 2:
                                print(f"Skipping a problematic sector due to network cut: {e}", file=sys.stderr)
                
                if not lc_list:
                    return {"status": "no_time_series", "metadata": meta, "archive_error": archive_error}
                
                lc_collection = lk.LightCurveCollection(lc_list)
                
                print("[PIPELINE] Kepler Download Complete. Processing data arrays...", file=sys.stderr)
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
                sort_idx = np.argsort(t)
                
                return {
                    "status": "success",
                    "metadata": meta,
                    "time": t[sort_idx],
                    "flux": f[sort_idx],
                    "flux_err": e[sort_idx],
                    "archive_error": archive_error,
                }

            def download_combined_fusion_pipeline(t_name):
                print("[PIPELINE] Entering Combined Fusion Download Track...", file=sys.stderr)
                # DYNAMIC NAME-TO-COORDINATE RESOLUTION
                from astropy.coordinates import SkyCoord
                import astropy.units as u
                import requests
                import time

                print(f"[RemoteDiscoveryEngine] Resolving coordinates dynamically for '{safe_canonical}'", file=sys.stderr)

                query = f"SELECT ra, dec FROM pscomppars WHERE pl_name = '{safe_canonical}'"
                url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
                params = {"query": query, "format": "json"}

                target_coords = t_name
                for attempt in range(3):
                    try:
                        resp = requests.get(url, params=params, timeout=15.0)
                        resp.raise_for_status()
                        data = resp.json()
                        if data and len(data) > 0:
                            ra_val = float(data[0]['ra'])
                            dec_val = float(data[0]['dec'])
                            target_coords = SkyCoord(ra=ra_val*u.deg, dec=dec_val*u.deg, frame='icrs')
                            print(f"[RemoteDiscoveryEngine] Using SkyCoord(RA={ra_val}, Dec={dec_val})", file=sys.stderr)
                        break
                    except Exception as e:
                        if attempt == 2:
                            print(f"[RemoteDiscoveryEngine] Coordinate query failed after 3 attempts: {e}. Falling back to string.", file=sys.stderr)
                        else:
                            time.sleep(2.0)

                search_tess = RemoteDiscoveryEngine._call_with_timeout(
                    lk.search_lightcurve, args=(target_coords,),
                    kwargs={"author": "SPOC"}, timeout=15.0,
                    label="search_lightcurve(combined/TESS)"
                )
                if search_tess is None:
                    search_tess = lk.SearchResult([])
                search_kepler = RemoteDiscoveryEngine._call_with_timeout(
                    lk.search_lightcurve, args=(target_coords,),
                    kwargs={"author": "Kepler"}, timeout=15.0,
                    label="search_lightcurve(combined/Kepler)"
                )
                if search_kepler is None:
                    search_kepler = lk.SearchResult([])
                total_results = len(search_tess) + len(search_kepler)

                if total_results == 0:
                    return {
                        "status": "no_time_series",
                        "metadata": meta,
                        "archive_error": archive_error,
                    }

                # MULTI-MISSION TIME-COORDINATE UNIFICATION ENGINE
                _KEPLER_BKJD_OFFSET = 2454833.0
                _TESS_BTJD_OFFSET   = 2457000.0
                _UNIFIED_EPOCH      = _KEPLER_BKJD_OFFSET

                def _combined_download_and_unify():
                    lc_list = []
                    
                    for row in search_tess:
                        for attempt in range(3):
                            try:
                                lc = RemoteDiscoveryEngine._download_with_timeout(row, timeout=15.0)
                                if lc is not None:
                                    lc_list.append(lc)
                                break
                            except Exception as e:
                                if RemoteDiscoveryEngine._is_fits_corruption(e):
                                    RemoteDiscoveryEngine._wipe_lightkurve_cache()
                                if attempt == 2:
                                    print(f"Skipping a problematic sector due to network cut: {e}")

                    for row in search_kepler:
                        for attempt in range(3):
                            try:
                                lc = RemoteDiscoveryEngine._download_with_timeout(row, timeout=15.0)
                                if lc is not None:
                                    lc_list.append(lc)
                                break
                            except Exception as e:
                                if RemoteDiscoveryEngine._is_fits_corruption(e):
                                    RemoteDiscoveryEngine._wipe_lightkurve_cache()
                                if attempt == 2:
                                    print(f"Skipping a problematic sector due to network cut: {e}")

                    if not lc_list:
                        return None

                    lc_collection = lk.LightCurveCollection(lc_list)

                    kepler_fragments = []
                    tess_fragments   = []

                    for lc in lc_collection:
                        time_fmt = getattr(lc.time, 'format', '').lower()
                        lc_norm = lc.normalize()
                        try:
                            lc_flat = lc_norm.flatten()
                        except Exception:
                            lc_flat = lc_norm

                        if time_fmt == 'btjd':
                            tess_fragments.append(lc_flat)
                        else:
                            kepler_fragments.append(lc_flat)

                    print(
                        f"[RemoteDiscoveryEngine] Combined baseline: "
                        f"{len(kepler_fragments)} Kepler/K2 + "
                        f"{len(tess_fragments)} TESS fragments",
                        file=sys.stderr,
                    )

                    unified_t = []
                    unified_f = []
                    unified_e = []

                    for lc in kepler_fragments:
                        offset = _KEPLER_BKJD_OFFSET - _UNIFIED_EPOCH
                        unified_t.append(
                            np.asarray(lc.time.value, dtype=np.float64) + offset
                        )
                        unified_f.append(
                            np.asarray(lc.flux.value, dtype=np.float64)
                        )
                        unified_e.append(
                            np.asarray(lc.flux_err.value, dtype=np.float64)
                        )

                    for lc in tess_fragments:
                        offset = _TESS_BTJD_OFFSET - _UNIFIED_EPOCH
                        unified_t.append(
                            np.asarray(lc.time.value, dtype=np.float64) + offset
                        )
                        unified_f.append(
                            np.asarray(lc.flux.value, dtype=np.float64)
                        )
                        unified_e.append(
                            np.asarray(lc.flux_err.value, dtype=np.float64)
                        )

                    n_kep = len(kepler_fragments)
                    if kepler_fragments and tess_fragments:
                        kep_scatter = np.nanmedian(
                            [np.nanstd(arr) for arr in unified_f[:n_kep]]
                        )
                        tess_scatter = np.nanmedian(
                            [np.nanstd(arr) for arr in unified_f[n_kep:]]
                        )
                        if kep_scatter > 0 and tess_scatter > 0:
                            ratio = kep_scatter / tess_scatter
                            if ratio > 2.0:
                                scale = tess_scatter / kep_scatter
                                for i in range(n_kep):
                                    med = np.nanmedian(unified_f[i])
                                    unified_f[i] = med + (unified_f[i] - med) * scale
                                    unified_e[i] = unified_e[i] * scale
                            elif ratio < 0.5:
                                scale = kep_scatter / tess_scatter
                                for i in range(n_kep, len(unified_f)):
                                    med = np.nanmedian(unified_f[i])
                                    unified_f[i] = med + (unified_f[i] - med) * scale
                                    unified_e[i] = unified_e[i] * scale

                    t_out = np.concatenate(unified_t)
                    f_out = np.concatenate(unified_f)
                    e_out = np.concatenate(unified_e)

                    valid = np.isfinite(t_out) & np.isfinite(f_out) & np.isfinite(e_out)
                    t_out, f_out, e_out = t_out[valid], f_out[valid], e_out[valid]

                    idx = np.argsort(t_out)
                    t_out, f_out, e_out = t_out[idx], f_out[idx], e_out[idx]

                    return {
                        "kepler_segments": len(kepler_fragments),
                        "tess_segments":   len(tess_fragments),
                        "time": t_out,
                        "flux": f_out,
                        "flux_err": e_out,
                    }

                combined_result = None
                try:
                    combined_result = _combined_download_and_unify()
                except (OSError, ValueError, Exception) as fits_err:
                    if RemoteDiscoveryEngine._is_fits_corruption(fits_err):
                        print(
                            f"[RemoteDiscoveryEngine] FITS CORRUPTION DETECTED "
                            f"in combined download: {fits_err}",
                            file=sys.stderr,
                        )
                        RemoteDiscoveryEngine._wipe_lightkurve_cache()
                        combined_result = _combined_download_and_unify()
                    else:
                        raise

                if combined_result is None:
                    return {
                        "status": "no_time_series",
                        "metadata": meta,
                        "archive_error": archive_error,
                    }

                meta["time_baseline"]   = "unified_bkjd"
                meta["unified_epoch"]   = _UNIFIED_EPOCH
                meta["kepler_segments"] = combined_result["kepler_segments"]
                meta["tess_segments"]   = combined_result["tess_segments"]

                return {
                    "status":        "success",
                    "metadata":      meta,
                    "time":          combined_result["time"],
                    "flux":          combined_result["flux"],
                    "flux_err":      combined_result["flux_err"],
                    "archive_error": archive_error,
                }

            # Immediate UI Mode Selection
            mode = mission
            if mode == "TESS" or mode == "TESS Only" or mode == "TESS (via Lightkurve)":
                # Route to a completely isolated, clean, legacy download function
                return download_pure_tess_pipeline(target_name)
            elif mode == "Combined Baseline (Kepler + TESS)":
                # Route to the experimental multi-mission stitching block
                return download_combined_fusion_pipeline(target_name)
            elif mode == "Kepler" or mode == "Kepler Only" or mode == "Kepler (via Lightkurve)":
                return download_pure_kepler_pipeline(target_name)
            else:
                print(f"[RemoteDiscoveryEngine] Unrecognized or metadata-only mode '{mode}': Returning metadata only.", file=sys.stderr)
                return {
                    "status": "no_time_series",
                    "metadata": meta,
                    "archive_error": archive_error,
                }

        except Exception as exc:
            mast_error = str(exc)
            print(
                f"[RemoteDiscoveryEngine] MAST download failed for '{canonical}': {exc}",
                file=sys.stderr,
            )
            return {
                "status":      "error",
                "metadata":    meta,
                "archive_error": archive_error,
                "mast_error":  mast_error,
            }


# ---------------------------------------------------------------------------
# Module-level cached wrapper
# ---------------------------------------------------------------------------
# @st.cache_data MUST be applied at module level to work reliably across all
# Streamlit versions.  Applying it as a decorator on a @staticmethod inside a
# class body causes cache misses and silent re-execution on every rerun.
@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_data(target_name: str, mission: str = "Kepler") -> dict:
    """Cached entry point — delegates to ``RemoteDiscoveryEngine._fetch_data_impl``.

    Parameters
    ----------
    target_name:
        Raw planet name (any capitalisation / spacing variant).
    mission:
        Lightkurve mission string (``'Kepler'``, ``'TESS'``, etc.).

    Returns
    -------
    dict with keys:
        ``status``        – ``'success'`` | ``'no_time_series'`` | ``'error'``
        ``metadata``      – archive parameter dict (may be empty)
        ``archive_error`` – str or None
        ``mast_error``    – str or None  (only on ``'error'`` status)
        ``time``          – 1-D float64 array  (success only)
        ``flux``          – 1-D float64 array  (success only)
        ``flux_err``      – 1-D float64 array  (success only)
    """
    return RemoteDiscoveryEngine._fetch_data_impl(target_name, mission)


# Attach as a class attribute so callers using RemoteDiscoveryEngine.fetch_data
# continue to work without any import-site changes.
RemoteDiscoveryEngine.fetch_data = staticmethod(_cached_fetch_data)
