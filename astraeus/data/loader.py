"""ASTRAEUS project module."""

import lightkurve as lk
import numpy as np

def fetch_lightcurve(target_name: str, mission: str = "Kepler") -> lk.LightCurve:
    """Fetches and stitches light curve data from NASA archives."""
    search_result = lk.search_lightcurve(target_name, mission=mission)
    
    if len(search_result) == 0:
        raise ValueError(f"No data found for target '{target_name}' in mission '{mission}'.")

    lc_collection = search_result.download_all()
    return lc_collection.stitch()

def clean_lightcurve(lc: lk.LightCurve) -> lk.LightCurve:
    """Removes bad quality flags and drops NaNs from a light curve."""
    lc = lc[lc.quality == 0]
    return lc.remove_nans()

def extract_lightcurve_arrays(lc: lk.LightCurve) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extracts time, flux, and flux_err arrays from a light curve."""
    return lc.time.value, lc.flux.value, lc.flux_err.value

def load_nasa_lightcurve(target_name: str, mission: str = "Kepler") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    High-level facade to download and prepare observational light curve data.

    Args:
        target_name (str): The name of the target (e.g., 'Kepler-10', 'TrES-2b').
        mission (str): The mission to search for data (e.g., 'Kepler', 'TESS', 'K2').

    Returns:
        tuple: A tuple containing (time, flux, flux_err) as numpy arrays.
    """
    lc = fetch_lightcurve(target_name, mission=mission)
    lc = clean_lightcurve(lc)
    lc = lc.normalize()
    return extract_lightcurve_arrays(lc)
