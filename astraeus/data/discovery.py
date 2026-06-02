"""Discovery module for remote exoplanet data ingestion and time-series extraction."""

import sys
import numpy as np
import lightkurve as lk
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

class RemoteDiscoveryEngine:
    """
    A unified module to programmatically query planetary metadata from the 
    NASA Exoplanet Archive and download observation time-series from MAST.
    """

    @staticmethod
    def query_metadata(target_name: str) -> dict:
        """
        Queries the NASA Exoplanet Archive for target metadata.
        Prioritizes the 'pscomppars' composite table, then falls back to 'ps'.
        
        Args:
            target_name (str): Exoplanet designation (e.g., 'WASP-12 b')
            
        Returns:
            dict: Parsed metadata (pl_name, pl_orbper, st_rad, pl_trandep)
        """
        query_cols = "pl_name, pl_orbper, st_rad, pl_trandep"
        where_clause = f"pl_name = '{target_name}'"
        
        # 1. Try pscomppars for composite robust parameters
        try:
            res = NasaExoplanetArchive.query_criteria(
                table="pscomppars",
                select=query_cols,
                where=where_clause
            )
            if len(res) > 0:
                row = res[0]
                return {
                    "pl_name": str(row["pl_name"]),
                    "pl_orbper": float(row["pl_orbper"]) if not np.ma.is_masked(row["pl_orbper"]) else None,
                    "st_rad": float(row["st_rad"]) if not np.ma.is_masked(row["st_rad"]) else None,
                    "pl_trandep": float(row["pl_trandep"]) if not np.ma.is_masked(row["pl_trandep"]) else None,
                    "source_table": "pscomppars"
                }
        except Exception as e:
            print(f"Error querying pscomppars: {e}", file=sys.stderr)

        # 2. Try ps
        try:
            res = NasaExoplanetArchive.query_criteria(
                table="ps",
                select=query_cols,
                where=where_clause
            )
            if len(res) > 0:
                # 'ps' can return multiple rows, find the one with the most non-null values or just take first
                row = res[0]
                return {
                    "pl_name": str(row["pl_name"]),
                    "pl_orbper": float(row["pl_orbper"]) if not np.ma.is_masked(row["pl_orbper"]) else None,
                    "st_rad": float(row["st_rad"]) if not np.ma.is_masked(row["st_rad"]) else None,
                    "pl_trandep": float(row["pl_trandep"]) if not np.ma.is_masked(row["pl_trandep"]) else None,
                    "source_table": "ps"
                }
        except Exception as e:
            print(f"Error querying ps: {e}", file=sys.stderr)
            
        return {}
        
    @staticmethod
    def fetch_time_series(target_name: str, mission: str) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """
        Fetches time-series arrays using lightkurve from MAST.
        Limits to first 3 segments to optimize speed. Stitches and flattens them.
        
        Args:
            target_name (str): Target designation
            mission (str): Mission name ('TESS' or 'Kepler')
            
        Returns:
            tuple: (time, flux, flux_err) as numpy float64 arrays, or None if failed.
        """
        try:
            search_result = lk.search_lightcurve(target_name, mission=mission)
            if len(search_result) == 0:
                return None
                
            # Limit to first 3 segments for speed
            limited_search = search_result[:3]
            lc_collection = limited_search.download_all()
            
            if not lc_collection:
                return None
                
            # Stitch the collection
            stitched = lc_collection.stitch()
            
            # Flatten/normalize around baseline 1.0
            try:
                flattened = stitched.flatten()
            except Exception:
                # Fallback to simple normalization if flatten fails (e.g. not enough points)
                flattened = stitched.normalize()
                
            # Remove NaNs inside lightkurve
            flattened = flattened.remove_nans()
            
            return (
                np.asarray(flattened.time.value, dtype=np.float64),
                np.asarray(flattened.flux.value, dtype=np.float64),
                np.asarray(flattened.flux_err.value, dtype=np.float64)
            )
            
        except Exception as e:
            print(f"Error fetching time series for {target_name}: {e}", file=sys.stderr)
            return None

    @staticmethod
    def discover_and_cache(target_name: str, mission: str) -> dict:
        """
        Orchestrates metadata query, time-series download, cleaning, 
        and caching into Streamlit session state.
        
        Args:
            target_name (str): Target to search
            mission (str): 'TESS', 'Kepler', etc.
            
        Returns:
            dict: Summarized results or empty dict if not found.
        """
        metadata = RemoteDiscoveryEngine.query_metadata(target_name)
        arrays = RemoteDiscoveryEngine.fetch_time_series(target_name, mission)
        
        if arrays is None:
            return {"metadata": metadata, "status": "no_time_series"}
            
        t, f, e = arrays
        
        # Clean and sort chronologically
        valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
        t, f, e = t[valid], f[valid], e[valid]
        
        sort_idx = np.argsort(t)
        t, f, e = t[sort_idx], f[sort_idx], e[sort_idx]
        
        result = {
            "time": t,
            "flux": f,
            "flux_err": e,
            "metadata": metadata,
            "status": "success"
        }
        
        # Cache into Streamlit session states
        try:
            import streamlit as st
            st.session_state["active_data"] = result
            
            # For data ingestion panel standard
            from astraeus.dashboard.services.data_ingestion import LightCurveData
            st.session_state["dashboard_light_curve_data"] = LightCurveData(
                time=t, flux=f, flux_err=e
            )
        except Exception:
            pass # Ignore if not running in Streamlit
            
        return result
