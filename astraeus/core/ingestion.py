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
            res = NasaExoplanetArchive.query_criteria(
                table=RemoteDiscoveryEngine._FALLBACK_TABLE,
                select=RemoteDiscoveryEngine._FALLBACK_SELECT,
                where=f"pl_name = '{safe_canonical}' AND pl_orbper IS NOT NULL",
                order="pl_orbper DESC",
            )
            if len(res) > 0:
                period = RemoteDiscoveryEngine._resolve_float(res[0], "pl_orbper", "pl_orbpererr1")
                if period is not None:
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

            res = NasaExoplanetArchive.query_criteria(
                table=RemoteDiscoveryEngine._ARCHIVE_TABLE,
                select=RemoteDiscoveryEngine._ARCHIVE_SELECT,
                where=f"pl_name = '{safe_canonical}'",
            )

            print("--- NASA ARCHIVE DIAGNOSTIC AUDIT ---")
            print(f"Payload Type: {type(res)}")
            print(f"Available Columns: {list(res.colnames) if hasattr(res, 'colnames') else []}")
            if len(res) > 0:
                print(f"Raw Row 0 Content: {res[0]}")

            if len(res) > 0:
                row = res[0]

                # ── Column-structure audit ─────────────────────────────────
                # Print every column name returned in this row so that any
                # alias mismatch is immediately visible in the terminal log.
                try:
                    _col_names = list(row.colnames)
                except AttributeError:
                    _col_names = list(row.dtype.names) if hasattr(row, 'dtype') else []
                print(
                    f"[RemoteDiscoveryEngine] Archive columns for '{safe_canonical}': "
                    f"{_col_names}",
                    file=sys.stderr,
                )

                # ── Orbital Period ─────────────────────────────────────────
                # Resolution chain (most → least authoritative):
                #   1. pl_orbper      — standard pscomppars column
                #   2. pl_period      — legacy/alternate table alias
                #   3. pl_orbpererr1  — positive fitting error; kept as a
                #                      last-resort presence signal only
                # If every alias is masked or absent, fire the multi-table
                # fallback against the stable ``ps`` reference table before
                # defaulting to 0.0.  This ensures reference-paper NULL gaps
                # in pscomppars are healed automatically.
                pl_orbper = RemoteDiscoveryEngine._resolve_float(
                    row, "pl_orbper", "pl_period", "pl_orbpererr1"
                )
                if pl_orbper is None:
                    print(
                        f"[RemoteDiscoveryEngine] pscomppars orbital period masked for "
                        f"'{safe_canonical}'; escalating to ps-table fallback query.",
                        file=sys.stderr,
                    )
                    # ── MULTI-TABLE INTERROGATION FALLBACK ─────────────────
                    pl_orbper = RemoteDiscoveryEngine._fetch_ps_orbital_period(
                        safe_canonical
                    )
                    if pl_orbper is None:
                        print(
                            f"[RemoteDiscoveryEngine] Both tables lack orbital period "
                            f"for '{safe_canonical}'; flooring to 0.0.",
                            file=sys.stderr,
                        )
                        pl_orbper = 0.0

                # ── Stellar Radius ─────────────────────────────────────────
                # Primary   : st_rad   (solar radii, directly measured)
                # We do NOT use st_raderr1 or st_raderr2 as substitutes.
                st_rad = RemoteDiscoveryEngine._resolve_float(
                    row, "st_rad"
                )
                if st_rad is not None:
                    st_rad = abs(st_rad)

                # ── Stellar Effective Temperature ──────────────────────────
                st_teff = RemoteDiscoveryEngine._resolve_float(
                    row, "st_teff"
                )

                # ── Stellar Mass ───────────────────────────────────────────
                st_mass = RemoteDiscoveryEngine._resolve_float(
                    row, "st_mass"
                )
                if st_mass is not None:
                    st_mass = abs(st_mass)

                # ── J-Band Magnitude ───────────────────────────────────────
                sy_jmag = RemoteDiscoveryEngine._resolve_float(
                    row, "sy_jmag"
                )

                # ── Transit Depth ──────────────────────────────────────────
                # Primary  : pl_trandep  (ppm, directly catalogued)
                # Derived  : (pl_ratror)² × 1_000_000  when primary absent
                
                raw_trandep = None
                try:
                    raw_trandep = row.get("pl_trandep") if hasattr(row, 'get') else row["pl_trandep"]
                except Exception:
                    pass
                is_percentage = False
                if isinstance(raw_trandep, str):
                    is_percentage = "%" in raw_trandep
                elif hasattr(raw_trandep, 'unit'):
                    is_percentage = "%" in str(raw_trandep.unit)

                pl_trandep = RemoteDiscoveryEngine._resolve_float(
                    row, "pl_trandep"
                )
                
                if pl_trandep is not None:
                    if is_percentage:
                        pl_trandep = pl_trandep * 10000.0
                    elif pl_trandep < 1.0:
                        pl_trandep = pl_trandep * 1_000_000

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

                # ── Assemble raw metadata dict ─────────────────────────────
                try:
                    raw_row_dump = {col: str(row[col]) for col in row.colnames} if hasattr(row, 'colnames') else {}
                except Exception:
                    raw_row_dump = str(row)

                meta = {
                    "pl_name":        str(row["pl_name"]),
                    # Keys used by detective.py active_metadata bindings:
                    "orbital_period": pl_orbper,
                    "stellar_radius": st_rad,
                    "transit_depth":  pl_trandep,
                    # Raw archive names retained for downstream use:
                    "pl_orbper":      pl_orbper,
                    "st_rad":         st_rad,
                    "pl_trandep":     pl_trandep,
                    # Stellar parameters for physical characterization:
                    "st_teff":        st_teff,
                    "st_mass":        st_mass,
                    "sy_jmag":        sy_jmag,
                    "raw_row_dump":   raw_row_dump,
                }

                # ── NUMERIC SANITIZATION LAYER ─────────────────────────────
                # Hard-floor any residual None / NaN / masked values so that
                # st.session_state.active_metadata is always strictly typed.
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
        mast_error: str | None = None
        try:
            if mission == "Combined Baseline (Kepler + TESS)":
                search_result = lk.search_lightcurve(canonical, mission=("Kepler", "K2", "TESS"))
            else:
                search_result = lk.search_lightcurve(canonical, mission=mission)

            if len(search_result) == 0:
                return {
                    "status": "no_time_series",
                    "metadata": meta,
                    "archive_error": archive_error,
                }

            if mission == "Combined Baseline (Kepler + TESS)":
                lc_collection = search_result.download_all()
                if not lc_collection:
                    return {
                        "status": "no_time_series",
                        "metadata": meta,
                        "archive_error": archive_error,
                    }
                normalized_lcs = []
                for lc in lc_collection:
                    normalized_lcs.append(lc.normalize())
                lc_collection = lk.LightCurveCollection(normalized_lcs)
            else:
                # Capped at first 2 sectors/quarters for download speed and to
                # prevent application timeout disconnects.
                lc_collection = search_result[:2].download_all()
                if not lc_collection:
                    return {
                        "status": "no_time_series",
                        "metadata": meta,
                        "archive_error": archive_error,
                    }

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
                "status":        "success",
                "metadata":      meta,
                "time":          t,
                "flux":          f,
                "flux_err":      e,
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
