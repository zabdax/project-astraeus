"""ASTRAEUS project module."""

import lightkurve as lk
import numpy as np
import pandas as pd
import json
import astropy.units as u

from astraeus.core.time_units import to_bjd

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

def extract_lightcurve_arrays(lc: lk.LightCurve, mission: str = "Kepler") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extracts time, flux, and flux_err arrays from a light curve.

    I2 fix (round-2 diagnostic 2026-07-06, see
    logs/diagnostic_run_round2_*.json): the time array is converted
    from the mission-specific offset (BKJD / BTJD) to BJD full here so
    every downstream consumer gets a consistent, explicitly labeled
    epoch. Use `astraeus.core.time_units.to_bjd` for the conversion.
    """
    t = np.asarray(lc.time.value, dtype=np.float64)
    t = to_bjd(t, mission)
    return t, lc.flux.value, lc.flux_err.value

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
    return extract_lightcurve_arrays(lc, mission=mission)

def _resolve_columns(df: pd.DataFrame, column_map: dict = None) -> tuple[str, str, str]:
    """Resolves time, flux, and flux_err column names using mapping or heuristics."""
    if column_map is None:
        column_map = {}
        
    time_col = column_map.get('time')
    flux_col = column_map.get('flux')
    err_col = column_map.get('flux_err')
    
    if not time_col:
        # Audit fix M13 (2026-08-21): substring patterns mirror
        # DataAdapter.TIME_PATTERNS (astraeus/data/adapter.py) so both
        # loaders agree on the canonical schema; exact-only matching could
        # not map e.g. 'bjd_tdb'.  'bjd' as a substring also covers
        # 'bjd_tdb', so the tuple stays coverage-equivalent.
        time_patterns = ('time', 'bjd', 'hjd', 'mjd')
        for col in df.columns:
            c_lower = str(col).lower()
            if any(pat in c_lower for pat in time_patterns):
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
        # I2 fix (round-2 diagnostic 2026-07-06): convert to BJD full at
        # this ingestion boundary. See `extract_lightcurve_arrays`.
        t = np.asarray(lc.time.value, dtype=np.float64)
        t = to_bjd(t, mission)
        return t, lc.flux.value, lc.flux_err.value


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
        """Loads data using the appropriate strategy and enforces astropy units.

        Unit contract (audit fix M12, 2026-08-21):
            ``time_unit`` — the time column is genuinely *converted* to days
            (``u.day``); e.g. ``time_unit='hour'`` returns values divided by
            24.  ``flux_unit`` is accepted but must be dimensionless-
            compatible (normalized-flux convention); flux and flux_err are
            converted to ``u.dimensionless_unscaled``.  An invalid unit
            string or a non-convertible unit raises ``ValueError`` naming
            the affected column and unit.
        """
        strategy = cls._strategies.get(source_type)
        if not strategy:
            raise ValueError(f"Unsupported source_type: '{source_type}'. Expected one of {list(cls._strategies.keys())}.")

        t, f, e = strategy.load(source_path_or_id, **kwargs)

        # Ensure numpy arrays for cleaning
        t = np.asarray(t, dtype=np.float64)
        f = np.asarray(f, dtype=np.float64)
        e = np.asarray(e, dtype=np.float64)

        # 1. Clean non-finite values.  Audit fix M14 (2026-08-21): ±inf
        # poisons downstream chi2/MCMC just like NaN (the DataAdapter
        # already filters with np.isfinite); isnan alone let infinities
        # through.
        valid = np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
        t, f, e = t[valid], f[valid], e[valid]

        # 2. Check negative flux
        if (f < 0).any():
            raise AssertionError("Negative flux values detected in light curve.")

        # 3. Sort by time indices
        if len(t) > 0:
            sort_idx = np.argsort(t)
            t, f, e = t[sort_idx], f[sort_idx], e[sort_idx]

        time_unit = kwargs.get('time_unit')
        flux_unit = kwargs.get('flux_unit')

        if time_unit is not None:
            try:
                # Audit fix M12: actually convert to days — wrapping in a
                # Quantity and reading .value back was a no-op.
                t = u.Quantity(t, unit=time_unit).to(u.day).value
            except (u.UnitsError, ValueError) as exc:
                raise ValueError(
                    f"Time column: cannot convert values from unit "
                    f"'{time_unit}' to days: {exc}"
                ) from exc

        if flux_unit is not None:
            try:
                f = u.Quantity(f, unit=flux_unit).to(u.dimensionless_unscaled).value
                e = u.Quantity(e, unit=flux_unit).to(u.dimensionless_unscaled).value
            except (u.UnitsError, ValueError) as exc:
                raise ValueError(
                    f"Flux column: unit '{flux_unit}' is not dimensionless-"
                    f"compatible (normalized-flux convention required): {exc}"
                ) from exc

        return np.asarray(t, dtype=np.float64), np.asarray(f, dtype=np.float64), np.asarray(e, dtype=np.float64)


def universal_load_lightcurve(
    source_type: str,
    source_path_or_id: str,
    **kwargs
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unified Data Factory ingestion function for exoplanet light curve data."""
    return DataFactory.load(source_type, source_path_or_id, **kwargs)

