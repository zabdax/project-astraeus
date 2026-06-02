import io
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
    Connects to NASA Exoplanet Archive and MAST via Lightkurve.
    """
    @staticmethod
    def fetch_data(target_name: str, mission: str = 'Kepler') -> dict:
        # Cache check
        state_key = f"cache_{target_name}_{mission}"
        if state_key in st.session_state:
            return st.session_state[state_key]

        # 1. Fetch metadata
        meta = {}
        try:
            res = NasaExoplanetArchive.query_criteria(
                table="pscomppars",
                select="pl_name, pl_orbper, st_rad, pl_trandep",
                where=f"pl_name = '{target_name}'"
            )
            if len(res) > 0:
                row = res[0]
                meta = {
                    "pl_name": str(row["pl_name"]),
                    "pl_orbper": float(row["pl_orbper"]) if not np.ma.is_masked(row["pl_orbper"]) else None,
                    "st_rad": float(row["st_rad"]) if not np.ma.is_masked(row["st_rad"]) else None,
                    "pl_trandep": float(row["pl_trandep"]) if not np.ma.is_masked(row["pl_trandep"]) else None
                }
        except Exception as e:
            print(f"Error querying archive: {e}", file=sys.stderr)

        # 2. Fetch Time Series
        search_result = lk.search_lightcurve(target_name, mission=mission)
        if len(search_result) == 0:
            return {"status": "no_time_series", "metadata": meta}
            
        # Capped at first 3 sectors for speed
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
        
        result = {
            "status": "success",
            "metadata": meta,
            "time": t,
            "flux": f,
            "flux_err": e
        }
        
        # Explicit caching
        st.session_state[state_key] = result
        st.session_state['active_data'] = result
        return result
