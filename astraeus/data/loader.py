"""ASTRAEUS project module."""

import lightkurve as lk
import numpy as np
import pandas as pd
import json
import astropy.units as u

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

def _resolve_columns(df: pd.DataFrame, column_map: dict = None) -> tuple[str, str, str]:
    """Resolves time, flux, and flux_err column names using mapping or heuristics."""
    if column_map is None:
        column_map = {}
        
    time_col = column_map.get('time')
    flux_col = column_map.get('flux')
    err_col = column_map.get('flux_err')
    
    if not time_col:
        for col in df.columns:
            c_lower = str(col).lower()
            if 'time' in c_lower or c_lower in ['bjd', 'hjd', 'mjd']:
                time_col = col
                break
                
    if not flux_col:
        for col in df.columns:
            c_lower = str(col).lower()
            if ('flux' in c_lower or 'intensity' in c_lower or 'counts' in c_lower) and ('err' not in c_lower and 'sig' not in c_lower):
                flux_col = col
                break

    if not err_col:
        for col in df.columns:
            c_lower = str(col).lower()
            if 'err' in c_lower or 'sig' in c_lower:
                err_col = col
                break

    missing = []
    if not time_col or time_col not in df.columns:
        missing.append('time')
    if not flux_col or flux_col not in df.columns:
        missing.append('flux')
    if not err_col or err_col not in df.columns:
        missing.append('flux_err')

    if missing:
        raise ValueError(f"Could not confidently map required columns: {', '.join(missing)}. Available columns: {list(df.columns)}")
        
    return time_col, flux_col, err_col


from abc import ABC, abstractmethod

class DataLoaderStrategy(ABC):
    """Abstract base class for data loading strategies."""
    
    @abstractmethod
    def load(self, source_path_or_id: str, **kwargs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Loads data and returns time, flux, flux_err arrays."""
        pass


class NASAArchiveLoader(DataLoaderStrategy):
    """Loads data from the NASA Exoplanet Archive via lightkurve."""
    
    def load(self, source_path_or_id: str, **kwargs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        mission = kwargs.get('mission', 'Kepler')
        quarter = kwargs.get('quarter', None)
        search_result = lk.search_lightcurve(source_path_or_id, mission=mission, quarter=quarter)
        
        if len(search_result) == 0:
            raise ValueError(f"No data found for target '{source_path_or_id}' in mission '{mission}'.")

        lc_collection = search_result.download_all() if quarter is None else search_result.download()
        lc = lc_collection.stitch() if hasattr(lc_collection, 'stitch') else lc_collection
        lc = lc[lc.quality == 0].remove_nans().normalize()
        return lc.time.value, lc.flux.value, lc.flux_err.value


class CSVLoader(DataLoaderStrategy):
    """Loads light curve data from a CSV file."""
    
    def load(self, source_path_or_id: str, **kwargs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        df = pd.read_csv(source_path_or_id, **kwargs.get('csv_kwargs', {}))
        column_map = kwargs.get('column_map')
        time_col, flux_col, err_col = _resolve_columns(df, column_map)
        return df[time_col].values, df[flux_col].values, df[err_col].values


class JSONLoader(DataLoaderStrategy):
    """Loads light curve data from a JSON file."""
    
    def load(self, source_path_or_id: str, **kwargs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        try:
            df = pd.read_json(source_path_or_id, **kwargs.get('json_kwargs', {}))
        except ValueError:
            with open(source_path_or_id, 'r') as f_in:
                data = json.load(f_in)
            df = pd.DataFrame(data)

        column_map = kwargs.get('column_map')
        time_col, flux_col, err_col = _resolve_columns(df, column_map)
        return df[time_col].values, df[flux_col].values, df[err_col].values


class DataFactory:
    """Factory to instantiate and execute the correct data loader strategy."""
    
    _strategies = {
        'api': NASAArchiveLoader(),
        'csv': CSVLoader(),
        'json': JSONLoader(),
    }

    @classmethod
    def register_strategy(cls, source_type: str, strategy: DataLoaderStrategy):
        """Register a new data loading strategy to satisfy OCP."""
        cls._strategies[source_type] = strategy

    @classmethod
    def load(cls, source_type: str, source_path_or_id: str, **kwargs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Loads data using the appropriate strategy and enforces astropy units."""
        strategy = cls._strategies.get(source_type)
        if not strategy:
            raise ValueError(f"Unsupported source_type: '{source_type}'. Expected one of {list(cls._strategies.keys())}.")
            
        t, f, e = strategy.load(source_path_or_id, **kwargs)

        time_unit = kwargs.get('time_unit')
        flux_unit = kwargs.get('flux_unit')
        
        if time_unit is not None:
            try:
                t = u.Quantity(t, unit=time_unit).value
            except u.UnitConversionError as exc:
                raise u.UnitsError(f"Time unit {time_unit} error: {exc}")
        
        if flux_unit is not None:
            try:
                f = u.Quantity(f, unit=flux_unit).value
                e = u.Quantity(e, unit=flux_unit).value
            except u.UnitConversionError as exc:
                raise u.UnitsError(f"Flux unit {flux_unit} error: {exc}")

        return np.asarray(t, dtype=np.float64), np.asarray(f, dtype=np.float64), np.asarray(e, dtype=np.float64)


def universal_load_lightcurve(
    source_type: str,
    source_path_or_id: str,
    **kwargs
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unified Data Factory ingestion function for exoplanet light curve data."""
    return DataFactory.load(source_type, source_path_or_id, **kwargs)

