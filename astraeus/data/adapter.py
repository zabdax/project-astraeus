"""Intelligent, format-agnostic DataAdapter for exoplanet datasets."""

import io
import numpy as np
import pandas as pd
from astropy.io import fits


class DataAdapter:
    """
    Format-agnostic adapter to normalize incoming exoplanet datasets
    (CSV and FITS formats) into a single structured internal format.
    """

    TIME_PATTERNS = ["time", "bjd_tdb", "bjd", "hjd", "mjd"]
    FLUX_PATTERNS = ["flux", "pdcsap_flux", "sap_flux", "intensity", "counts"]
    ERR_PATTERNS = ["err", "sig", "error", "uncertainty"]

    def __init__(
        self,
        data_bytes: bytes,
        filename_or_ext: str,
        column_map: dict[str, str] | None = None,
    ):
        """
        Initialize the DataAdapter.

        Args:
            data_bytes (bytes): The raw file bytes in memory.
            filename_or_ext (str): The filename or file extension.
            column_map (dict, optional): Manual column mapping overrides.
                E.g. {'time': 'col1', 'flux': 'col2'}.
        """
        self.data_bytes = data_bytes
        self.filename_or_ext = filename_or_ext.lower().strip()
        self.column_map = {k.lower(): v for k, v in (column_map or {}).items()}
        self.metadata: dict = {}
        self.normalized_data: dict = {}

    def parse(self) -> dict:
        """
        Auto-detect format, parse the dataset, extract metadata, and normalize arrays.

        Returns:
            dict: Structured normalized data holding 'time', 'flux', and optionally 'flux_err',
                  along with an embedded 'metadata' dictionary.
        """
        is_csv = self.filename_or_ext.endswith(".csv") or self.filename_or_ext == "csv"
        is_json = self.filename_or_ext.endswith(".json") or self.filename_or_ext == "json"
        is_fits = (
            self.filename_or_ext.endswith(".fits")
            or self.filename_or_ext.endswith(".fit")
            or self.filename_or_ext in ("fits", "fit")
        )

        if is_csv:
            self._parse_csv()
        elif is_json:
            self._parse_json()
        elif is_fits:
            self._parse_fits()
        else:
            raise ValueError(
                f"Unsupported file format for extension/name: '{self.filename_or_ext}'. "
                "Expected CSV, JSON, FITS, or FIT."
            )

        # Save back to Streamlit active_data state if in Streamlit context
        self._preserve_in_streamlit()

        return self.normalized_data

    def _parse_csv(self) -> None:
        """Parse CSV content using pandas from an in-memory stream."""
        df = pd.read_csv(io.BytesIO(self.data_bytes))
        columns = list(df.columns)

        # Scan and resolve columns
        time_col, flux_col, err_col = self._scan_columns(columns)

        # Extract raw arrays
        time_raw = df[time_col].to_numpy()
        flux_raw = df[flux_col].to_numpy()

        flux_err_raw = None
        if err_col:
            flux_err_raw = df[err_col].to_numpy()

        # Clean and standardize arrays
        self.normalized_data = self._standardize_arrays(time_raw, flux_raw, flux_err_raw)
        self.normalized_data["metadata"] = {}  # CSV typically lacks headers

    def _parse_json(self) -> None:
        """Parse JSON content using pandas/json from an in-memory stream."""
        import json as json_lib

        try:
            df = pd.read_json(io.BytesIO(self.data_bytes))
        except ValueError:
            data = json_lib.loads(self.data_bytes.decode("utf-8"))
            df = pd.DataFrame(data)

        columns = list(df.columns)

        # Scan and resolve columns
        time_col, flux_col, err_col = self._scan_columns(columns)

        # Extract raw arrays
        time_raw = df[time_col].to_numpy()
        flux_raw = df[flux_col].to_numpy()

        flux_err_raw = None
        if err_col:
            flux_err_raw = df[err_col].to_numpy()

        # Clean and standardize arrays
        self.normalized_data = self._standardize_arrays(time_raw, flux_raw, flux_err_raw)
        self.normalized_data["metadata"] = {}  # JSON typically lacks headers

    def _parse_fits(self) -> None:
        """Parse FITS content using astropy.io.fits from an in-memory stream."""
        with fits.open(io.BytesIO(self.data_bytes)) as hdul:
            # 1. Extract metadata from primary header matrix (HDU 0)
            self.metadata = self._extract_fits_metadata(hdul)

            # 2. Find the first BinTableHDU
            table_hdu = None
            for hdu in hdul:
                if isinstance(hdu, fits.BinTableHDU):
                    table_hdu = hdu
                    break

            if table_hdu is None:
                raise ValueError("No binary table extension (BinTableHDU) found in the FITS file.")

            # Extract column names from FITS table
            columns = list(table_hdu.columns.names)

            # Scan and resolve columns
            time_col, flux_col, err_col = self._scan_columns(columns)

            # Extract arrays natively from FITS table data
            # Force conversion to float64 and handle endianness safely via numpy
            time_raw = np.array(table_hdu.data[time_col], dtype=np.float64)
            flux_raw = np.array(table_hdu.data[flux_col], dtype=np.float64)

            flux_err_raw = None
            if err_col:
                flux_err_raw = np.array(table_hdu.data[err_col], dtype=np.float64)

            # Clean and standardize arrays
            self.normalized_data = self._standardize_arrays(time_raw, flux_raw, flux_err_raw)
            self.normalized_data["metadata"] = self.metadata

    def _scan_columns(self, columns: list[str]) -> tuple[str, str, str | None]:
        """
        Intelligently scan and map available column names to time, flux, and flux_err.
        """
        col_mapping = {col.lower(): col for col in columns}
        norm_cols = list(col_mapping.keys())

        # 1. Map Time Column
        time_col = None
        if "time" in self.column_map:
            override = self.column_map["time"]
            if override.lower() in col_mapping:
                time_col = col_mapping[override.lower()]

        if not time_col:
            for pattern in self.TIME_PATTERNS:
                if pattern in col_mapping:
                    time_col = col_mapping[pattern]
                    break
            if not time_col:
                for col in norm_cols:
                    if any(pat in col for pat in self.TIME_PATTERNS):
                        time_col = col_mapping[col]
                        break

        if not time_col:
            raise ValueError(f"Could not map required 'time' column. Available: {columns}")

        # 2. Map Flux Column
        flux_col = None
        if "flux" in self.column_map:
            override = self.column_map["flux"]
            if override.lower() in col_mapping:
                flux_col = col_mapping[override.lower()]

        if not flux_col:
            # Exact match, avoiding error keywords
            for pattern in self.FLUX_PATTERNS:
                if pattern in col_mapping and not any(
                    err_pat in pattern for err_pat in self.ERR_PATTERNS
                ):
                    flux_col = col_mapping[pattern]
                    break
            # Substring match, avoiding error keywords
            if not flux_col:
                for col in norm_cols:
                    if any(pat in col for pat in self.FLUX_PATTERNS) and not any(
                        err_pat in col for err_pat in self.ERR_PATTERNS
                    ):
                        flux_col = col_mapping[col]
                        break

        if not flux_col:
            raise ValueError(f"Could not map required 'flux' column. Available: {columns}")

        # 3. Map Flux Error Column
        err_col = None
        if "flux_err" in self.column_map:
            override = self.column_map["flux_err"]
            if override.lower() in col_mapping:
                err_col = col_mapping[override.lower()]

        if not err_col:
            flux_col_lower = flux_col.lower()
            # Try to find error column related to selected flux column (e.g. pdcsap_flux_err)
            for col in norm_cols:
                if flux_col_lower in col and any(err_pat in col for err_pat in self.ERR_PATTERNS):
                    err_col = col_mapping[col]
                    break
            # General fallback to any error column
            if not err_col:
                for col in norm_cols:
                    if any(err_pat in col for err_pat in self.ERR_PATTERNS):
                        err_col = col_mapping[col]
                        break

        return time_col, flux_col, err_col

    def _standardize_arrays(
        self,
        time_raw: np.ndarray,
        flux_raw: np.ndarray,
        flux_err_raw: np.ndarray | None,
    ) -> dict:
        """
        Clean missing values, NaNs, and Infs. Cast to np.float64 and sort chronologically.
        """
        time_arr = np.asarray(time_raw, dtype=np.float64)
        flux_arr = np.asarray(flux_raw, dtype=np.float64)

        valid_mask = np.isfinite(time_arr) & np.isfinite(flux_arr)

        flux_err_arr = None
        if flux_err_raw is not None:
            flux_err_arr = np.asarray(flux_err_raw, dtype=np.float64)
            valid_mask &= np.isfinite(flux_err_arr)

        time_clean = time_arr[valid_mask]
        flux_clean = flux_arr[valid_mask]

        if len(time_clean) > 0:
            sort_idx = np.argsort(time_clean)
            time_clean = time_clean[sort_idx]
            flux_clean = flux_clean[sort_idx]
        else:
            sort_idx = np.array([], dtype=int)

        result = {"time": time_clean, "flux": flux_clean}

        if flux_err_arr is not None:
            flux_err_clean = flux_err_arr[valid_mask]
            if len(flux_err_clean) > 0:
                flux_err_clean = flux_err_clean[sort_idx]
            result["flux_err"] = flux_err_clean

        return result

    def _extract_fits_metadata(self, hdul: fits.HDUList) -> dict:
        """Extract primary target identification data directly from FITS headers."""
        meta = {}
        primary_hdr = hdul[0].header

        target_keys = [
            "OBJECT",
            "RA",
            "DEC",
            "TICID",
            "KEPLERID",
            "KICID",
            "CAMPAIGN",
            "QUARTER",
        ]
        for key in target_keys:
            if key in primary_hdr:
                meta[key.lower()] = primary_hdr[key]

        # Grab all other standard fields excluding history/comments
        for key in primary_hdr:
            key_lower = key.lower()
            if key and key not in ("COMMENT", "HISTORY", "") and key_lower not in meta:
                meta[key_lower] = primary_hdr[key]

        return meta

    def _preserve_in_streamlit(self) -> None:
        """Store output in st.session_state.active_data if in Streamlit context."""
        try:
            import streamlit as st

            # This will succeed only if there is a running Streamlit session
            st.session_state["active_data"] = self.normalized_data
        except Exception:
            pass
