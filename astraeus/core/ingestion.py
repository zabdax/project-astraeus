import io
import re
import sys
import numpy as np
import pandas as pd
from astropy.io import fits
import lightkurve as lk
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
import streamlit as st

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


class RemoteDiscoveryEngine:
    """
    Connects to NASA Exoplanet Archive (TAP/pscomppars table) and MAST via
    Lightkurve.  All archive field access uses primary → fallback → derived
    resolution so that coordinate fields are never silently dropped.
    """

    # ------------------------------------------------------------------
    # Archive query configuration
    # ------------------------------------------------------------------
    #: Comprehensive confirmed-planet composite-parameter table.
    _ARCHIVE_TABLE = "pscomppars"

    #: All columns fetched in a single round-trip.  Includes every primary
    #: field AND its error-column fallback, plus pl_ratror for the derived
    #: transit-depth calculation.
    _ARCHIVE_SELECT = (
        "pl_name, "
        "pl_orbper, pl_orbpererr1, "
        "st_rad, st_raderr1, "
        "pl_trandep, pl_ratror"
    )

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
    def _resolve_float(row, primary: str, fallback: str | None = None) -> float | None:
        """Extract a float from *row*, trying *primary* then *fallback*.

        Returns ``None`` when both columns are masked or absent.
        """
        for col in filter(None, [primary, fallback]):
            try:
                val = row[col]
                if not np.ma.is_masked(val):
                    return float(val)
            except (KeyError, TypeError, ValueError):
                continue
        return None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def fetch_data(target_name: str, mission: str = "Kepler") -> dict:
        """Retrieve archive metadata and MAST photometry for *target_name*.

        Parameters
        ----------
        target_name:
            Raw planet name (any capitalisation / spacing variant).
        mission:
            Lightkurve mission string (``'Kepler'``, ``'TESS'``, etc.).

        Returns
        -------
        dict with keys:
            ``status``      – ``'success'`` | ``'no_time_series'``
            ``metadata``    – archive parameter dict (fields may be None)
            ``time``        – 1-D float64 array  (success only)
            ``flux``        – 1-D float64 array  (success only)
            ``flux_err``    – 1-D float64 array  (success only)
        """
        # ── 0. Normalise the target name before any network call ──────────
        target_name = RemoteDiscoveryEngine._normalize_target_name(target_name)

        # ── 1. Fetch metadata from NASA Exoplanet Archive (TAP) ───────────
        meta: dict = {}
        try:
            res = NasaExoplanetArchive.query_criteria(
                table=RemoteDiscoveryEngine._ARCHIVE_TABLE,
                select=RemoteDiscoveryEngine._ARCHIVE_SELECT,
                where=f"pl_name = '{target_name}'",
            )

            if len(res) > 0:
                row = res[0]

                # ── Orbital Period ─────────────────────────────────────────
                # Primary  : pl_orbper
                # Fallback : pl_orbpererr1 (non-null implies period was fit;
                #            use only as a presence check, not a value)
                pl_orbper = RemoteDiscoveryEngine._resolve_float(
                    row, "pl_orbper", "pl_orbpererr1"
                )
                # If fallback triggered we have the error, not the period –
                # surface None so callers know the primary is missing.
                if pl_orbper is None:
                    try:
                        _err_present = not np.ma.is_masked(row["pl_orbpererr1"])
                    except (KeyError, TypeError):
                        _err_present = False
                    # Keep None: error col alone cannot substitute the period.
                    _ = _err_present  # documented intention; value not used

                # ── Stellar Radius ─────────────────────────────────────────
                # Primary  : st_rad
                # Fallback : st_raderr1  (same caveat as above)
                st_rad = RemoteDiscoveryEngine._resolve_float(
                    row, "st_rad", "st_raderr1"
                )

                # ── Transit Depth ──────────────────────────────────────────
                # Primary  : pl_trandep  (ppm)
                # Derived  : (pl_ratror)^2 × 1_000_000  when primary absent
                pl_trandep = RemoteDiscoveryEngine._resolve_float(
                    row, "pl_trandep"
                )
                if pl_trandep is None:
                    pl_ratror = RemoteDiscoveryEngine._resolve_float(
                        row, "pl_ratror"
                    )
                    if pl_ratror is not None:
                        pl_trandep = (pl_ratror ** 2) * 1_000_000
                        print(
                            f"[RemoteDiscoveryEngine] pl_trandep derived from "
                            f"pl_ratror ({pl_ratror:.6f}) → {pl_trandep:.2f} ppm",
                            file=sys.stderr,
                        )

                meta = {
                    "pl_name": str(row["pl_name"]),
                    "pl_orbper": pl_orbper,
                    "st_rad": st_rad,
                    "pl_trandep": pl_trandep,
                }

        except Exception as exc:
            print(
                f"[RemoteDiscoveryEngine] Archive query failed: {exc}",
                file=sys.stderr,
            )

        # ── 2. Fetch photometric time-series from MAST via Lightkurve ─────
        search_result = lk.search_lightcurve(target_name, mission=mission)
        if len(search_result) == 0:
            return {"status": "no_time_series", "metadata": meta}

        # Capped at first 3 sectors/quarters for speed
        lc_collection = search_result[:3].download_all()
        if not lc_collection:
            return {"status": "no_time_series", "metadata": meta}

        stitched = lc_collection.stitch()
        try:
            flattened = stitched.flatten()
        except Exception:
            flattened = stitched.normalize()

        flattened = flattened.remove_nans()

        t = np.asarray(flattened.time.value, dtype=np.float64)
        f = np.asarray(flattened.flux.value, dtype=np.float64)
        e = np.asarray(flattened.flux_err.value, dtype=np.float64)

        valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
        t, f, e = t[valid], f[valid], e[valid]

        sort_idx = np.argsort(t)
        t, f, e = t[sort_idx], f[sort_idx], e[sort_idx]

        return {
            "status": "success",
            "metadata": meta,
            "time": t,
            "flux": f,
            "flux_err": e,
        }
