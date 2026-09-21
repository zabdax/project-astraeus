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

    # If flux_err is not present, default to zeros of the same shape.
    # (Kept for the live Streamlit consumers, PRD §16: Streamlit stays
    # green until Phase 3 exit.  The canonical ``Dataset`` adopter below
    # reads a zero-only error column as ABSENT, so the silent-invention
    # problem is fixed at the seam rather than by changing this return.)
    flux_err = parsed.get("flux_err")
    if flux_err is None or len(flux_err) == 0:
        flux_err = np.zeros_like(flux)

    return LightCurveData(time=time, flux=flux, flux_err=flux_err)


def to_dataset(
    lcd: LightCurveData,
    *,
    target_name: str,
    mission: str = "Kepler",
    time_unit: str = "BJD",
) -> "Dataset":
    """P1-D: adopt this service's arrays onto the canonical seam.

    ``LightCurveData`` has no n_cadence, no baseline, no time-unit label
    and no identity; the canonical contract adds all four.  A zero-only
    error column is read as ABSENT rather than trusted -- see
    ``load_uploaded_light_curve`` for why that matters.
    """
    from astraeus.contracts.dataset import Dataset, Mission, TargetRef, TimeUnit

    # ``load_uploaded_light_curve`` fills a zero column in place of a missing
    # one, so a ``None`` check never fires here; the seam's own rule (a
    # zero-only column IS absent) is what the source label must reflect.
    err_absent = lcd.flux_err is None or bool(
        np.all(np.asarray(lcd.flux_err) == 0.0)
    )

    return Dataset.from_light_curve_data(
        lcd,
        target=TargetRef(
            name=target_name,
            mission=Mission(mission) if mission in Mission._value2member_map_ else Mission.UNKNOWN,
        ),
        time_unit=time_unit,
        source="dashboard:uploaded" if err_absent else "dashboard:archive",
        sort=True,
    )
