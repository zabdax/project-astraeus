"""Light-curve loading workflows for dashboard data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
import os
import tempfile

import numpy as np

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
    """Persist an uploaded file temporarily and load it through the shared loader."""

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
            tmp.write(uploaded_bytes)
            tmp_path = tmp.name

        time, flux, flux_err = universal_load_lightcurve(
            file_ext,
            tmp_path,
            column_map=column_map or {},
        )
        return LightCurveData(time=time, flux=flux, flux_err=flux_err)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
