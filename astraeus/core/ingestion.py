import sys

from astraeus.data.adapter import DataAdapter
from astraeus.core.nasa_archive import NASAExoplanetArchive
from astraeus.core.lightkurve_client import LightkurveClient

class RemoteDiscoveryEngine:
    """
    Connects to NASA Exoplanet Archive (TAP/pscomppars table) and MAST via
    Lightkurve. Acts as a facade coordinating NASAExoplanetArchive and LightkurveClient.
    """

    @staticmethod
    def _fetch_data_impl(target_name: str, mission: str) -> dict:
        canonical = NASAExoplanetArchive.normalize_target_name(target_name)
        meta, archive_error = NASAExoplanetArchive.fetch_metadata(canonical)

        if mission == "NASA Exoplanet Archive":
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
            }

        mast_error = None
        data = None

        if mission in ("TESS", "TESS Only", "TESS (via Lightkurve)"):
            data, mast_error = LightkurveClient.download_pipeline(target_name, "TESS")
        elif mission in ("Kepler", "Kepler Only", "Kepler (via Lightkurve)"):
            data, mast_error = LightkurveClient.download_pipeline(target_name, "Kepler")
        elif mission == "Combined Baseline (Kepler + TESS)":
            data, mast_error = LightkurveClient.download_combined_fusion(meta.get("pl_name", canonical))
        else:
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
            }

        if data is None:
            return {
                "status": "error" if mast_error else "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
                "mast_error": mast_error,
            }

        if "baseline" in data:
            meta["time_baseline"] = data["baseline"]
            meta["kepler_segments"] = data.get("kepler_segments", 0)
            meta["tess_segments"] = data.get("tess_segments", 0)

        return {
            "status": "success",
            "metadata": meta,
            "time": data["time"],
            "flux": data["flux"],
            "flux_err": data["flux_err"],
            "archive_error": archive_error,
            "mast_error": mast_error,
        }

def _cached_fetch_data(target_name: str, mission: str = "Kepler") -> dict:
    import streamlit as st
    @st.cache_data(ttl=3600, show_spinner=False)
    def _inner_fetch(t_name, m_name):
        return RemoteDiscoveryEngine._fetch_data_impl(t_name, m_name)
    return _inner_fetch(target_name, mission)

RemoteDiscoveryEngine.fetch_data = staticmethod(_cached_fetch_data)

# Export DataAdapter for backwards compatibility
__all__ = ["RemoteDiscoveryEngine", "DataAdapter"]
