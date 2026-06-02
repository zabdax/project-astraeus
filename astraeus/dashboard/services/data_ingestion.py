"""Light-curve loading workflows for dashboard data ingestion."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from astraeus.data import DataAdapter
from astraeus.data.loader import universal_load_lightcurve


@dataclass(frozen=True)
class LightCurveData:
    """Loaded light-curve arrays ready for preview or analysis."""

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray


def load_archive_light_curve(target_id: str, mission: str) -> LightCurveData:
    """Load a light curve from the configured remote archive backend."""

    time, flux, flux_err = universal_load_lightcurve("api", target_id, mission=mission)
    return LightCurveData(time=time, flux=flux, flux_err=flux_err)


def load_uploaded_light_curve(
    uploaded_bytes: bytes,
    file_ext: str,
    column_map: dict[str, str] | None = None,
) -> LightCurveData:
    """Load an uploaded file natively using the format-agnostic DataAdapter."""
    adapter = DataAdapter(
        data_bytes=uploaded_bytes,
        filename_or_ext=file_ext,
        column_map=column_map,
    )
    parsed = adapter.parse()

    time = parsed["time"]
    flux = parsed["flux"]

    # If flux_err is not present, default to zeros of the same shape
    flux_err = parsed.get("flux_err")
    if flux_err is None or len(flux_err) == 0:
        flux_err = np.zeros_like(flux)

    return LightCurveData(time=time, flux=flux, flux_err=flux_err)
